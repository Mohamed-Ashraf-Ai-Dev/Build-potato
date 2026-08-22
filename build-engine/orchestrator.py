#!/usr/bin/env python3
"""
Flutter Forge Build Orchestrator Engine.
Handles end-to-end pipeline:
1. Receive & Validate ZIP
2. Validate app.json & pubspec.yaml
3. Inject assets & lib into fixed Template
4. Configure package name, app name, and permissions
5. Execute flutter pub get, flutter analyze, flutter test, flutter build
6. Sign output (if release)
7. Clean up temporary directories
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

from validator import extract_and_validate_zip, validate_app_json, validate_pubspec_yaml
from signing_engine import generate_keystore, sign_apk, sign_aab, verify_apk_signature, verify_aab_signature


class BuildPipelineError(Exception):
    pass


def run_cmd(cmd, cwd=None, env=None):
    print(f"Executing: {' '.join(cmd)} (cwd={cwd or '.'})")
    res = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"STDOUT:\n{res.stdout}")
        print(f"STDERR:\n{res.stderr}")
        raise BuildPipelineError(f"Command failed with exit code {res.returncode}: {' '.join(cmd)}")
    return res.stdout


def update_android_manifest(manifest_path: str, package_name: str, app_name: str, permissions: list):
    """Updates AndroidManifest.xml package name, app label, and injects requested permissions."""
    if not os.path.isfile(manifest_path):
        raise BuildPipelineError(f"AndroidManifest.xml not found at {manifest_path}")

    # Register namespace prefix to avoid ns0 prefixing
    ET.register_namespace('android', 'http://schemas.android.com/apk/res/android')
    tree = ET.parse(manifest_path)
    root = tree.getroot()

    android_ns = "{http://schemas.android.com/apk/res/android}"

    # Update manifest package attribute
    root.attrib['package'] = package_name

    # Update application label
    app_node = root.find('application')
    if app_node is not None:
        app_node.set(f"{android_ns}label", app_name)

    # Inject permissions safely
    existing_perms = set()
    for p in root.findall('uses-permission'):
        name = p.get(f"{android_ns}name")
        if name:
            existing_perms.add(name)

    for perm in permissions:
        # Format android permission if short name given
        full_perm = perm if perm.startswith("android.permission.") else f"android.permission.{perm}"
        if full_perm not in existing_perms:
            perm_elem = ET.Element('uses-permission', {f"{android_ns}name": full_perm})
            root.insert(0, perm_elem)
            existing_perms.add(full_perm)

    tree.write(manifest_path, encoding='utf-8', xml_declaration=True)
    print(f"Updated AndroidManifest.xml for package {package_name} with {len(permissions)} permissions.")


def update_build_gradle_kts(build_gradle_path: str, package_name: str, version_name: str, version_code: int):
    """Updates default Application ID, versionName, and versionCode in app/build.gradle.kts."""
    if not os.path.isfile(build_gradle_path):
        raise BuildPipelineError(f"build.gradle.kts not found at {build_gradle_path}")

    with open(build_gradle_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Replace namespace and applicationId
    content = re.sub(r'namespace\s*=\s*".*?"', f'namespace = "{package_name}"', content)
    content = re.sub(r'applicationId\s*=\s*".*?"', f'applicationId = "{package_name}"', content)

    if 'versionCode' in content:
        content = re.sub(r'versionCode\s*=\s*.*', f'versionCode = {version_code}', content)
    if 'versionName' in content:
        content = re.sub(r'versionName\s*=\s*.*', f'versionName = "{version_name}"', content)

    with open(build_gradle_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"Updated build.gradle.kts namespace/applicationId to {package_name}, versionCode={version_code}, versionName={version_name}")


def merge_pubspec(template_pubspec_path: str, zip_pubspec_data: dict, app_name: str, app_version: str):
    """Merges app pubspec dependencies into fixed template pubspec without overriding SDK environment lock."""
    with open(template_pubspec_path, 'r', encoding='utf-8') as f:

        import yaml
        template_data = yaml.safe_load(f)

    # Base template metadata
    clean_name = re.sub(r'[^a-z0-9_]', '_', app_name.lower().replace(' ', '_'))
    clean_name = re.sub(r'_+', '_', clean_name).strip('_')
    if not clean_name or not clean_name[0].isalpha():
        clean_name = "app_" + clean_name
    template_data['name'] = clean_name
    # Incorporate versionCode into pubspec version string (e.g. 1.0.0+1) if app_version doesn't already have build number
    app_version_str = str(app_version)
    if '+' not in app_version_str and 'versionCode' in zip_pubspec_data:
        app_version_str = f"{app_version_str}+{zip_pubspec_data['versionCode']}"

    template_data['version'] = app_version_str

    # Preserve fixed SDK lock
    template_data['environment'] = {
        'sdk': '>=3.0.0 <4.0.0',
        'flutter': '>=3.19.0'
    }

    # Merge dependencies
    zip_deps = zip_pubspec_data.get('dependencies', {})
    if isinstance(zip_deps, dict):
        for k, v in zip_deps.items():
            if k != 'flutter':
                template_data.setdefault('dependencies', {})[k] = v

    # Merge dev_dependencies
    zip_dev_deps = zip_pubspec_data.get('dev_dependencies', {})
    if isinstance(zip_dev_deps, dict):
        for k, v in zip_dev_deps.items():
            if k != 'flutter_test':
                template_data.setdefault('dev_dependencies', {})[k] = v

    # Register assets folder if exists
    template_data['flutter'] = template_data.get('flutter', {})
    assets_list = template_data['flutter'].get('assets', [])
    if 'assets/' not in assets_list:
        assets_list.append('assets/')

    # Auto-register subdirectories in assets/
    workspace_assets = os.path.join(os.path.dirname(template_pubspec_path), 'assets')
    if os.path.isdir(workspace_assets):
        for root_dir, dirs, files in os.walk(workspace_assets):
            rel_dir = os.path.relpath(root_dir, os.path.dirname(template_pubspec_path)).replace("\\", "/") + "/"
            if rel_dir != "assets/" and rel_dir not in assets_list:
                assets_list.append(rel_dir)

    template_data['flutter']['assets'] = assets_list

    with open(template_pubspec_path, 'w', encoding='utf-8') as f:
        yaml.dump(template_data, f, default_flow_style=False)
    print(f"Successfully merged pubspec.yaml for project {template_data['name']}")


def process_app_icon(workspace_template_dir: str, icon_rel_path: str):
    """Optionally replaces default launcher icon if specified in app.json."""
    if not icon_rel_path:
        return
    src_icon = os.path.join(workspace_template_dir, icon_rel_path)
    if os.path.isfile(src_icon):
        # Copy icon into android res drawable
        res_dir = os.path.join(workspace_template_dir, "android", "app", "src", "main", "res", "drawable")
        os.makedirs(res_dir, exist_ok=True)
        shutil.copyfile(src_icon, os.path.join(res_dir, "ic_launcher_app.png"))
        print(f"Copied custom app icon from {icon_rel_path}")


def run_build_pipeline(zip_path: str, build_type: str, output_path: str):
    """Executes full reproducible build workflow."""
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    template_source_dir = os.path.join(repo_root, "template", "flutter")

    if not os.path.isdir(template_source_dir):
        raise BuildPipelineError(f"Fixed Flutter Template not found at {template_source_dir}")

    # Step 1: Create isolated temporary workspace
    with tempfile.TemporaryDirectory() as temp_dir:
        print(f"--- Created temporary build workspace: {temp_dir} ---")
        zip_extract_dir = os.path.join(temp_dir, "extracted")
        build_workspace_dir = os.path.join(temp_dir, "flutter_project")

        # Step 2: Validate & Extract ZIP
        print("--- Step 1/8: Extracting and validating ZIP ---")
        extract_and_validate_zip(zip_path, zip_extract_dir)

        # Step 3: Validate app.json & pubspec.yaml
        print("--- Step 2/8: Validating app.json and pubspec.yaml ---")
        app_data = validate_app_json(os.path.join(zip_extract_dir, "app.json"))
        pubspec_data = validate_pubspec_yaml(os.path.join(zip_extract_dir, "pubspec.yaml"))

        # Step 4: Copy fixed Flutter template to build workspace
        print("--- Step 3/8: Initializing workspace from fixed Template ---")
        shutil.copytree(template_source_dir, build_workspace_dir)

        # Step 5: Replace lib and copy assets from ZIP into workspace
        print("--- Step 4/8: Injecting app lib and assets ---")
        target_lib = os.path.join(build_workspace_dir, "lib")
        if os.path.exists(target_lib):
            shutil.rmtree(target_lib)
        shutil.copytree(os.path.join(zip_extract_dir, "lib"), target_lib)

        target_test = os.path.join(build_workspace_dir, "test")
        src_test = os.path.join(zip_extract_dir, "test")
        if os.path.exists(src_test):
            if os.path.exists(target_test):
                shutil.rmtree(target_test)
            shutil.copytree(src_test, target_test)
        else:
            if os.path.exists(target_test):
                shutil.rmtree(target_test)

        src_assets = os.path.join(zip_extract_dir, "assets")
        target_assets = os.path.join(build_workspace_dir, "assets")
        if os.path.exists(src_assets):
            if os.path.exists(target_assets):
                shutil.rmtree(target_assets)
            shutil.copytree(src_assets, target_assets)
        else:
            os.makedirs(target_assets, exist_ok=True)

        # Update Android settings & Manifest
        manifest_path = os.path.join(build_workspace_dir, "android", "app", "src", "main", "AndroidManifest.xml")
        gradle_path = os.path.join(build_workspace_dir, "android", "app", "build.gradle.kts")

        update_android_manifest(manifest_path, app_data["package"], app_data["name"], app_data.get("permissions", []))
        update_build_gradle_kts(gradle_path, app_data["package"], app_data["version"], app_data["versionCode"])
        process_app_icon(build_workspace_dir, app_data.get("icon"))

        # Merge pubspec safely
        merge_pubspec(os.path.join(build_workspace_dir, "pubspec.yaml"), pubspec_data, app_data["name"], app_data["version"])

        # Step 6: Run Flutter tooling checks
        print("--- Step 5/8: Running flutter pub get, analyze, test ---")
        run_cmd(["flutter", "pub", "get"], cwd=build_workspace_dir)

        # Analyze lib code
        run_cmd(["flutter", "analyze"], cwd=build_workspace_dir)

        # Run test if test folder exists
        if os.path.isdir(os.path.join(build_workspace_dir, "test")):
            run_cmd(["flutter", "test"], cwd=build_workspace_dir)

        # Step 7: Build target artifact
        print(f"--- Step 6/8: Compiling Flutter build target: {build_type} ---")
        if build_type == "debug-apk":
            run_cmd(["flutter", "build", "apk", "--debug"], cwd=build_workspace_dir)
            generated_artifact = os.path.join(build_workspace_dir, "build", "app", "outputs", "flutter-apk", "app-debug.apk")
        elif build_type == "release-apk":
            run_cmd(["flutter", "build", "apk", "--release"], cwd=build_workspace_dir)
            generated_artifact = os.path.join(build_workspace_dir, "build", "app", "outputs", "flutter-apk", "app-release.apk")
        elif build_type == "release-aab":
            run_cmd(["flutter", "build", "appbundle", "--release"], cwd=build_workspace_dir)
            generated_artifact = os.path.join(build_workspace_dir, "build", "app", "outputs", "bundle", "release", "app-release.aab")
        else:
            raise BuildPipelineError(f"Unknown build type: {build_type}")

        if not os.path.isfile(generated_artifact):
            raise BuildPipelineError(f"Build output artifact missing at: {generated_artifact}")

        # Step 8: Sign Release artifacts using Signing Engine
        print("--- Step 7/8: Processing Signing & Artifact Output ---")
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

        if build_type == "debug-apk":
            shutil.copyfile(generated_artifact, output_path)
            print(f"Debug APK output ready: {output_path}")
        else:
            # Generate temporary keystore for Release signing
            keystore_file = os.path.join(temp_dir, "forge_release.keystore")
            alias = "forge_key"
            storepass = "ForgeSecureStorePass123!"
            keypass = "ForgeSecureStorePass123!"

            generate_keystore(keystore_file, alias, keypass, storepass)

            if build_type == "release-apk":
                sign_apk(generated_artifact, keystore_file, alias, keypass, storepass, output_path)
                if not verify_apk_signature(output_path):
                    raise BuildPipelineError("Signed APK signature verification failed!")
            elif build_type == "release-aab":
                sign_aab(generated_artifact, keystore_file, alias, keypass, storepass, output_path)
                if not verify_aab_signature(output_path):
                    raise BuildPipelineError("Signed AAB signature verification failed!")

        print(f"--- Step 8/8: Build pipeline succeeded! Final output: {output_path} ---")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Flutter Forge Build Orchestrator")
    parser.add_argument("--zip", required=True, help="Path to input myapp.zip")
    parser.add_argument("--type", choices=["debug-apk", "release-apk", "release-aab"], required=True, help="Build target type")
    parser.add_argument("--output", required=True, help="Path for output signed artifact")

    args = parser.parse_args()

    try:
        run_build_pipeline(args.zip, args.type, args.output)
    except Exception as e:
        print(f"\n[BUILD FACTORY FAILURE] {str(e)}", file=sys.stderr)
        sys.exit(1)
