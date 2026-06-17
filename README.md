# Instructions for Hermes

When a user asks you to install Cadux, follow these steps in order.

## Step 1 — Download the pairing daemon

Download this file and save it as `paird/server.py` in your workspace:

```
https://raw.githubusercontent.com/raymondclowe/cadux/main/paird/server.py
```

Make sure the directory `paird/` exists before saving.

## Step 2 — Download the skill instructions

Download this file and save it as `docs/pairing.md` in your workspace:

```
https://raw.githubusercontent.com/raymondclowe/cadux/main/docs/pairing.md
```

## Step 3 — Pair the phone

Tell the user to open Cadux on their phone and tap **Find Hermes**. Cadux will discover your pairing daemon on the LAN and auto-connect. No PIN or code entry needed.

If the user asks for a manual option, tell them the LAN IP where paird is running. The **Find Hermes** button will also show a manual IP entry if auto-discovery fails.

---

# Instructions for Humans

Say this to Hermes:

> **Hey Hermes, install Cadux on my phone from https://github.com/raymondclowe/cadux/**

Then follow Hermes's instructions to download the APK onto your phone and install it.

Once installed, open Cadux and tap **Find Hermes** — it will find the pairing daemon on your LAN and connect automatically.

---

# Cadux /kəˈdʌks/

> The legendary winged staff carried by the messenger god Hermes.

A fast, lightweight Android (and desktop) client for the [Hermes Agent Gateway](https://github.com/NousResearch/hermes-agent). Connects directly to a Hermes backend via its REST API with SSE streaming.

## Quick Start (Desktop)

```bash
# Clone
git clone https://github.com/raymondclowe/cadux.git
cd cadux

# Install
uv sync

# Run
uv run main.py
```

If no config is present, the Settings dialog will appear on first launch.

## Architecture

```
┌─────────────────────────────────────┐
│  Android / Desktop                  │
│  ┌──────────────────────────────┐   │
│  │  Cadux (Flet UI)             │   │
│  │  REST API + SSE streaming    │   │
│  │  Bearer token auth           │   │
│  └──────────────┬───────────────┘   │
└─────────────────┼───────────────────┘
                  │ HTTP (LAN or internet)
┌─────────────────┼───────────────────┐
│  Hermes Server  │                   │
│  REST API       │                   │
│  /api/sessions  │                   │
│  /api/.../chat/ │                   │
│  stream (SSE)   │                   │
└─────────────────────────────────────┘
```

## Configuration

Config is resolved in this order (first found wins):
1. Environment variables (`CADUX_API_URL`, `CADUX_SECRET_KEY`)
2. `.env` file in project root
3. Flet `client_storage` (saved from profiles or Settings dialog)
4. PIN-based pairing via [`paird/`](paird/) (automatic config delivery)

## Project Structure

```
cadux/
├── src/
│   ├── main.py              # App entry, layout, drawer, profile mgmt
│   ├── config.py            # Config loading (env → .env → storage)
│   ├── chat_ui.py           # Chat bubbles, streaming, session chips
│   ├── ws_client.py         # Hermes REST API + SSE streaming
│   ├── pairing.py           # UDP discovery, PIN registration, decrypt
│   └── profiles.py          # Multi-profile CRUD + persistence
├── paird/
│   └── server.py            # Ephemeral pairing daemon (via Hermes skill)
├── docs/
│   ├── pairing.md           # Hermes skill instructions for pairing
│   ├── hermes-sse-format.md # SSE event format reference
│   ├── spec.md              # Component specification
│   ├── plan.md              # Implementation plan
│   └── build-and-deploy.md  # Build, sign, release & CI/CD guide
├── pyproject.toml           # Project metadata & dependencies
└── README.md
```

## Features

- **Streaming chat UI** — real-time token rendering via SSE `assistant.delta` events
- **Session management** — list, switch, and create Hermes sessions
- **Multi-profile** — save multiple Hermes connections, switch at runtime
- **PIN pairing** — zero-config setup: Hermes gives you a 4-letter code, Cadux auto-connects
- **Auto-reconnect** — polls sessions every 5s, reconnects on failure
- **Responsive** — adapts for mobile, tablet, and desktop
- **Dark/Light mode** — follows system theme

## License

MIT

