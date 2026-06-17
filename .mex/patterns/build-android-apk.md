---
name: build-android-apk
description: Building and signing the Android APK for distribution.
triggers:
  - "APK"
  - "build"
  - "android"
  - "release"
  - "deploy"
  - "flet build"
edges:
  - target: context/setup.md
    condition: when checking prerequisites or environment setup
  - target: context/stack.md
    condition: when checking Python version compatibility with Flet's Android build
last_updated: 2026-06-17
---

# Build Android APK

## Context

Cadux targets Android as the primary mobile platform. The APK is built using `flet build apk`,
which embeds Python 3.12.9 and all dependencies into a Flutter-based Android app.

Before starting, ensure prerequisites from `context/setup.md` are met: Android SDK with API 34,
build-tools 34.0.0, JDK 17+, and `ANDROID_HOME` set.

## Task: Build Debug APK

### Steps

1. Run the build:
   ```bash
   flet build apk
   ```
2. The APK lands at build/apk/debug/app-debug.apk.
3. Install on a device via USB or adb:
   ```bash
   adb install build/apk/debug/app-debug.apk
   ```

### Gotchas

- **First build downloads Python for Android**: Creates a build/flutter/build_python_3.12.9 directory on first build. This takes several minutes.
- **Flet uses Python 3.12.9 for Android** regardless of your local Python version. The `pyproject.toml` says `>=3.14` for desktop dev, but the APK embeds 3.12.9.
- **site-packages contains pre-built Android-native packages**: These are the compiled .so versions of flet, aiohttp, etc. for each architecture. Don't delete this directory.

## Task: Build Release APK

### Steps

1. Generate a keystore (one-time):
   ```bash
   keytool -genkey -v -keystore cadux-release.keystore -alias cadux -keyalg RSA -keysize 2048 -validity 10000
   ```
2. Set environment variables for signing:
   ```powershell
   $env:FLET_BUILD_KEYSTORE = "./cadux-release.keystore"
   $env:FLET_BUILD_KEYSTORE_PASSWORD = "your-password"
   $env:FLET_BUILD_KEY_ALIAS = "cadux"
   $env:FLET_BUILD_KEY_PASSWORD = "your-key-password"
   ```
3. Build:
   ```bash
   flet build apk --build-type release
   ```
4. The signed APK is at build/apk/release/app-release.apk.

### Gotchas

- **Never commit the keystore or passwords**: Add `*.keystore` to `.gitignore`.
- **Architecture-specific builds**: Use `--android-arch arm64-v8a` for a smaller APK targeting modern 64-bit devices only. The default builds for all architectures (arm64-v8a, armeabi-v7a, x86_64).
- **SHA1 verification**: After building, verify with PowerShell: Get-FileHash build/apk/release/app-release.apk -Algorithm SHA1. The build/apk/cadux.apk.sha1 file should be updated.

### Verify

- [ ] `flet build apk` completes without errors
- [ ] APK installs and launches on an Android device
- [ ] The Settings dialog appears on first launch (no stored config)
- [ ] After entering API URL + key, the status dot turns green
- [ ] Sending a message streams a response from Hermes

## Update Scaffold

- [ ] Update `.mex/ROUTER.md` "Current Project State" if APK build behavior changes
- [ ] Update `docs/build-and-deploy.md` if build commands or prerequisites change
- [ ] If this is a new task type without a pattern, create one in `.mex/patterns/` and add to `patterns/INDEX.md`
