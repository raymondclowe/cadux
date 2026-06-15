# Cadux — Build & Deployment Guide

## Prerequisites

| Tool | Required For | Install |
|------|-------------|---------|
| **uv** | Dependency management, running desktop | `pip install uv` or [astral.sh](https://docs.astral.sh/uv/getting-started/installation/) |
| **Python 3.14+** | Runtime (match syntax, `|=` union) | Via `uv python install 3.14` |
| **flet** | APK builds, desktop packaging | `uv tool install flet-cli` (already in `pyproject.toml` as dep) |
| **Android SDK** | APK compilation | See [Android SDK setup](#android-sdk-setup) below |
| **JDK 17+** | Android Gradle builds | `winget install EclipseAdoptium.Temurin.17.JDK` or [Adoptium](https://adoptium.net/) |
| **Git** | Version tagging, GitHub releases | Bundled or `winget install Git.Git` |

### Android SDK Setup

`flet build apk` needs `ANDROID_HOME` or `ANDROID_SDK_ROOT` pointing at an SDK with at least:
- `platforms/android-34`
- `build-tools/34.0.0`
- `cmdline-tools/latest`

**Via Android Studio (recommended):**
1. Install [Android Studio](https://developer.android.com/studio)
2. Open SDK Manager → install API 34 platform + build-tools
3. Set environment variable: `ANDROID_HOME=%LOCALAPPDATA%\Android\Sdk`

**Via command-line tools only:**
```powershell
# Download cmdline-tools from https://developer.android.com/studio#command-line-tools-and-look
# Extract to e.g. C:\android-sdk
$env:ANDROID_HOME = "C:\android-sdk"
& "$env:ANDROID_HOME\cmdline-tools\latest\bin\sdkmanager.bat" `
    "platforms;android-34" "build-tools;34.0.0" "platform-tools"
```

Verify:
```powershell
& "$env:ANDROID_HOME\cmdline-tools\latest\bin\sdkmanager.bat" --list
```

---

## Desktop (Windows / Linux / macOS)

### Run for development

```bash
uv run python -m src.main
```

Or use the entry-point script:

```bash
uv run main.py
```

### Package as standalone executable

```bash
flet pack main.py --name cadux
```

Output lands in `dist/`. This bundles Python + dependencies into a single `.exe` (Windows), `.app` (macOS), or ELF binary (Linux).

---

## Android APK

### Quick build

```bash
flet build apk
```

The APK will be at `build/apk/`:
- Debug (no signing): `build/apk/debug/app-debug.apk`
- Release: `build/apk/release/app-release.apk`

### Build variants

```bash
# Debug APK (faster iteration, no signing)
flet build apk --build-type debug

# Release APK (optimized, must be signed)
flet build apk --build-type release

# Specify architecture
flet build apk --android-arch arm64-v8a      # modern 64-bit only (smaller APK)
flet build apk --android-arch armeabi-v7a    # legacy 32-bit
flet build apk --android-arch "arm64-v8a armeabi-v7a x86_64"  # multi-arch fat APK
```

### Signing the release APK

1. Generate a keystore (one-time):
   ```bash
   keytool -genkey -v -keystore cadux-release.keystore -alias cadux -keyalg RSA -keysize 2048 -validity 10000
   ```

2. Sign with `flet` (pass keystore props via env):
   ```bash
   $env:FLET_BUILD_KEYSTORE = "./cadux-release.keystore"
   $env:FLET_BUILD_KEYSTORE_PASSWORD = "your-password"
   $env:FLET_BUILD_KEY_ALIAS = "cadux"
   $env:FLET_BUILD_KEY_PASSWORD = "your-key-password"
   flet build apk --build-type release
   ```

### Inspect the APK

```bash
# Check APK info
& "$env:ANDROID_HOME\build-tools\34.0.0\aapt.exe" dump badging build/apk/release/app-release.apk

# SHA1 fingerprint (for GitHub release verification)
Get-FileHash build/apk/release/app-release.apk -Algorithm SHA1
```

---

## GitHub Releases

### Manual release (via CLI)

```bash
# 1. Tag the version
git tag v0.1.0
git push origin v0.1.0

# 2. Create release + upload APK via gh CLI
gh release create v0.1.0 `
  --title "Cadux v0.1.0" `
  --notes "Initial Android release." `
  build/apk/release/app-release.apk

# 3. Verify
gh release view v0.1.0
```

### Manual release (via GitHub Web UI)

1. Push a tag: `git tag v0.1.0 && git push origin v0.1.0`
2. Go to **Releases** → **Draft a new release**
3. Choose the tag, add title + notes
4. Drag `build/apk/release/app-release.apk` into the assets area
5. Click **Publish release**

### Automated release (GitHub Actions)

Create `.github/workflows/release.yml`:

```yaml
name: Build & Release APK

on:
  push:
    tags:
      - 'v*'

jobs:
  build-and-release:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.14'

      - name: Setup uv
        uses: astral-sh/setup-uv@v3

      - name: Setup Android SDK
        uses: android-actions/setup-android@v3
        with:
          api-level: 34
          build-tools: '34.0.0'

      - name: Install dependencies
        run: uv sync

      - name: Build APK
        run: uv run flet build apk --build-type release

      - name: Upload to Release
        uses: softprops/action-gh-release@v2
        with:
          files: build/apk/release/app-release.apk
```

Now every `git tag v*` push triggers a full build and attaches the APK to the release automatically.

---

## Quick Reference

| Task | Command |
|------|---------|
| Run desktop | `uv run python -m src.main` |
| Build debug APK | `flet build apk` |
| Build release APK | `flet build apk --build-type release` |
| Sign APK | Set `FLET_BUILD_*` env vars + `flet build apk --build-type release` |
| Create GitHub release | `gh release create v0.1.0 build/apk/release/app-release.apk` |
| APK SHA1 | `Get-FileHash build/apk/release/app-release.apk -Algorithm SHA1` |
