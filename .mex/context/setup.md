---
name: setup
description: Dev environment setup and commands. Load when setting up the project for the first time or when environment issues arise.
triggers:
  - "setup"
  - "install"
  - "environment"
  - "getting started"
  - "how do I run"
  - "local development"
edges:
  - target: context/stack.md
    condition: when specific technology versions or library details are needed
  - target: context/architecture.md
    condition: when understanding how components connect during setup
  - target: context/pairing.md
    condition: when setting up the pairing daemon or troubleshooting pairing issues
last_updated: 2026-06-17
---

# Setup

## Prerequisites

- **uv** — package manager and runner. Install via `pip install uv` or from [astral.sh](https://docs.astral.sh/uv/getting-started/installation/)
- **Python 3.14+** — install via `uv python install 3.14`
- **Android SDK + JDK 17+** (optional, only for APK builds) — see `docs/build-and-deploy.md` for Android SDK setup

## First-time Setup

1. Clone the repo: git clone https://github.com/raymondclowe/cadux  then cd cadux
2. Install dependencies: `uv sync`
3. (Optional) Create `.env` file with `CADUX_API_URL` and `CADUX_SECRET_KEY` for zero-config launch
4. Run: uv run main.py
5. If no config is present, the Settings dialog appears on first launch — enter your Hermes API URL and secret key

## Environment Variables

- `CADUX_API_URL` (optional) — Hermes API base URL (e.g., `http://192.168.0.83:8642`). Used if no profile is active.
- `CADUX_SECRET_KEY` (optional) — Hermes API bearer token. Used if no profile is active.
- Both can also be set in a `.env` file at the project root (loaded via `python-dotenv`).
- If neither env vars nor `.env` are set, the Settings dialog prompts on first launch and saves to a profile.

## Common Commands

- uv run main.py — run the desktop app (dev mode)
- uv sync — install/update all dependencies
- uv add <package> — add a new dependency
- uv run --with ruff ruff check <file> — lint a Python file (ruff not in project deps)
- flet build apk — build Android APK (requires Android SDK + JDK 17+)
- flet build apk --build-type release — build release-signed APK
- flet pack main.py --name cadux — package as standalone desktop executable
- uv run python -m src.main — alternative run command (uses module path)

## Common Issues

**"No module named flet" after clone:** Run `uv sync` — dependencies are not auto-installed on clone.
**Settings dialog keeps reappearing:** The API URL or secret key is empty/missing. Check that both fields are filled before saving, or set `CADUX_API_URL` and `CADUX_SECRET_KEY` in `.env`.
**Status dot stays grey:** The REST listener only starts when config is present. Ensure a profile is active or env vars are set, then tap "Reconnect" in the drawer.
**SSE stream hangs mid-response:** The Hermes server may have dropped the connection. Tap "Reconnect" in the drawer to restart the listener. The `TCPConnector(force_close=True)` setting helps but is not a guarantee.
**Android build fails with SDK errors:** Ensure `ANDROID_HOME` is set and the API 34 platform along with build-tools 34.0.0 are installed. See docs/build-and-deploy.md.
