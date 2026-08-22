#!/usr/bin/env python3
"""
Flutter Forge - Security ZIP Extractor and Validator.
Ensures safe extraction of myapp.zip into a temporary workspace.
"""

import json
import os
import re
import shutil
import zipfile
import yaml

FORBIDDEN_EXTENSIONS = {
    ".sh", ".exe", ".bat", ".cmd", ".bin", ".jar", ".class", ".so", ".dll", ".dylib", ".gradle", ".kts"
}

FORBIDDEN_FILES = {
    "build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts",
    "AndroidManifest.xml", "MainActivity.kt", "MainActivity.java"
}

ALLOWED_ASSET_PREFIXES = ("assets/images/", "assets/sounds/", "assets/fonts/", "assets/")


class ZIPValidationError(Exception):
    pass


def is_path_safe(base_dir: str, target_path: str) -> bool:
    """Prevents Path Traversal attacks (../, absolute paths, symlinks)."""
    base_dir = os.path.realpath(base_dir)
    target_path = os.path.realpath(target_path)
    return target_path.startswith(base_dir + os.sep) or target_path == base_dir


def extract_and_validate_zip(zip_path: str, extract_to_dir: str) -> str:
    """
    Validates myapp.zip and extracts safe contents into extract_to_dir.
    Returns path to extracted workspace.
    """
    if not os.path.isfile(zip_path):
        raise ZIPValidationError(f"ZIP file not found at: {zip_path}")

    if not zipfile.is_zipfile(zip_path):
        raise ZIPValidationError(f"File {zip_path} is not a valid zip file")

    os.makedirs(extract_to_dir, exist_ok=True)
    extract_to_dir_abs = os.path.realpath(extract_to_dir)

    with zipfile.ZipFile(zip_path, 'r') as zf:
        infolist = zf.infolist()

        # Detect single root wrapper folder offset if present
        root_dirs = set()
        for member in infolist:
            parts = member.filename.strip("/").split("/")
            if len(parts) > 1:
                root_dirs.add(parts[0])

        has_single_wrapper = len(root_dirs) == 1 and not any("/" not in m.filename.strip("/") and m.filename.strip("/") != "" for m in infolist)

        # Check path traversal and forbidden files
        for member in infolist:
            filename = member.filename

            # Remove single root wrapper prefix for path checks if wrapped
            check_filename = filename
            if has_single_wrapper:
                parts = filename.strip("/").split("/")
                check_filename = "/".join(parts[1:]) if len(parts) > 1 else ""

            if not check_filename:
                continue

            # Path traversal check
            if ".." in filename or filename.startswith("/") or filename.startswith("\\"):
                raise ZIPValidationError(f"Forbidden path traversal detected in ZIP entry: {filename}")

            target_path = os.path.abspath(os.path.join(extract_to_dir_abs, filename))
            if not is_path_safe(extract_to_dir_abs, target_path):
                raise ZIPValidationError(f"Path traversal detected outside target dir: {filename}")

            base_name = os.path.basename(filename)
            ext = os.path.splitext(filename)[1].lower()

            # Check forbidden extensions & specific script files
            if ext in FORBIDDEN_EXTENSIONS:
                raise ZIPValidationError(f"Executable or dangerous extension forbidden in ZIP: {filename}")

            if base_name in FORBIDDEN_FILES:
                raise ZIPValidationError(f"Modification of native/gradle file forbidden in ZIP: {filename}")

            # Disallow files outside allowed directories (app.json, pubspec.yaml, lib/, assets/)
            normalized = check_filename.strip("/")
            top_level = normalized.split("/")[0] if "/" in normalized else normalized

            if top_level not in {"app.json", "pubspec.yaml", "lib", "assets", "test"}:
                raise ZIPValidationError(f"Forbidden top-level directory/file in ZIP: {top_level}")

        # Perform extraction safely
        zf.extractall(extract_to_dir_abs)

    # If ZIP contains a single root folder containing the files, handle root folder offset
    extracted_contents = os.listdir(extract_to_dir_abs)
    if len(extracted_contents) == 1:
        single_item = os.path.join(extract_to_dir_abs, extracted_contents[0])
        if os.path.isdir(single_item) and os.path.exists(os.path.join(single_item, "app.json")):
            # Shift files up
            for sub_item in os.listdir(single_item):
                shutil.move(os.path.join(single_item, sub_item), extract_to_dir_abs)
            shutil.rmtree(single_item)

    # Mandatory files check
    required_files = ["app.json", "pubspec.yaml", "lib/main.dart"]
    for req in required_files:
        full_path = os.path.join(extract_to_dir_abs, req)
        if not os.path.isfile(full_path):
            raise ZIPValidationError(f"Missing required file in ZIP: {req}")

    return extract_to_dir_abs


