#!/usr/bin/env python3
"""
Flutter Forge Comprehensive 23-Test Suite Execution Script.
Executes all 23 verification scenarios required by specification.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

# Add build-engine and signing to PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "build-engine")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "signing")))

from orchestrator import run_build_pipeline, BuildPipelineError
from validator import extract_and_validate_zip, validate_app_json, validate_pubspec_yaml, ZIPValidationError
from signing_engine import verify_apk_signature, verify_aab_signature

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TEST_TEMP = os.path.join(REPO_ROOT, "tests", "temp_workspaces")

PASSED_TESTS = []
FAILED_TESTS = []


def run_test(test_name: str, test_func):
    """Runner helper for capturing test status."""
    print(f"\n==================================================")
    print(f"RUNNING: {test_name}")
    print(f"==================================================")
    try:
        test_func()
        print(f"SUCCESS: {test_name} passed!")
        PASSED_TESTS.append(test_name)
    except Exception as e:
        print(f"FAILURE: {test_name} failed with error: {e}")
        FAILED_TESTS.append((test_name, str(e)))


def make_zip(zip_dest_path: str, files_dict: dict):
    """Creates a test zip file from a dictionary mapping file path -> string content or bytes."""
    os.makedirs(os.path.dirname(zip_dest_path), exist_ok=True)
    with zipfile.ZipFile(zip_dest_path, 'w') as zf:
        for fname, content in files_dict.items():
            if isinstance(content, bytes):
                zf.writestr(fname, content)
            else:
                zf.writestr(fname, content)


def base_valid_files():
    return {
        "app.json": json.dumps({
            "name": "Test App",
            "package": "com.forge.testapp",
            "version": "1.0.0",
            "versionCode": 1,
            "permissions": ["CAMERA", "INTERNET"]
        }),
        "pubspec.yaml": "name: testapp\ndescription: A test app\nversion: 1.0.0\nenvironment:\n  sdk: '>=3.0.0 <4.0.0'\ndependencies:\n  flutter:\n    sdk: flutter\n",
        "lib/main.dart": "import 'package:flutter/material.dart'; void main() => runApp(const MaterialApp(home: Scaffold(body: Text('Hello Forge'))));\n"
    }


# --- TEST DEFINITIONS ---

def test_1_flutter_template_alone():
    """Test 1: Fixed Template alone builds cleanly."""
    template_dir = os.path.join(REPO_ROOT, "template", "flutter")
    res = subprocess.run(["flutter", "analyze"], cwd=template_dir, capture_output=True, text=True)
    assert res.returncode == 0, f"Template analysis failed: {res.stderr}"


def test_2_simple_flutter_app():
    """Test 2: Basic Flutter application build."""
    zip_path = os.path.join(TEST_TEMP, "test2.zip")
    out_apk = os.path.join(TEST_TEMP, "test2-debug.apk")
    make_zip(zip_path, base_valid_files())
    run_build_pipeline(zip_path, "debug-apk", out_apk)
    assert os.path.isfile(out_apk), "Debug APK missing"


def test_3_multiple_screens():
    """Test 3: Multiple Dart screens."""
    files = base_valid_files()
    files["lib/screen1.dart"] = "import 'package:flutter/material.dart'; class Screen1 extends StatelessWidget { const Screen1({super.key}); @override Widget build(BuildContext context) => const Text('Screen1'); }"
    files["lib/screen2.dart"] = "import 'package:flutter/material.dart'; class Screen2 extends StatelessWidget { const Screen2({super.key}); @override Widget build(BuildContext context) => const Text('Screen2'); }"
    files["lib/main.dart"] = "import 'package:flutter/material.dart'; import 'screen1.dart'; void main() => runApp(const MaterialApp(home: Screen1()));"

    zip_path = os.path.join(TEST_TEMP, "test3.zip")
    out_apk = os.path.join(TEST_TEMP, "test3-debug.apk")
    make_zip(zip_path, files)
    run_build_pipeline(zip_path, "debug-apk", out_apk)
    assert os.path.isfile(out_apk), "Multi-screen APK missing"


def test_4_images():
    """Test 4: Image assets in assets/images/."""
    files = base_valid_files()
    # 1x1 transparent PNG file
    png_bytes = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x03\x00\x05\xfe\x02\xfe\xa7\x96"\x60\x00\x00\x00\x00IEND\xaeB`\x82'
    files["assets/images/logo.png"] = png_bytes
    files["lib/main.dart"] = "import 'package:flutter/material.dart'; void main() => runApp(MaterialApp(home: Image.asset('assets/images/logo.png')));"

    zip_path = os.path.join(TEST_TEMP, "test4.zip")
    out_apk = os.path.join(TEST_TEMP, "test4-debug.apk")
    make_zip(zip_path, files)
    run_build_pipeline(zip_path, "debug-apk", out_apk)
    assert os.path.isfile(out_apk), "Image asset APK missing"


def test_5_fonts():
    """Test 5: Font assets."""
    files = base_valid_files()
    files["assets/fonts/sample.ttf"] = b'TTF_DUMMY_FONT_BYTES'
    zip_path = os.path.join(TEST_TEMP, "test5.zip")
    out_apk = os.path.join(TEST_TEMP, "test5-debug.apk")
    make_zip(zip_path, files)
    run_build_pipeline(zip_path, "debug-apk", out_apk)
    assert os.path.isfile(out_apk), "Font asset APK missing"


def test_6_audio():
    """Test 6: Audio assets."""
    files = base_valid_files()
    files["assets/sounds/bell.mp3"] = b'ID3_DUMMY_AUDIO_BYTES'
    zip_path = os.path.join(TEST_TEMP, "test6.zip")
    out_apk = os.path.join(TEST_TEMP, "test6-debug.apk")
    make_zip(zip_path, files)
    run_build_pipeline(zip_path, "debug-apk", out_apk)
    assert os.path.isfile(out_apk), "Audio asset APK missing"


def test_7_multiple_assets():
    """Test 7: Multiple nested assets."""
    files = base_valid_files()
    files["assets/images/bg.png"] = b'PNG'
    files["assets/sounds/click.wav"] = b'WAV'
    files["assets/fonts/custom.otf"] = b'OTF'
    files["assets/data/config.json"] = '{"key": "value"}'

    zip_path = os.path.join(TEST_TEMP, "test7.zip")
    out_apk = os.path.join(TEST_TEMP, "test7-debug.apk")
    make_zip(zip_path, files)
    run_build_pipeline(zip_path, "debug-apk", out_apk)
    assert os.path.isfile(out_apk), "Multiple asset APK missing"


def test_8_dependencies():
    """Test 8: Valid Flutter dependencies (e.g. path)."""
    files = base_valid_files()
    files["pubspec.yaml"] = "name: testapp\nversion: 1.0.0\nenvironment:\n  sdk: '>=3.0.0 <4.0.0'\ndependencies:\n  flutter:\n    sdk: flutter\n  path: ^1.9.0\n"
    files["lib/main.dart"] = "import 'package:flutter/material.dart'; import 'package:path/path.dart' as p; void main() => runApp(MaterialApp(home: Text(p.join('a', 'b'))));"

    zip_path = os.path.join(TEST_TEMP, "test8.zip")
    out_apk = os.path.join(TEST_TEMP, "test8-debug.apk")
    make_zip(zip_path, files)
    run_build_pipeline(zip_path, "debug-apk", out_apk)
    assert os.path.isfile(out_apk), "Dependencies APK missing"


def test_9_permissions():
    """Test 9: Android permissions injection."""
    files = base_valid_files()
    files["app.json"] = json.dumps({
        "name": "Permission App",
        "package": "com.forge.permapp",
        "version": "1.0.0",
        "versionCode": 1,
        "permissions": ["RECORD_AUDIO", "CAMERA", "ACCESS_FINE_LOCATION"]
    })

    zip_path = os.path.join(TEST_TEMP, "test9.zip")
    out_apk = os.path.join(TEST_TEMP, "test9-debug.apk")
    make_zip(zip_path, files)
    run_build_pipeline(zip_path, "debug-apk", out_apk)
    assert os.path.isfile(out_apk), "Permission test APK missing"


def test_10_app_name_package_version():
    """Test 10: Customized App name, package, version in app.json."""
    files = base_valid_files()
    files["app.json"] = json.dumps({
        "name": "Custom Forge App",
        "package": "com.custom.forgeapp",
        "version": "2.5.1",
        "versionCode": 42
    })

    zip_path = os.path.join(TEST_TEMP, "test10.zip")
    out_apk = os.path.join(TEST_TEMP, "test10-debug.apk")
    make_zip(zip_path, files)
    run_build_pipeline(zip_path, "debug-apk", out_apk)
    assert os.path.isfile(out_apk), "Custom Metadata APK missing"


def test_11_debug_apk():
    """Test 11: Debug APK build workflow."""
    zip_path = os.path.join(TEST_TEMP, "test11.zip")
    out_apk = os.path.join(TEST_TEMP, "app-debug.apk")
    make_zip(zip_path, base_valid_files())
    run_build_pipeline(zip_path, "debug-apk", out_apk)
    assert os.path.isfile(out_apk), "app-debug.apk missing"


def test_12_release_apk():
    """Test 12: Release APK build workflow."""
    zip_path = os.path.join(TEST_TEMP, "test12.zip")
    out_apk = os.path.join(TEST_TEMP, "app-release.apk")
    make_zip(zip_path, base_valid_files())
    run_build_pipeline(zip_path, "release-apk", out_apk)
    assert os.path.isfile(out_apk), "app-release.apk missing"


def test_13_release_aab():
    """Test 13: Release AAB build workflow."""
    zip_path = os.path.join(TEST_TEMP, "test13.zip")
    out_aab = os.path.join(TEST_TEMP, "app-release.aab")
    make_zip(zip_path, base_valid_files())
    run_build_pipeline(zip_path, "release-aab", out_aab)
    assert os.path.isfile(out_aab), "app-release.aab missing"


def test_14_signing_verification():
    """Test 14: Verification of signatures for Release APK and AAB."""
    rel_apk = os.path.join(TEST_TEMP, "app-release.apk")
    rel_aab = os.path.join(TEST_TEMP, "app-release.aab")
    assert verify_apk_signature(rel_apk), "APK signature verification failed"
    assert verify_aab_signature(rel_aab), "AAB signature verification failed"


def test_15_invalid_app_json():
    """Test 15: Invalid app.json raises error."""
    files = base_valid_files()
    files["app.json"] = "INVALID_JSON_CONTENT{"
    zip_path = os.path.join(TEST_TEMP, "test15.zip")
    make_zip(zip_path, files)
    try:
        run_build_pipeline(zip_path, "debug-apk", os.path.join(TEST_TEMP, "dummy.apk"))
        assert False, "Should have failed due to invalid app.json"
    except (ZIPValidationError, BuildPipelineError):
        pass


def test_16_invalid_pubspec_yaml():
    """Test 16: Invalid pubspec.yaml raises error."""
    files = base_valid_files()
    files["pubspec.yaml"] = "invalid: yaml: [tab failure\t"
    zip_path = os.path.join(TEST_TEMP, "test16.zip")
    make_zip(zip_path, files)
    try:
        run_build_pipeline(zip_path, "debug-apk", os.path.join(TEST_TEMP, "dummy.apk"))
        assert False, "Should have failed due to invalid pubspec.yaml"
    except (ZIPValidationError, BuildPipelineError):
        pass


def test_17_missing_main_dart():
    """Test 17: Missing main.dart raises error."""
    files = base_valid_files()
    del files["lib/main.dart"]
    zip_path = os.path.join(TEST_TEMP, "test17.zip")
    make_zip(zip_path, files)
    try:
        run_build_pipeline(zip_path, "debug-apk", os.path.join(TEST_TEMP, "dummy.apk"))
        assert False, "Should have failed due to missing main.dart"
    except (ZIPValidationError, BuildPipelineError):
        pass


def test_18_invalid_dependency():
    """Test 18: Forbidden unconstrained dependency version (+ or latest or any) raises error."""
    files = base_valid_files()
    files["pubspec.yaml"] = "name: testapp\nversion: 1.0.0\nenvironment:\n  sdk: '>=3.0.0 <4.0.0'\ndependencies:\n  flutter:\n    sdk: flutter\n  some_pkg: any\n"
    zip_path = os.path.join(TEST_TEMP, "test18.zip")
    make_zip(zip_path, files)
    try:
        run_build_pipeline(zip_path, "debug-apk", os.path.join(TEST_TEMP, "dummy.apk"))
        assert False, "Should have failed due to unconstrained 'any' dependency"
    except (ZIPValidationError, BuildPipelineError):
        pass


def test_19_forbidden_files_in_zip():
    """Test 19: Forbidden script or executable files in ZIP raises error."""
    files = base_valid_files()
    files["malicious.sh"] = "#!/bin/bash\necho hack"
    zip_path = os.path.join(TEST_TEMP, "test19.zip")
    make_zip(zip_path, files)
    try:
        run_build_pipeline(zip_path, "debug-apk", os.path.join(TEST_TEMP, "dummy.apk"))
        assert False, "Should have failed due to forbidden .sh file"
    except (ZIPValidationError, BuildPipelineError):
        pass


def test_20_path_traversal_attack():
    """Test 20: Path traversal in ZIP filename raises error."""
    zip_path = os.path.join(TEST_TEMP, "test20.zip")
    os.makedirs(os.path.dirname(zip_path), exist_ok=True)
    with zipfile.ZipFile(zip_path, 'w') as zf:
        zf.writestr("app.json", json.dumps({"name": "a", "package": "com.a.a", "version": "1.0.0", "versionCode": 1}))
        zf.writestr("pubspec.yaml", "name: a\nversion: 1.0.0\n")
        zf.writestr("lib/main.dart", "void main(){}")
        zf.writestr("../../../etc/passwd", "root:x:0:0:")

    try:
        run_build_pipeline(zip_path, "debug-apk", os.path.join(TEST_TEMP, "dummy.apk"))
        assert False, "Should have failed due to path traversal attack"
    except (ZIPValidationError, BuildPipelineError):
        pass


def test_21_empty_assets():
    """Test 21: Build succeeds when assets directory is empty."""
    files = base_valid_files()
    files["assets/.gitkeep"] = ""
    zip_path = os.path.join(TEST_TEMP, "test21.zip")
    out_apk = os.path.join(TEST_TEMP, "test21-debug.apk")
    make_zip(zip_path, files)
    run_build_pipeline(zip_path, "debug-apk", out_apk)
    assert os.path.isfile(out_apk), "Empty assets build failed"


def test_22_large_project():
    """Test 22: Large project with 50 generated Dart source files."""
    files = base_valid_files()
    main_imports = ["import 'package:flutter/material.dart';"]
    main_widgets = []
    for i in range(50):
        fname = f"lib/page_{i}.dart"
        files[fname] = f"import 'package:flutter/material.dart'; class Page{i} extends StatelessWidget {{ const Page{i}({{super.key}}); @override Widget build(BuildContext context) => const Text('Page {i}'); }}"
        main_imports.append(f"import 'page_{i}.dart';")
        main_widgets.append(f"const Page{i}(),")

    files["lib/main.dart"] = "\n".join(main_imports) + "\nvoid main() => runApp(MaterialApp(home: Column(children: [" + "".join(main_widgets) + "])));"

    zip_path = os.path.join(TEST_TEMP, "test22.zip")
    out_apk = os.path.join(TEST_TEMP, "test22-debug.apk")
    make_zip(zip_path, files)
    run_build_pipeline(zip_path, "debug-apk", out_apk)
    assert os.path.isfile(out_apk), "Large project build failed"


def test_23_repeated_builds():
    """Test 23: Consecutive reproducible builds run cleanly without interference."""
    zip_path = os.path.join(TEST_TEMP, "test23.zip")
    make_zip(zip_path, base_valid_files())

    for i in range(3):
        out_apk = os.path.join(TEST_TEMP, f"test23-run-{i}.apk")
        run_build_pipeline(zip_path, "debug-apk", out_apk)
        assert os.path.isfile(out_apk), f"Repeated build run {i} failed"


def main():
    if os.path.exists(TEST_TEMP):
        shutil.rmtree(TEST_TEMP)
    os.makedirs(TEST_TEMP, exist_ok=True)

    test_cases = [
        ("Test 1: Flutter Template Alone", test_1_flutter_template_alone),
        ("Test 2: Simple Flutter App", test_2_simple_flutter_app),
        ("Test 3: Multiple Screens", test_3_multiple_screens),
        ("Test 4: Images Asset Integration", test_4_images),
        ("Test 5: Fonts Asset Integration", test_5_fonts),
        ("Test 6: Audio Asset Integration", test_6_audio),
        ("Test 7: Multiple Assets Folders", test_7_multiple_assets),
        ("Test 8: Valid Dependencies Resolution", test_8_dependencies),
        ("Test 9: Android Permissions Injection", test_9_permissions),
        ("Test 10: App Name / Package / Version", test_10_app_name_package_version),
        ("Test 11: Debug APK Pipeline", test_11_debug_apk),
        ("Test 12: Release APK Pipeline", test_12_release_apk),
        ("Test 13: Release AAB Pipeline", test_13_release_aab),
        ("Test 14: Signing & Signature Verification", test_14_signing_verification),
        ("Test 15: Invalid app.json Handling", test_15_invalid_app_json),
        ("Test 16: Invalid pubspec.yaml Handling", test_16_invalid_pubspec_yaml),
        ("Test 17: Missing main.dart Handling", test_17_missing_main_dart),
        ("Test 18: Incompatible/Unconstrained Dependency Handling", test_18_invalid_dependency),
        ("Test 19: ZIP Containing Forbidden Executable Files", test_19_forbidden_files_in_zip),
        ("Test 20: Path Traversal Attack Prevention", test_20_path_traversal_attack),
        ("Test 21: Empty Assets Folder Handling", test_21_empty_assets),
        ("Test 22: Large Project Scale Test", test_22_large_project),
        ("Test 23: Repeated Consecutive Builds", test_23_repeated_builds),
    ]

    for name, func in test_cases:
        run_test(name, func)

    print("\n==================================================")
    print("FINAL TEST RESULTS SUMMARY")
    print("==================================================")
    print(f"Total Tests Run: {len(test_cases)}")
    print(f"Passed: {len(PASSED_TESTS)}")
    print(f"Failed: {len(FAILED_TESTS)}")

    if FAILED_TESTS:
        print("\nFailed Scenarios:")
        for fname, err in FAILED_TESTS:
            print(f"- {fname}: {err}")
        sys.exit(1)
    else:
        print("\nALL 23 TESTS PASSED SUCCESSFULLY!")
        # Cleanup test workspace artifacts
        if os.path.exists(TEST_TEMP):
            shutil.rmtree(TEST_TEMP)
        sys.exit(0)


if __name__ == "__main__":
    main()
