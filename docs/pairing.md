# Cadux Pairing System

A zero-typing LAN discovery + visual verification pairing system for connecting
Cadux to a Hermes Agent server.

## High-Level Flow

```
┌─────────┐    1. LAN scan        ┌──────────────────┐
│  Cadux  │  ────────────────────> │   paird daemon    │
│ (phone) │  GET /discover         │  (port 8643 on   │
│         │                        │   Hermes host)   │
│         │    2. POST /register   │                  │
│         │  <── session_id ────  │                  │
│         │                        │                  │
│         │  "Ask Hermes to pair"  │                  │
│         │                        │                  │
│  User ──┼── "Pair with cadux" ──>│── Hermes AI ──> │
│         │                        │  3. POST /initiate│
│         │                        │  <── correct_code│
│         │                        │                  │
│         │  4. GET /session/{id}  │                  │
│         │  <── 6 codes + config ─│                  │
│         │                        │                  │
│         │  5. User taps code ───>│  (decrypted      │
│         │     (local XOR decrypt)│   locally)       │
│         │                        │                  │
│         │  6. ✅ Auto-connects   │                  │
└─────────┘                        └──────────────────┘
```

## Components

### 1. `paird/server.py` — The daemon

An aiohttp web server that runs on the Hermes host. It:
- Listens on port 8643 (configurable via `PAIRD_PORT`)
- Serves `GET /discover` for LAN auto-discovery
- Accepts `POST /register` — Cadux registers intent to pair
- Accepts `POST /initiate` — **Hermes AI calls this** to trigger pairing
- Serves `GET /session/{id}` — Cadux polls for session state
- Serves a web UI at `GET /` showing all pending sessions

### 2. `src/pairing.py` — The Cadux client

Used by the Cadux app to:
- `scan(timeout)` — probe the local subnet for paird daemons
- `PairingSession(url)` — manage a pairing session
- `session.register()` — register intent to pair
- `session.poll()` — wait for Hermes to call /initiate
- `session.try_code(code)` — XOR-decrypt config locally, verify MD5

### 3. `paird/skills/cadux-pairing/` — The Hermes skill

A Hermes skill that tells the Hermes AI how to:
- Start/stop/status the paird daemon
- Call `POST /initiate` when a user asks to pair
- Tell the user which code to tap

Includes:
- `SKILL.md` — Skill definition (YAML frontmatter + markdown docs)
- `scripts/paird_manager.py` — CLI tool (`start`, `stop`, `status`, `restart`)

## Installation on a Hermes Server

**Prerequisites:** Python 3.10+, `aiohttp` installed.

### Option 1: Install script (recommended)

```bash
# From the cadux repo
cd paird
bash install.sh         # Linux/macOS
# or
powershell -File install.ps1   # Windows
```

### Option 2: Manual install

```bash
# Copy to Hermes skills directory
SKILL_DIR="$HOME/.hermes/skills/cadux-pairing"
mkdir -p "$SKILL_DIR/scripts"

cp paird/skills/cadux-pairing/SKILL.md "$SKILL_DIR/"
cp paird/skills/cadux-pairing/scripts/paird_manager.py "$SKILL_DIR/scripts/"
cp paird/server.py "$SKILL_DIR/"
pip install aiohttp

# Verify
python3 "$SKILL_DIR/scripts/paird_manager.py" status
```

### Option 3: Standalone (without Hermes)

Just run the daemon directly:
```bash
cd cadux
CADUX_API_URL=http://localhost:8642 CADUX_SECRET_KEY=your-key uv run paird/server.py
```

## Pairing Flow (End-User View)

1. **Open Cadux** → tap "🔍 Find Server" (banner) or Settings → "Find Server"
2. Cadux scans the LAN (progress bar visible), discovers paird on port 8643
3. Cadux registers a session and shows: **"Ask Hermes: Pair with cadux"**
4. **You tell Hermes** "Pair with cadux" or "My Cadux is waiting"
5. **Hermes AI calls** `POST /initiate` on paird, gets the correct code back
6. **Hermes tells you** the code — e.g. "Tap **K47** on your Cadux screen"
7. **You tap that code** on Cadux → config decrypts locally, connection established
8. ✅ Cadux shows "Paired!" and the chat UI appears

The human-in-the-loop verification ensures only an authorized person (who can
talk to both Hermes and Cadux) gets the API key.

## Security Properties

| Property | How It's Achieved |
|----------|-------------------|
| No plaintext API key on wire | XOR + SHA-256 encryption |
| Human verification | Code comes from Hermes AI, user confirms visually |
| Short-lived sessions | Sessions expire after 120s |
| No replay | Single-use session, codes are one-shot |
| Familiar UX | Same "confirm on another device" pattern as Microsoft/GitHub |

## Development

The pairing system lives in the `paird/` directory:
```
paird/
├── README.md                    # Quick-start docs
├── server.py                    # The daemon
├── install.sh                   # Linux/macOS installer
├── install.ps1                  # Windows installer
└── skills/
    └── cadux-pairing/
        ├── SKILL.md             # Hermes skill definition
        └── scripts/
            ├── __init__.py
            └── paird_manager.py # Hermes tool to start/stop/status
```

## Future Improvements

- **mDNS discovery** — supplement LAN scan with Zeroconf/Bonjour for faster discovery
- **Persistent sessions** — allow re-pairing without re-scanning
- **TLS support** — optional HTTPS for the daemon
- **Pairing confirmation callback** — Hermes calls Cadux back after successful pairing