def validate_app_json(app_json_path: str) -> dict:
    """Validates structure and values in app.json."""
    if not os.path.isfile(app_json_path):
        raise ZIPValidationError("app.json does not exist")

    try:
        with open(app_json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        raise ZIPValidationError(f"Invalid app.json syntax: {str(e)}")

    if not isinstance(data, dict):
        raise ZIPValidationError("app.json root must be a JSON object")

    # Required fields
    required_fields = ["name", "package", "version", "versionCode"]
    for field in required_fields:
        if field not in data or data[field] is None:
            raise ZIPValidationError(f"app.json missing required field: '{field}'")

    # Package name validation (e.g. com.example.myapp)
    package_pattern = r'^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$'
    if not re.match(package_pattern, str(data["package"])):
        raise ZIPValidationError(f"Invalid package name in app.json: '{data['package']}'")

    # App name non-empty string validation
    if not isinstance(data["name"], str) or not data["name"].strip():
        raise ZIPValidationError("app.json 'name' must be a non-empty string")

    # Version validation (e.g. 1.0.0)
    if not isinstance(data["version"], str) or not data["version"].strip():
        raise ZIPValidationError("app.json 'version' must be a valid string")

    # VersionCode validation (integer > 0)
    if not isinstance(data["versionCode"], int) or data["versionCode"] < 1:
        raise ZIPValidationError("app.json 'versionCode' must be a positive integer")

    # Permissions list validation (optional, default empty list)
    if "permissions" in data:
        if not isinstance(data["permissions"], list):
            raise ZIPValidationError("app.json 'permissions' must be a list of strings")
        for perm in data["permissions"]:
            if not isinstance(perm, str):
                raise ZIPValidationError("Permission items in app.json must be strings")

    return data


def validate_pubspec_yaml(pubspec_path: str) -> dict:
    """Validates pubspec.yaml rules according to DEPENDENCY_POLICY.md."""
    if not os.path.isfile(pubspec_path):
        raise ZIPValidationError("pubspec.yaml does not exist")

    try:
        with open(pubspec_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
    except Exception as e:
        raise ZIPValidationError(f"Invalid pubspec.yaml syntax: {str(e)}")

    if not isinstance(data, dict):
        raise ZIPValidationError("pubspec.yaml root must be a dictionary")

    # Check dependencies for unconstrained or illegal versions
    deps = data.get("dependencies", {})
    if isinstance(deps, dict):
        for pkg, ver in deps.items():
            if pkg in ("flutter", "flutter_test"):
                continue
            if isinstance(ver, str):
                ver_str = ver.strip().lower()
                if ver_str in ("any", "latest", "+") or ver_str.startswith("+"):
                    raise ZIPValidationError(f"Forbidden unconstrained dependency version for '{pkg}': '{ver}'")

    dev_deps = data.get("dev_dependencies", {})
    if isinstance(dev_deps, dict):
        for pkg, ver in dev_deps.items():
            if pkg in ("flutter", "flutter_test"):
                continue
            if isinstance(ver, str):
                ver_str = ver.strip().lower()
                if ver_str in ("any", "latest", "+") or ver_str.startswith("+"):
                    raise ZIPValidationError(f"Forbidden unconstrained dev_dependency version for '{pkg}': '{ver}'")

    return data
