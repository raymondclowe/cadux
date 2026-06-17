---
name: stack
description: Technology stack, library choices, and the reasoning behind them. Load when working with specific technologies or making decisions about libraries and tools.
triggers:
  - "library"
  - "package"
  - "dependency"
  - "which tool"
  - "technology"
edges:
  - target: context/decisions.md
    condition: when the reasoning behind a tech choice is needed
  - target: context/conventions.md
    condition: when understanding how to use a technology in this codebase
last_updated: 2026-06-17
---

# Stack

## Core Technologies

- **Python 3.14+** — primary language (uses `|=` union syntax and other 3.14 features)
- **Flet ≥0.85.3** — UI framework, cross-platform (Android, Windows, macOS, Linux, web). All UI is built declaratively with Flet widgets. The app runs via `ft.app(target=main)` or `ft.run(main=main)`.
- **aiohttp ≥3.9.0** — async HTTP client for REST API calls and SSE streaming. Not aiohttp server — client-side only.
- **uv** — package manager and runner. All scripts run via `uv run`, dependencies added via `uv add`.

## Key Libraries

- **Flet** (not Kivy, not Tkinter, not a web SPA) — chosen for cross-platform Android + desktop from a single Python codebase with Material Design widgets built in.
- **aiohttp** (not httpx, not requests) — async HTTP with SSE streaming support via `resp.content.readline()`. The `TCPConnector(force_close=True)` is used to avoid connection pool issues on reconnect.
- **python-dotenv ≥1.2.2** — loads `.env` files for local development convenience. Production config should come from environment variables or profiles.
- **stdlib `hashlib` + `base64`** — used for XOR+SHA256 encryption in the pairing flow (not a cryptography library — intentionally simple for the short-lived PIN exchange).
- **stdlib `socket` + `asyncio`** — UDP broadcast discovery for finding paird on the LAN. No external discovery library needed.
- **stdlib `dataclasses`** — the `Profile` dataclass is the only data model. No ORM, no Pydantic.

## What We Deliberately Do NOT Use

- **No WebSockets** — despite `ws_client.py` filename, all communication is REST + SSE. The WebSocket approach in the original spec was replaced.
- **No cryptography library** — the pairing XOR encryption is intentionally simple (SHA256-derived key, single-use PIN). No need for Fernet, NaCl, or TLS at the pairing layer.
- **No ORM or database** — profiles use Flet's `client_storage` (JSON in platform key-value store). No SQLite, no SQLAlchemy.
- **No Pydantic** — the single `Profile` dataclass is simple enough. No validation layer needed.
- **No state management library** — state lives in `page.session.store` (in-memory per-session) and `page.client_storage` (persisted). No Redux, no Riverpod.

## Version Constraints

- **Python ≥3.14** — the codebase uses the `|=` union operator for `dict` merging (`body | {"error": ...}`) which requires 3.9+, but the `pyproject.toml` pins `>=3.14`. Flet's Android build bundles Python 3.12.9 (see the build/flutter/build_python_3.12.9 directory after first build).
- **Flet ≥0.85.3** — earlier versions may lack `page.run_task()`, `can_reveal_password`, or the specific `ft.Colors` constants used throughout.
