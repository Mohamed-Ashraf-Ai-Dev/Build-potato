# Build Versions Specification (Build Environment Lock)

| Component | Version | Notes / Constraint |
| :--- | :--- | :--- |
| **Flutter SDK** | `3.41.2` | Channel Stable |
| **Dart SDK** | `3.11.0` | Bundled with Flutter 3.41.2 |
| **Java / JDK** | `21` (OpenJDK 21.0.10) | Ubuntu 64-bit package |
| **Android SDK API** | `34` (Android 14) | Target SDK & Compile SDK |
| **Min SDK** | `21` (Android 5.0) | Minimum supported Android API |
| **Build Tools** | `34.0.0` | Android SDK Build-Tools |
| **Gradle** | `8.14` | Fixed Gradle wrapper |
| **AGP (Android Gradle Plugin)** | `8.11.1` | Fixed AGP version |
| **Kotlin** | `2.2.20` | Fixed Kotlin plugin version |

## Fixed Environment Directives
1. **Strict Version Immutability**: No incoming application (`myapp.zip`) is permitted to override, alter, or negotiate these versions.
2. **No Dynamic Floating Specs**: Disallowed terms in build scripts and dependencies include `latest`, `any`, `+`, `stable` wildcard references.
3. **Reproducibility Guarantee**: The Flutter template is compiled strictly against this defined toolchain.
