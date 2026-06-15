# Cadux Pairing Daemon (`paird`)

A zero-typing LAN pairing system for [Cadux](https://github.com/cadux) — the
Flet-based chat frontend for Hermes Agent.

## Architecture

```
┌──────────────┐     LAN scan        ┌──────────────────┐
│              │  ──────────────────> │                  │
│   Cadux      │  GET /discover       │   paird daemon   │
│   (phone/    │                      │   (port 8643)    │
│    desktop)  │  POST /register      │                  │
│              │  <── session_id ─── │   Hermes AI      │
│              │                      │   calls          │
│   User says  │  ──"Pair with ─────> │   POST /initiate │
│   "Pair..."  │     cadux"           │   ──> returns    │
│              │                      │   correct_code   │
│   Cadux      │  GET /session/{id}   │                  │
│   polls      │  <── 6 codes + cfg ─ │                  │
│              │                      │                  │
│   User taps  │  (decrypts locally)  │                  │
│   the code   │  ✅ Connects         │                  │
└──────────────┘                      └──────────────────┘
                                               │
                                        Hermes AI tells
                                        user the code
```

## Files

| File | Purpose |
|------|---------|
| `server.py` | The aiohttp daemon — handles discovery, pairing sessions, web UI |
| `skills/cadux-pairing/SKILL.md` | Hermes skill definition (tells Hermes AI about paird) |
| `skills/cadux-pairing/scripts/paird_manager.py` | CLI tool to start/stop/status paird |
| `install.sh` | Linux/macOS installer |
| `install.ps1` | Windows installer |

## Quick Start

### On the Hermes server (just the daemon):

```bash
# From the cadux repo root
cd paird
CADUX_API_URL=http://localhost:8642 CADUX_SECRET_KEY=your-key-here uv run server.py
```

Then open `http://<server-ip>:8643/` on your browser to see the pairing UI.

### Install as a Hermes skill:

**Linux/macOS:**
```bash
cd paird
bash install.sh
```

**Windows (PowerShell):**
```powershell
cd paird
powershell -ExecutionPolicy Bypass -File install.ps1
```

### Verify installation:
```bash
python3 ~/.hermes/skills/cadux-pairing/scripts/paird_manager.py status
python3 ~/.hermes/skills/cadux-pairing/scripts/paird_manager.py start
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Web UI — shows all active pairing sessions |
| GET | `/discover` | JSON identity (LAN auto-discovery) |
| POST | `/register` | Cadux registers intent to pair → `{session_id}` |
| POST | `/initiate` | **Hermes AI calls this** → generates 6 codes, encrypts config → `{correct_code}` |
| GET | `/session/{id}` | Cadux polls for status → `{status, codes, config_encrypted, md5_sig}` |

### POST /register

Response:
```json
{
  "session_id": "a1b2c3d4-...",
  "status": "waiting"
}
```

### POST /initiate

No request body needed. Pairs with the most recent waiting session.

Response:
```json
{
  "correct_code": "K47",
  "session_id": "a1b2c3d4-..."
}
```

Error (no pending session):
```json
{"error": "No pending pairing request. Open Cadux first."}
```
Status: 404

### GET /session/{id}

While waiting:
```json
{"status": "waiting"}
```

When ready (Hermes has called /initiate):
```json
{
  "status": "ready",
  "codes": ["K47", "X2B", "M9Q", ...],
  "config_encrypted": "<base64>",
  "md5_sig": "<md5-of-plaintext>"
}
```
```

Session expired (404):
```json
{ "error": "session expired" }
```

## Pairing Flow

1. **Cadux auto-discovers** paird on the LAN via `GET /discover`
2. **Cadux calls** `POST /start` → gets 3 short alphanumeric codes
3. **Cadux shows** the 3 codes as tappable buttons
4. **Server operator** opens `http://<host>:8643/` in their browser — sees the **live code highlighted in red**, reads it aloud
5. **User** taps the matching code on Cadux
6. **Cadux POSTs** to `/confirm/<session>` with the chosen code
7. **If correct**: daemon encrypts the Hermes API config with that code and returns it → Cadux decrypts and auto-configures
8. **If wrong**: daemon returns 403 → Cadux shows "Wrong code — try another"

The visual verification (human sees both screens) is what proves the user is authorized to receive the API key.

## Security Notes

- The pairing code is a **visual verification channel** — someone must be able to see **both** the server operator's screen and the Cadux screen to intercept the pairing.
- The API key is encrypted in transit using XOR with a SHA-256 derived key, which means the key material never travels in plaintext.
- Pairing sessions expire after **120 seconds**.
- This is a **convenience layer for LAN development** — not a replacement for TLS or certificate-based auth in production.

## Configuration

The paird daemon needs two values to encrypt config for Cadux:

- `CADUX_API_URL` — The Hermes API URL (e.g., `http://localhost:8642`)
- `CADUX_SECRET_KEY` — The Hermes API key/token

These can be set via:
1. Environment variables
2. A `.env` file in the repo root
3. Hermes config (when installed as a skill, auto-detected)
