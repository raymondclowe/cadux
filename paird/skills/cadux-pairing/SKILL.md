---
description: "Cadux Pairing — LAN discovery and one-tap pairing for the Cadux Hermes client."
version: 2.0.0
author: Cadux
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [cadux, pairing, lan, discovery, hermes-client]
    category: productivity
    requires_toolsets: [terminal, http]
---

# Cadux Pairing Skill

Provides a **zero-typing pairing flow** between a Hermes server and the
Cadux mobile/desktop client. No QR codes, no long API keys to type on a phone.

## Two Pairing Methods

### Method A: Code Pairing (recommended — simplest)

The primary flow: Cadux shows a 4-character code, the user tells you the code,
you pass it to `/initiate`, and Cadux auto-connects.

1. User opens Cadux → taps "Start Code Pairing" → sees code like **K47M**
2. User tells you (Hermes): "Pair with cadux, code K47M"
3. **You call POST /initiate with the code** → paird encrypts config, marks ready
4. Cadux polls, decrypts, connects — the user sees "✅ Paired!"

### Method B: 6-Code LAN Scan (original flow)

1. Cadux scans the LAN and discovers paird on the Hermes host
2. Cadux registers a pairing session and shows "Ask Hermes to pair"
3. The user asks you (Hermes) to initiate pairing
4. **You call POST /initiate** on the paird daemon → 6 codes generated, config encrypted
5. The correct code is returned to you — tell the user which one to tap
6. User taps that code on Cadux → config decrypted locally, connection established

## How It Works

Two components work together:

### 1. paird daemon (`paird/server.py`)

A lightweight aiohttp web server on port **8643** that:
- Serves `GET /discover` for LAN auto-discovery
- Accepts `POST /register` — Cadux registers intent → returns session_id
- Accepts `POST /initiate` — **you (Hermes) call this** to trigger pairing → generates 6 codes, encrypts config, returns `correct_code`
- Serves `GET /session/{id}` — Cadux polls until status is "ready"
- Serves a web UI at `GET /` showing all codes (operator can see which is live)

### 2. Cadux client (`src/pairing.py` in the Cadux repo)

Discovers paird on the LAN, shows 6 codes, decrypts config locally when the user taps the correct one.

## Prerequisites

- Python 3.10+ with `aiohttp` installed
- The paird daemon (`paird/server.py`) available on this machine
- Cadux app installed on the device that will connect

## Script Path

```bash
PAIRD_MGR=~/.hermes/skills/cadux-pairing/scripts/paird_manager.py
```

## Commands

### start — Start the pairing daemon

```bash
python3 $PAIRD_MGR start
python3 $PAIRD_MGR start --port 8643
```

Reads Hermes API configuration automatically from:
1. `CADUX_API_URL` / `CADUX_SECRET_KEY` environment variables
2. `HERMES_API_URL` / `HERMES_API_KEY` environment variables
3. Hermes `.env` file (`~/.hermes/.env`)
4. Hermes gateway launch script env vars

Returns JSON:
```json
{"status": "started", "pid": 12345, "url": "http://<server-ip>:8643", "port": 8643}
```

### stop — Stop the pairing daemon

```bash
python3 $PAIRD_MGR stop
```

### status — Check if daemon is running

```bash
python3 $PAIRD_MGR status
```

Returns JSON:
```json
{"status": "running", "pid": 12345, "url": "http://0.0.0.0:8643", "port": 8643, "healthy": true}
```

Or if stopped:
```json
{"status": "stopped", "url": null, "port": 8643}
```

### restart — Restart the daemon

```bash
python3 $PAIRD_MGR restart
```

## API — Hermes-initiated Pairing Flow (YOU call /initiate)

When a Cadux user asks to pair, **YOU** are responsible for calling the `/initiate`
endpoint on paird.

### Endpoint

```
POST http://localhost:8643/initiate
```

### Code Pairing (Method A — use when user gives you a code)

If the user says "Pair with cadux, code K47M", pass the code in the body:

```bash
curl -X POST http://localhost:8643/initiate \
  -H "Content-Type: application/json" \
  -d '{"code": "K47M"}'
```

