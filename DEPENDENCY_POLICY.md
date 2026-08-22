# Flutter Forge Dependency Policy

## Overview
Flutter Forge enforces strict safety and reproducibility rules for third-party dependencies supplied via `myapp.zip` (`pubspec.yaml`).

## Rules & Constraints

### 1. Fixed SDK Lock
- Incoming `pubspec.yaml` **MUST NOT** modify the `environment.sdk` or `environment.flutter` fields to incompatible ranges.
- The build engine overrides SDK environment definitions to match the fixed build lock (`Flutter 3.41.2`, `Dart 3.11.0`).

### 2. Forbidden & Unsafe Packages
- Native Gradle modification packages or packages attempting runtime binary generation are blocked.
- Unconstrained wildcard dependency versions (e.g. `path: any`, `foo: ^latest`, `bar: +`) are rejected during pre-build validation.

### 3. Incompatible Dependency Handling
- When an incoming `pubspec.yaml` specifies dependencies incompatible with Flutter `3.41.2`:
  - **The build engine IMMEDIATELY terminates execution.**
  - An explicit diagnostic log is emitted describing the conflict.
  - The build engine **NEVER** attempts to upgrade, downgrade, or change Flutter / AGP / Gradle versions to satisfy dependencies.

### 4. Asset & Plugin Integration Rules
- Standard Flutter packages (`provider`, `shared_preferences`, `http`, `flutter_bloc`, `audioplayers`, etc.) with standard plugin bindings are supported.
- Custom native `android/` directory injections inside `myapp.zip` are ignored or disallowed to prevent environment corruption.

## Updating Policies
- Core policy updates must be tested against the fixed Flutter Template before approval.
