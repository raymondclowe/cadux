---
description: "Cadux Pairing — LAN discovery and one-tap pairing for the Cadux Hermes client."
version: 1.0.0
author: Cadux
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [cadux, pairing, lan, discovery, hermes-client]
    category: productivity
    requires_toolsets: [terminal]
---

# Cadux Pairing Skill

Provides a **zero-typing LAN pairing flow** between a Hermes server and the
Cadux mobile/desktop client. No QR codes, no long API keys to type on a phone.

## What This Solves

Cadux is a Flet-based chat frontend for Hermes Agent. When you run Cadux on
your phone or another machine and want to connect it to this Hermes server,
you normally need to type the API URL and secret key by hand — hard on a phone
keyboard. This skill replaces that with a **3-code tap-to-pair** flow:

1. Cadux scans the LAN and finds this Hermes server via the paird daemon
2. Cadux shows 3 short alphanumeric codes on screen
3. You open the pairing web UI on this server and **read the highlighted code aloud**
4. The person with Cadux taps the matching code
5. The API config is encrypted with that code and sent to Cadux

The human-in-the-loop visual verification ensures only an authorized person
(one who can see both screens) gets the API key.

## How It Works

Two components work together:

### 1. paird daemon (`paird/server.py`)

A lightweight aiohttp web server that:
- Serves `GET /discover` for LAN auto-discovery
- Accepts `POST /start` to create a pairing session (returns 3 codes)
- Accepts `POST /confirm/<session>` to verify a code and return the encrypted config
- Serves a web UI at `GET /` showing which code is live

### 2. Cadux client (`src/pairing.py` in the Cadux repo)

Discovers paird on the LAN, shows codes, sends the user's tap for confirmation.

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
4. Hermes `config.yaml`

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

## Flow — When a User Asks to Pair

When someone with Cadux says they want to connect, follow these steps:

1. **Start the daemon** if not already running:
   ```bash
   python3 $PAIRD_MGR start
   ```

2. **Tell the user the daemon URL** — they'll see codes appear on Cadux:
   > "Open `http://<your-ip>:8643/` on your browser — you'll see three codes on your Cadux screen. Read me the highlighted one."

   Wait for the user to read a code.

3. **Verify the code in the web UI** — the live code is highlighted in red.
   If the code matches what they see on Cadux, tell them to tap it.

4. **Confirm the pairing worked** — the user should get a "Connected!" message
   on Cadux, and Hermes will be configured automatically on their device.

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
The daemon binds to `0.0.0.0`, so it listens on all interfaces.

**Wrong code tapped:**
The daemon returns a 403 error. Cadux shows "Wrong code — try another".
The correct code is always the highlighted one in the web UI.

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

- The pairing code is a visual verification channel — someone must be able
  to see **both** the server operator's screen and the Cadux screen to
  intercept the pairing.
- The API key is encrypted in transit using XOR with a SHA-256 derived key.
- Pairing sessions expire after 120 seconds.
- This is not designed to replace TLS or certificate-based auth for
  production deployments — it's a convenience layer for LAN development use.
