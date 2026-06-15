# Cadux Pairing System

Three pairing methods are available:

| Method | Best for | Requires |
|--------|----------|----------|
| **Code Pair** (recommended) | Android / mobile | Just talk to Hermes |
| **QR Code** | Android / mobile | Phone camera to scan QR |
| **LAN Scan** | Desktop | Devices on same subnet |

---

## Method 1: Code Pairing (Recommended)

The simplest flow: Cadux shows a 4-character code. The user tells Hermes that
code. Cadux auto-detects the result and connects — no typing anywhere, no
camera, no web browser.

### High-Level Flow

```
┌─────────┐                          ┌──────────────────┐
│  Hermes  │                          │   Cadux (phone)  │
│          │                          │                   │
│          │  1. Cadux generates      │                   │
│          │     random code "K47M"   │  Shows "K47M"     │
│          │  <── POST /register ──── │  "Tell Hermes:    │
│          │     {code:"K47M"}        │   Pair with...    │
│          │                          │    code K47M"     │
│          │                          │                   │
│  user ───┤  2. Tells Hermes:        │                   │
│          │     "Pair with cadux,    │                   │
│          │      code K47M"          │                   │
│          │                          │                   │
│          │  3. Hermes calls         │                   │
│          │     POST /initiate       │                   │
│          │     {"code":"K47M"}      │                   │
│          │  ─── config_encrypted ──>│  Decrypts locally  │
│          │                          │  → connected!     │
└─────────┘                          └──────────────────┘
```

### End-User Steps

1. Open **Cadux** on your phone → tap Settings ⚙ → **"Code Pair"** tab
2. Tap **"Start Code Pairing"** → a 4-character code appears (e.g. `K47M`)
3. **Tell Hermes**: "Pair with cadux, code K47M"
4. Cadux auto-connects — you'll see "✅ Paired!" and the chat UI appears

### Security

- Config (API URL + secret key) is **XOR-encrypted** with a SHA-256 derived key
- The **code** is shown only on the phone — an attacker needs physical proximity to see it
- Sessions **expire after 120 seconds**
- Each pairing attempt generates a **fresh random code**

### paird Endpoints

```
POST /register {"code": "K47M"}  → {session_id, status: "waiting"}
POST /initiate {"code": "K47M"}  → {session_id, status: "ready"}  (Hermes calls this)
GET  /session/{id}               → {status, codes, config_encrypted, md5_sig}
```

---

## Method 2: QR Code Pairing

A QR-code-based flow where the paird server displays a QR code on its web UI;
the user scans it with their phone, pastes the encrypted blob into Cadux, types
the decryption code shown on screen, and is connected. Works on any network —
no LAN discovery needed.

### End-User Steps

1. On the Hermes machine, open `http://<hermes-ip>:8643/qrcode` in a browser
2. You'll see a **QR code** and a large **Decryption Code** (e.g. `K47M`)
3. **Scan the QR** with your phone camera → your phone shows the encrypted text
4. **Copy the full encrypted text** from your phone
5. Open **Cadux** → tap Settings ⚙ → **"QR Code"** tab
6. **Paste the encrypted blob** into the text area
7. **Type the Decryption Code** you see on screen
8. Tap **"Decrypt & Connect"** → Cadux configures itself and connects

No typing of long API URLs or secret keys on a phone keyboard!

### Security

- Config (API URL + secret key) is **XOR-encrypted** with a SHA-256 derived key
- The **decryption code** is displayed as readable text *next to* the QR, not embedded
  in it — someone must both see the QR *and* read the screen to get the config
- QR sessions **expire after 120 seconds** (auto-refresh for a fresh code)
- Each page load generates a **fresh session** with a new random code

### paird Endpoint

```
GET /qrcode     → QR pairing page (HTML + JS)
GET /qr-session/{id}  → JSON {encrypted, code, md5_sig} (for programmatic access)
```

---

## Method 3: LAN Scan + Hermes-Initiated Pairing

A zero-typing LAN discovery + visual verification flow for desktop environments
where devices are on the same subnet.

### High-Level Flow

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

### End-User View

1. **Open Cadux** → tap "🔍 LAN Scan" (banner) or Settings → "Find Server"
2. Cadux scans the LAN (progress bar visible), discovers paird on port 8643
3. Cadux registers a session and shows: **"Ask Hermes: Pair with cadux"**
4. **You tell Hermes** "Pair with cadux" or "My Cadux is waiting"
5. **Hermes AI calls** `POST /initiate` on paird, gets the correct code back
6. **Hermes tells you** the code — e.g. "Tap **K47** on your Cadux screen"
7. **You tap that code** on Cadux → config decrypts locally, connection established
8. ✅ Cadux shows "Paired!" and the chat UI appears

The human-in-the-loop verification ensures only an authorized person (who can
talk to both Hermes and Cadux) gets the API key.

---

## Components

### 1. `paird/server.py` — The daemon

An aiohttp web server that runs on the Hermes host. It:
- Listens on port 8643 (configurable via `PAIRD_PORT`)
- Serves a web UI at `GET /` — code claim form + active session list
- Serves `GET /qrcode` — QR pairing page (alternative method)
- Serves `GET /discover` for LAN auto-discovery
- Accepts `POST /register` — Cadux registers intent to pair (optionally with `code`)
- Accepts `POST /initiate` — **Hermes AI calls this** to trigger pairing (LAN method)
- Accepts `POST /claim` — user enters phone-displayed code; encrypts config
- Serves `GET /session/{id}` — Cadux polls for session state
- Serves `GET /qr-session/{id}` — QR session data JSON
- Serves `GET /qr-ascii` — ASCII QR for terminal use

### 2. `src/pairing.py` — The Cadux client

Used by the Cadux app to:
- `generate_code(n)` — generate a random 4-char pairing code
- `scan(timeout)` — probe the local subnet for paird daemons
- `PairingSession(url)` — manage a pairing session
- `session.register(code)` — register intent (optionally with a code for code-pairing)
- `session.poll()` — wait for pairing to be ready
- `session.try_code(code)` — XOR-decrypt config locally, verify MD5
- `decrypt_blob(encrypted_b64, code)` — decrypt a QR-scanned config blob

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

## Security Properties

| Property | How It's Achieved |
|----------|-------------------|
| No plaintext API key on wire | XOR + SHA-256 encryption |
| Short-lived sessions | Sessions expire after 120s |
| No replay | Single-use session, codes are one-shot |
| Two-factor visual (QR) | QR code + decryption code shown separately on screen |
| Human verification (LAN) | Code comes from Hermes AI, user confirms visually |

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
- **In-app QR scanner** — use Flet camera integration to scan QR directly inside Cadux
- **Pairing confirmation callback** — Hermes calls Cadux back after successful pairing
