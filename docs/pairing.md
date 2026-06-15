# Cadux Pairing System

A zero-typing LAN discovery + visual verification pairing system for connecting
Cadux to a Hermes Agent server.

## High-Level Flow

```
┌─────────┐    1. LAN scan     ┌──────────────────┐
│  Cadux  │ ─────────────────> │   paird daemon    │
│ (phone) │  GET /discover     │  (port 8643 on   │
│         │                    │   Hermes host)   │
│         │   2. POST /start   │                  │
│         │ <── 3 codes ────  │                  │
│         │                    │                  │
│         │   3. Shows codes   │  Web UI shows    │
│         │   4. User taps one │  live code       │
│         │   ───────────────> │  highlighted     │
│         │   POST /confirm    │                  │
│         │ <── config ─────  │  5. Encrypts     │
│         │                    │     config with  │
│         │  6. Auto-connects  │     that code    │
└─────────┘                    └──────────────────┘
```

## Components

### 1. `paird/server.py` — The daemon

An aiohttp web server that runs on the Hermes host. It:
- Listens on port 8643 (configurable via `PAIRD_PORT`)
- Serves `GET /discover` for LAN auto-discovery
- Accepts `POST /start` to create pairing sessions (returns 3 codes)
- Accepts `POST /confirm/<session>` to verify codes and return encrypted config
- Serves a web UI at `GET /` showing which code is "live" (highlighted in red)

### 2. `src/pairing.py` — The Cadux client

Used by the Cadux app to:
- `scan(timeout)` — probe the local subnet for paird daemons
- `PairingSession(url)` — manage a pairing session
- `session.start()` — get 3 candidate codes
- `session.confirm(code)` — send user's choice to daemon, decrypt config if correct

### 3. `paird/skills/cadux-pairing/` — The Hermes skill

A Hermes skill that tells the Hermes AI how to:
- Start/stop/status the paird daemon
- Help users through the pairing flow

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

1. **Open Cadux** → tap the hamburger menu → "Find Server"
2. Cadux scans the LAN and finds the Hermes host
3. **3 tappable code buttons** appear on screen (e.g., `K47`, `X2B`, `M9Q`)
4. **Server operator** opens `http://<hermes-ip>:8643/` in their browser
5. Web UI shows one code **highlighted in red** — the operator reads it aloud
6. **User taps the matching code** on Cadux
7. ✅ If correct: Cadux shows "Connected!" and auto-configures
8. ❌ If wrong: Cadux shows "Wrong code — try another"

The human-in-the-loop visual verification is what proves the user is authorized.
Someone must be able to see **both** the server operator's screen AND the
Cadux screen to intercept the pairing.

## Security Properties

| Property | How It's Achieved |
|----------|-------------------|
| No plaintext API key on wire | XOR + SHA-256 encryption |
| Visual verification | Live code only visible on server operator's screen |
| Short-lived sessions | Sessions expire after 120s |
| No replay | Single-use session, code verified server-side |
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
- **Hermes skill integration** — have the Hermes agent generate one-time pairing URLs on demand
