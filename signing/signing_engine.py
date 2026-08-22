#!/usr/bin/env python3
"""
Flutter Forge - Independent Signing Engine.
Generates temporary keystores, signs Release APK and Release AAB, and verifies signatures.
Zero credentials printed to logs or committed to git.
"""

import argparse
import os
import shutil
import subprocess
import tempfile


class SigningEngineError(Exception):
    pass


def run_command(cmd, log_output=True, sensitive=False):
    """Executes bash commands safely without printing sensitive passwords to output."""
    if not sensitive and log_output:
        print(f"Running: {' '.join(cmd)}")

    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        err_msg = res.stderr.strip() if res.stderr else res.stdout.strip()
        if sensitive:
            # Mask sensitive values before printing err_msg for debugging safety
            masked_err = err_msg
            for i, word in enumerate(cmd):
                if word in ("-storepass", "-keypass", "--ks-pass", "--key-pass") and i + 1 < len(cmd):
                    val = cmd[i + 1]
                    if val.startswith("pass:"):
                        val = val[5:]
                    if val:
                        masked_err = masked_err.replace(val, "******")
                elif word.startswith("pass:"):
                    masked_err = masked_err.replace(word[5:], "******")
            err_msg = f"Command failed: {masked_err}"
        raise SigningEngineError(f"Execution failed: {err_msg}")
    return res.stdout


def generate_keystore(keystore_path: str, alias: str, keypass: str, storepass: str, dname: str = "CN=FlutterForge"):
    """Generates a temporary keystore using keytool."""
    cmd = [
        "keytool", "-genkeypair", "-v",
        "-keystore", keystore_path,
        "-alias", alias,
        "-keyalg", "RSA",
        "-keysize", "2048",
        "-validity", "10000",
        "-storepass", storepass,
        "-keypass", keypass,
        "-dname", dname
    ]
    run_command(cmd, sensitive=True)
    if not os.path.isfile(keystore_path):
        raise SigningEngineError("Failed to generate keystore file")


def find_apksigner():
    """Finds apksigner executable in system or Android SDK build-tools."""
    system_apk = shutil.which("apksigner")
    if system_apk:
        return system_apk

    android_home = os.environ.get("ANDROID_HOME", "/opt/android-sdk")
    build_tools_dir = os.path.join(android_home, "build-tools")
    if os.path.exists(build_tools_dir):
        versions = sorted(os.listdir(build_tools_dir), reverse=True)
        for v in versions:
            candidate = os.path.join(build_tools_dir, v, "apksigner")
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                return candidate
    raise SigningEngineError("apksigner not found in system PATH or Android SDK build-tools")


def find_zipalign():
    """Finds zipalign executable in system or Android SDK build-tools."""
    system_zip = shutil.which("zipalign")
    if system_zip:
        return system_zip

    android_home = os.environ.get("ANDROID_HOME", "/opt/android-sdk")
    build_tools_dir = os.path.join(android_home, "build-tools")
    if os.path.exists(build_tools_dir):
        versions = sorted(os.listdir(build_tools_dir), reverse=True)
        for v in versions:
            candidate = os.path.join(build_tools_dir, v, "zipalign")
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                return candidate
    return None  # Optional if APK is already aligned by Gradle


def sign_apk(apk_path: str, keystore_path: str, alias: str, keypass: str, storepass: str, output_path: str):
    """Signs an APK using apksigner."""
    apksigner = find_apksigner()
    cmd = [
        apksigner, "sign",
        "--ks", keystore_path,
        "--ks-key-alias", alias,
        "--ks-pass", f"pass:{storepass}",
        "--key-pass", f"pass:{keypass}",
        "--out", output_path,
        apk_path
    ]
    run_command(cmd, sensitive=True)
    print(f"APK successfully signed: {output_path}")


def sign_aab(aab_path: str, keystore_path: str, alias: str, keypass: str, storepass: str, output_path: str):
    """Signs an AAB bundle using jarsigner."""
    jarsigner = shutil.which("jarsigner")
    if not jarsigner:
        raise SigningEngineError("jarsigner tool not found in PATH")

    if aab_path != output_path:
        shutil.copyfile(aab_path, output_path)

    cmd = [
        jarsigner,
        "-keystore", keystore_path,
        "-storepass", storepass,
        "-keypass", keypass,
        "-sigalg", "SHA256withRSA",
        "-digestalg", "SHA-256",
        output_path,
        alias
    ]
    run_command(cmd, sensitive=True)
    print(f"AAB successfully signed: {output_path}")


def verify_apk_signature(apk_path: str) -> bool:
    """Verifies APK signature with apksigner."""
    apksigner = find_apksigner()
    cmd = [apksigner, "verify", "--verbose", apk_path]
    try:
        out = run_command(cmd, log_output=False)
        if "Verified" in out or "SHA-256 digest" in out or "Scheme v2" in out:
            print(f"APK signature verification passed for: {apk_path}")
            return True
        return False
    except Exception as e:
        print(f"APK signature verification failed: {e}")
        return False


def verify_aab_signature(aab_path: str) -> bool:
    """Verifies AAB signature with jarsigner."""
    jarsigner = shutil.which("jarsigner")
    if not jarsigner:
        raise SigningEngineError("jarsigner tool not found")

    cmd = [jarsigner, "-verify", "-verbose", "-certs", aab_path]
    try:
        out = run_command(cmd, log_output=False)
        if "jar verified" in out:
            print(f"AAB signature verification passed for: {aab_path}")
            return True
        return False
    except Exception as e:
        print(f"AAB signature verification failed: {e}")
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Flutter Forge Signing Engine")
    parser.add_argument("--action", choices=["genkey", "sign-apk", "sign-aab", "verify-apk", "verify-aab"], required=True)
    parser.add_argument("--input", required=False)
    parser.add_argument("--output", required=False)
    parser.add_argument("--keystore", required=False)
    parser.add_argument("--alias", default="upload")
    parser.add_argument("--storepass", default="forge_secret_storepass")
    parser.add_argument("--keypass", default="forge_secret_keypass")

    args = parser.parse_args()

    if args.action == "genkey":
        generate_keystore(args.keystore, args.alias, args.keypass, args.storepass)
    elif args.action == "sign-apk":
        sign_apk(args.input, args.keystore, args.alias, args.keypass, args.storepass, args.output)
    elif args.action == "sign-aab":
        sign_aab(args.input, args.keystore, args.alias, args.keypass, args.storepass, args.output)
    elif args.action == "verify-apk":
        if not verify_apk_signature(args.input):
            exit(1)
    elif args.action == "verify-aab":
        if not verify_aab_signature(args.input):
            exit(1)
