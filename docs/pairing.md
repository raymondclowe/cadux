# Hermes Skill: Pairing Cadux

When a user says "pair my Cadux", "connect my phone", "pair with Cadux", or similar,
Hermes should run the ephemeral pairing daemon.

## Flow (one-tap for the user)

1. Start the pairing daemon (no PIN needed):

   ```bash
   cd paird
   CADUX_API_URL=http://localhost:8642 CADUX_SECRET_KEY=sk-abc123... \
       uv run server.py
   ```

2. Tell the user:
   > "Open Cadux on your phone and tap **Find Hermes**."

3. Cadux discovers paird on the LAN via:
   - UDP broadcast (fast, ~1s)
   - HTTP subnet probe (fallback, scans the phone's subnet, ~3s)

4. When found, Cadux hits `GET /config` → gets `{api_url, secret_key}` → saves as profile → connects.

Done. No PIN, no code entry, no typing.

## Daemon Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/discover` | Returns `{"service":"cadux-paird","host":"<lan_ip>"}` |
| `GET` | `/config` | Returns `{api_url, secret_key}` directly (no PIN) |
| `POST` | `/register` | PIN mode only — requires `--pin` flag on startup |

The daemon listens on UDP port **8642** for `CADUX_DISCOVER` broadcast pings and HTTP on port **8643**.

## Environment Setup

The pairing daemon reads the Hermes API URL and secret key from:

- `CADUX_API_URL` (or `HERMES_API_URL` as fallback) — defaults to `http://localhost:8642`
- `CADUX_SECRET_KEY` — the Hermes API key the phone will use

Make sure both are set before the daemon starts.

## PIN Mode (legacy / optional)

Start with `--pin` flag for extra security:

```bash
PAIRD_PORT=8643 uv run server.py --ttl 60 --pin K47M
```

In this mode, Cadux shows a PIN entry screen and the daemon encrypts the config with the PIN.

## Troubleshooting

- **Cadux can't find paird** → Check port 8643 is reachable on the LAN. Try `curl http://<host>:8643/discover` from another machine.
- **"No CADUX_SECRET_KEY found"** → Set `CADUX_SECRET_KEY` env var before starting paird.
