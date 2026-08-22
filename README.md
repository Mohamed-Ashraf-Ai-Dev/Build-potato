# Flutter Forge — Flutter APK/AAB Build Factory

Flutter Forge is a secure, isolated, and reproducible build engine for compiling AI-generated Flutter apps into signed Android APKs and AABs.

## Architecture

```
AI Output (myapp.zip)
       │
       ▼
  Build Engine (Security Validation & Verification)
       │
       ▼
 Fixed Template Injection (Flutter 3.41.2 / AGP 8.11.1 / Gradle 8.14)
       │
       ▼
 Signing Engine (Keystore Generation & apksigner)
       │
       ▼
 Signed Artifact (app-debug.apk / app-release.apk / app-release.aab)
```

## Workflows
- `build-debug-apk.yml`
- `build-release-apk.yml`
- `build-release-aab.yml`

## Environment Lock
See [BUILD_VERSIONS.md](./BUILD_VERSIONS.md) for detailed version matrices.
See [DEPENDENCY_POLICY.md](./DEPENDENCY_POLICY.md) for package handling rules.
