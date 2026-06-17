---
name: pairing
description: The PIN-based pairing system that connects Cadux to a Hermes host via LAN discovery and encrypted credential exchange.
triggers:
  - "pairing"
  - "pair"
  - "paird"
  - "PIN"
  - "discovery"
  - "LAN"
  - "UDP broadcast"
edges:
  - target: context/architecture.md
    condition: when understanding how pairing connects to the rest of the system
  - target: context/stack.md
    condition: when understanding why XOR+SHA256 was chosen over a crypto library
  - target: context/setup.md
    condition: when setting up the pairing daemon on the Hermes host
last_updated: 2026-06-17
---

# Pairing

## Flow Summary

```
Hermes host                          Cadux (phone/desktop)
───────────                          ─────────────────────
1. User says "pair my Cadux"
2. Hermes generates 4-char PIN
3. Starts paird: server.py --ttl 60 --pin K47M
4. paird listens UDP:8642 + HTTP:8643
                                     5. User taps "Set Up Connection"
                                     6. Sends UDP broadcast CADUX_DISCOVER
7. paird responds with {service, host, port}
                                     8. Shows PIN entry (4 boxes)
                                     9. User types K47M → taps Connect
                                     10. POST /register {"code":"K47M"}
11. paird validates PIN
12. Encrypts config with XOR+SHA256(PIN)
13. Returns {config_encrypted, md5_sig}
                                     14. Decrypts config, verifies MD5
                                     15. Saves as profile, auto-connects
16. paird exits immediately
```

## Components

### paird/server.py (Hermes host side)
- **`--ttl N`** — auto-exit after N seconds (default 60)
- **`--pin XXXX`** — preauthorize a PIN; matching POST /register returns encrypted config immediately
- **UDP responder** — listens on port 8642 for `CADUX_DISCOVER` pings, responds with `{service, host, port}`
- **HTTP on port 8643** — serves `/discover`, `/register`, `/session/{id}`
- **Early exit** — if `--pin` is set and a claim succeeds, exits immediately (doesn't wait for TTL)
- **Encryption** — XOR with SHA256(PIN.upper().encode()) as key stream, MD5 checksum of plaintext

### src/pairing.py (Cadux client side)
- **`discover_paird(timeout=3.0, target_ip=None)`** — UDP broadcast to 255.255.255.255:8643 (or direct to target_ip). Returns `{host, port}` or `None`.
- **`register_with_paird(host, port, pin)`** — POST /register with `{"code": pin}`. Returns response dict.
- **`pairing_flow(page)`** — full orchestration as a modal dialog: discover → PIN entry → register → decrypt → save profile → rebuild UI
- **`decrypt_config(encrypted_b64, password, expected_md5)`** — XOR decrypt, verify MD5, parse JSON. Returns `{api_url, secret_key}` or `None`.

### src/chat_ui.py — Pairing Widgets
- **`build_pin_entry(page, on_submit)`** — 4 auto-advancing uppercase character boxes + Connect button. Auto-focuses next box on input, handles Backspace to go back.
- **`build_discovery_status()`** — ProgressRing + "Searching for Hermes..." text

## Key Constraints

- **PIN charset**: `ABCDEFGHJKMNPQRSTUVWXYZ23456789` (no I/O/0/1 — unambiguous)
- **TTL**: 60 seconds default. The daemon exits after TTL or after first successful claim (whichever comes first).
- **Encryption is NOT authenticated**: XOR is not AES-GCM. MD5 is a checksum, not a MAC. Acceptable because the PIN is communicated out-of-band (Hermes chat) and the window is 60 seconds.
- **UDP discovery may fail on some networks**: The manual IP fallback allows direct entry of the paird host IP.
- **`paird/server.py` runs on the Hermes host**, not on Cadux. It is started by the Hermes agent (or manually) when the user requests pairing.
- **No QR code in the simplified flow**: The original spec included QR codes, but the current implementation uses UDP discovery + PIN only. QR is retained as a manual paste option in Settings.

## Encryption Detail

```python
# paird side (encrypt):
key = hashlib.sha256(pin.upper().encode()).digest()
encrypted = bytes(plain[i] ^ key[i % 32] for i in range(len(plain)))
md5_sig = hashlib.md5(plain).hexdigest()

# Cadux side (decrypt):
key = hashlib.sha256(password.upper().encode()).digest()
raw = base64.b64decode(encrypted_b64)
plain = bytes(raw[i] ^ key[i % 32] for i in range(len(raw)))
# verify: hashlib.md5(plain).hexdigest() == expected_md5
config = json.loads(plain)  # {"api_url": "...", "secret_key": "..."}
```