Response:
```json
{"correct_code": "K47M", "session_id": "a1b2c3d4-...", "status": "ready"}
```

Cadux will auto-detect and connect — no further action needed. Tell the user
"Paired — check your Cadux screen" and you're done.

### 6-Code Mode (Method B — no code provided)

If the user just says "Pair with cadux" without a code:

```bash
curl -X POST http://localhost:8643/initiate
```

Response:
```json
{"correct_code": "K47", "session_id": "a1b2c3d4-..."}
```

**Tell the user the code** — say: "Tap the code **K47** on your Cadux screen"

### Code Pairing Flow (Method A — step by step)

This is the simplest path. Use this whenever the user gives you a code.

1. **User opens Cadux → "Code Pair" tab → taps "Start Code Pairing"**  
   Cadux shows a 4-char code like **K47M** and says "Tell Hermes: Pair with cadux, code K47M"

2. **User tells you the code**  
   "Pair with cadux, code K47M"

3. **You start paird if needed:**
   ```bash
   python3 $PAIRD_MGR start
   ```

4. **You call POST /initiate with the code:**
   ```bash
   curl -X POST http://localhost:8643/initiate \
     -H "Content-Type: application/json" \
     -d '{"code": "K47M"}'
   ```
   → paird encrypts config, marks session ready

5. **Cadux auto-detects and connects** — no further steps.  
   Tell the user: "✅ Done — check your Cadux screen"

### 6-Code LAN Flow (Method B — step by step)

1. **User opens Cadux and taps "Find Server"**  
   Cadux scans the LAN and discovers paird. It registers a session and shows:
   > "Ask Hermes: Pair with cadux"

2. **User asks you to pair**  
   They say something like: "Pair with cadux" or "My Cadux is waiting"

3. **You start paird if needed:**
   ```bash
   python3 $PAIRD_MGR start
   ```

4. **You call POST /initiate:**
   ```bash
   curl -X POST http://localhost:8643/initiate
   ```
   Response:
   ```json
   {"correct_code": "K47", "session_id": "a1b2c3d4-..."}
   ```

5. **Tell the user the code**  
   Say: "Tap the code **K47** on your Cadux screen"

6. **User taps the code** → Cadux decrypts the config locally and connects.  
   You'll see in paird logs:
   ```
   Initiated (6-code mode) — session a1b2c3d4 codes=['K47', ...] (correct: K47)
   ```

7. **Confirm** — the user should see "✅ Paired!" on Cadux, and the chat UI appears.

### Important Notes

- **Code-pairing mode** (`/initiate` with `{"code": "K47M"}`): finds the session with that exact code. Used when the user gives you a code.
- **6-code mode** (`/initiate` with no body): pairs with the **most recent waiting** session. Used for LAN scan flow.
- If no session is waiting, you'll get `{"error": "No pending pairing request..."}` with HTTP 404.
- Sessions expire after 120 seconds.

## Troubleshooting

**Daemon won't start:**
```bash
python3 $PAIRD_MGR status
# Check: is something already on port 8643?
```

**Can't find Hermes config:**
Set the environment variables explicitly:
```bash
CADUX_API_URL=http://localhost:8642 CADUX_SECRET_KEY=your-key python3 $PAIRD_MGR start
```

**Cadux can't find the server:**
Make sure port 8643 is accessible from the client device (no firewall blocking).

**/initiate returns "No waiting session with code":**
The code doesn't match. Ask the user to read the code again — or have them restart Code Pairing in Cadux.

**Wrong code tapped:**
Cadux shows "Wrong code — try another". The user needs the code from `/initiate`.

## Logs

The daemon logs to:
```
~/.hermes/skills/cadux-pairing/paird.log
```

Check logs if the daemon starts but isn't responding:
```bash
tail -20 ~/.hermes/skills/cadux-pairing/paird.log
```

## Security Notes

- The pairing code is a visual verification channel — someone must be able to see **both** the server operator's screen and the Cadux screen to intercept the pairing.
- The API key is encrypted in transit using XOR with a SHA-256 derived key.
- Pairing sessions expire after 120 seconds.
- This is not designed to replace TLS or certificate-based auth for production deployments — it's a convenience layer for LAN development use.
