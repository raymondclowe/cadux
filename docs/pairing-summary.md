# Cadux Ephemeral PIN Pairing — Implementation Summary

## Files Changed

### `paird/server.py` — Complete rewrite
- **Ephemeral mode**: `--ttl N` CLI arg (default 60s) — process auto-exits after N seconds
- **PIN-preauthorize**: `--pin XXXX` — matching PIN in POST /register immediately returns encrypted config (no polling needed)
- **UDP broadcast responder**: Listens on UDP port for `CADUX_DISCOVER` pings, responds with service identity
- **Early-exit**: After first successful claim, exits immediately instead of waiting for TTL
- **Removed**: QR endpoints, 6-code generation, HTML web UI, `qrcode` import, claim endpoint, initiate endpoint
- **Retained**: GET /discover, POST /register, GET /session/{id}

### `src/pairing.py` — New file
- `decrypt_config()` — XOR+SHA256 decryption with MD5 verification (mirrors paird/server.py)
- `discover_paird()` — UDP broadcast to 255.255.255.255:8643, returns `{host, port}` or None
- `register_with_paird()` — POST /register with PIN, returns response dict
- `pairing_flow()` — Full orchestration inside a modal dialog: discover → PIN entry → register → decrypt → save profile → auto-connect
- On discovery failure: shows manual IP fallback (IP text field + Try Manual IP button)
- On PIN failure: shows error text inline ("Wrong code", "Timed out", "Could not decrypt")
- On success: saves profile via `create_profile()`, sets active, rebuilds UI via `main()`

### `src/chat_ui.py` — 2 new widgets
- `build_pin_entry(on_submit)` — 4 auto-advancing uppercase character boxes (52x60px each) + Connect button. Calls `on_submit(pin)` when tapped with 4 chars filled.
- `build_discovery_status()` — ProgressRing + "Searching for Hermes..." text

### `src/main.py` — 3 changes
- **Unconfigured banner**: Replaced dual "Settings" + "Code Pair" buttons with single "📱 Set Up Connection" button
- **`_pairing_flow_dialog()`**: New function — calls `pairing.pairing_flow()`, falls back to manual-entry settings on failure
- **`_show_settings_dialog()`**: Rewritten — pairing primary ("📱 Set Up with Code" button at top), manual entry fields collapsed under "Enter Manually" toggle. For already-configured profiles, shows profile name + status + "Re-pair" button at top.

### `docs/pairing.md` — New file
- Hermes skill instructions for generating PIN and starting paird
- Daemon endpoint reference
- Troubleshooting guide

## Dependencies
- **Zero new Python dependencies** — all stdlib (socket, hashlib, base64) + existing aiohttp

## Flow

```
User → Hermes: "Pair my Cadux"
Hermes:
  1. Generates 4-char PIN (e.g. "K47M")
  2. Starts: paird/server.py --ttl 60 --pin K47M
  3. Tells user: "Enter K47M in Cadux. I'm at 192.168.0.83."

Cadux (phone):
  1. Opens settings → taps "Set Up with Code"
  2. Sends UDP broadcast → discovers paird at 192.168.0.83:8643
  3. Shows PIN entry → user types K47M → tap Connect
  4. POST /register {"code":"K47M"} → gets back encrypted config
  5. XOR-decrypts, verifies MD5 → saves profile → auto-connects
  6. paird exits immediately
```

## Verification

```bash
# Terminal 1: Start paird
cd paird
CADUX_API_URL=http://localhost:8642 CADUX_SECRET_KEY=sk-test uv run server.py --ttl 120 --pin TEST

# Terminal 2: Test UDP discovery
python -c "
import socket
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
s.settimeout(2)
s.sendto(b'CADUX_DISCOVER', ('255.255.255.255', 8643))
data, addr = s.recvfrom(1024)
print('Response from', addr, ':', data.decode())
s.close()
"

# Terminal 2: Test register with correct PIN
curl -X POST http://localhost:8643/register -H "Content-Type: application/json" -d '{"code":"TEST"}'
# → {"session_id":"...", "status":"ready", "config_encrypted":"...", "md5_sig":"..."}

# Terminal 2: Test wrong PIN
curl -X POST http://localhost:8643/register -H "Content-Type: application/json" -d '{"code":"WRONG"}'
# → {"error":"Wrong code"} (HTTP 403)
```
