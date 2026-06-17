---
name: architecture
description: How the major pieces of this project connect and flow. Load when working on system design, integrations, or understanding how components interact.
triggers:
  - "architecture"
  - "system design"
  - "how does X connect to Y"
  - "integration"
  - "flow"
edges:
  - target: context/stack.md
    condition: when specific technology details are needed
  - target: context/decisions.md
    condition: when understanding why the architecture is structured this way
  - target: context/pairing.md
    condition: when working with the pairing flow, LAN discovery, or paird daemon
last_updated: 2026-06-17
---

# Architecture

## System Overview

Cadux is a chat client (Android APK + desktop) that connects to a Hermes Agent Gateway
via its REST API with SSE streaming. The user sends messages from a Flet-based UI,
which are dispatched as HTTP POST requests to `/api/sessions/{id}/chat/stream`.
Responses stream back as SSE events (`assistant.delta`, `assistant.completed`,
`run.completed`) and are rendered token-by-token into message bubbles.

Configuration is resolved from: environment variables → `.env` file → session store.
Multi-profile support allows switching between different Hermes instances without
re-entering credentials. Optional PIN-based pairing discovers a local `paird` daemon
via UDP broadcast, registers with a 4-char PIN, and receives encrypted credentials.

## Key Components

- **`src/main.py`** — App entry point, builds the Flet page (app bar, drawer, layout, responsive padding). Orchestrates profile loading, config resolution, and the REST listener lifecycle. Depends on all other `src/` modules.
- **`src/ws_client.py`** — REST API client using `aiohttp`. Manages the persistent HTTP session, polls `/api/sessions` every 5s, activates sessions, sends messages via SSE streaming, and handles session CRUD. The file is named `ws_client` for historical reasons but uses REST+SSE, not WebSockets.
- **`src/chat_ui.py`** — Pure UI widgets: message bubbles, delta streaming append, PIN entry boxes, input area, empty-state placeholder, session chip. No network logic.
- **`src/config.py`** — Resolves `api_url` and `secret_key` from env → `.env` → `page.session.store`. Returns `None` if not configured.
- **`src/profiles.py`** — Multi-profile CRUD persisted to `page.client_storage`. Each `Profile` stores `id`, `name`, `api_url`, `secret_key`, and optional `active_session_id`.
- **`src/pairing.py`** — LAN discovery via UDP broadcast, PIN registration with `paird`, XOR+SHA256 config decryption. See `context/pairing.md` for full flow.
- **`paird/server.py`** — Ephemeral pairing daemon that runs on the Hermes host. Listens for UDP discovery pings and serves HTTP `/register` for PIN-based credential exchange. Not part of the Cadux client — runs on the server side.

## External Dependencies

- **Hermes Agent Gateway REST API** — The backend this client connects to. Endpoints used: `GET /api/sessions`, `POST /api/sessions`, `DELETE /api/sessions/{id}`, `GET /api/sessions/{id}/messages`, `POST /api/sessions/{id}/chat/stream` (SSE). Auth via `Bearer` token in the `Authorization` header.
- **paird (Pairing Daemon)** — Ephemeral server on the Hermes host (port 8643 HTTP, port 8642 UDP). Used only during initial setup for PIN-based credential exchange. Not needed after pairing completes.
- **Flet** — The UI framework (Material Design, cross-platform). All UI is built with Flet widgets (`ft.Page`, `ft.Column`, `ft.Container`, etc.). The app uses `page.run_task()` for all async operations and `page.client_storage` for profile persistence.

## What Does NOT Exist Here

- No WebSocket connection — despite the filename `ws_client.py`, all communication is REST + SSE over HTTP. The WebSocket-based architecture in `docs/spec.md` was superseded by the REST API approach.
- No local database — profiles are persisted in Flet's `page.client_storage` (key-value), not SQLite or any other database.
- No authentication or user management — identity is handled entirely by the Hermes backend via the Bearer token. Cadux is a stateless client.
- No message persistence on the client — chat history is loaded from the Hermes server on session activation, not stored locally.
- No offline mode — the app requires a live connection to the Hermes API at all times.
