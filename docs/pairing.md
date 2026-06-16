# Hermes Skill: Pairing Cadux

When a user says "pair my Cadux", "connect my phone", "pair with Cadux", or similar,
Hermes should run the ephemeral pairing daemon and relay the PIN to the user.

## Flow

1. Generate a 4-character PIN using unambiguous characters (no I/O/0/1).
   Use these characters: `ABCDEFGHJKMNPQRSTUVWXYZ23456789`

2. Determine the Hermes host's LAN IP.

3. Start the pairing daemon with the PIN and a 60-second TTL:

   ```
   cd paird
   PAIRD_PORT=8643 uv run server.py --ttl 60 --pin <PIN>
   ```

4. Tell the user:
   > "Open Cadux on your phone. Tap **Set Up Connection** and enter: **<PIN>**.
   > I'm at **<LAN_IP>**. You have 60 seconds."

5. If the pairing succeeds, the daemon exits immediately. No further action needed.

6. If the user says it timed out or failed, repeat from step 1 with a fresh PIN.

## Daemon Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/discover` | Returns `{"service":"cadux-paird","host":"<lan_ip>","port":8643}` |
| `POST` | `/register` | Cadux sends `{"code": "<PIN>"}`, returns encrypted config on match |
| `GET` | `/session/{id}` | Poll session state (used for non-PIN fallback) |

The daemon listens on UDP port **8642** for `CADUX_DISCOVER` broadcast pings from Cadux and serves HTTP on port **8643** by default.

## Environment Setup

The pairing daemon reads the Hermes API URL and secret key from these environment variables:

- `CADUX_API_URL` (or `HERMES_API_URL` as fallback) — defaults to `http://localhost:8642`
- `CADUX_SECRET_KEY` — the Hermes API key the phone will use

Make sure both are set before the daemon starts:
```
export CADUX_API_URL=http://localhost:8642
export CADUX_SECRET_KEY=sk-abc123...
```

## Troubleshooting

- **Cadux can't find paird** → Check that port 8643 is reachable on the LAN. Try `curl http://<host>:8643/discover` from another machine on the same network.
- **Wrong code error** → The PIN is case-sensitive. Ensure the code displayed by Hermes matches exactly.
- **Pairing times out** → The daemon exits after 60 seconds. Run it again with a fresh PIN.
