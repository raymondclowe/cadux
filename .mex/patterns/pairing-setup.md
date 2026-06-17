---
name: pairing-setup
description: Setting up and debugging the PIN-based LAN pairing flow between Cadux and a Hermes host via paird.
triggers:
  - "pairing"
  - "pair"
  - "paird"
  - "PIN"
  - "discovery"
  - "connect phone"
  - "set up connection"
edges:
  - target: context/pairing.md
    condition: when understanding the full pairing architecture and encryption details
  - target: context/setup.md
    condition: when setting up the paird daemon environment
  - target: context/decisions.md
    condition: when questioning the XOR+SHA256 encryption choice
last_updated: 2026-06-17
---

# Pairing Setup

## Context

The pairing flow connects Cadux to a Hermes host without manually typing API URLs and secret keys.
It uses a 4-character PIN communicated out-of-band (via Hermes chat), UDP broadcast for LAN discovery,
and XOR+SHA256 encryption for credential exchange. The daemon runs on the Hermes host, not on Cadux.

Before starting, read `context/pairing.md` for the full flow and encryption details.

## Task: Start the Pairing Daemon (Hermes Host Side)

### Steps

1. Ensure environment variables are set on the Hermes host:
   ```bash
   export CADUX_API_URL=http://localhost:8642
   export CADUX_SECRET_KEY=sk-your-hermes-key
   ```
2. Navigate to the paird directory and start the daemon:
   ```bash
   cd paird
   uv run server.py --ttl 60 --pin K47M
   ```
   Replace `K47M` with a PIN using only characters from `ABCDEFGHJKMNPQRSTUVWXYZ23456789`.
3. The daemon logs: `UDP responder listening on port 8642` and `HTTP server on port 8643`.
4. Tell the user the PIN and your LAN IP. They have 60 seconds.

### Gotchas

- **PIN charset is restricted**: No I/O/0/1. Use only `ABCDEFGHJKMNPQRSTUVWXYZ23456789`.
- **Both env vars must be set**: `CADUX_API_URL` and `CADUX_SECRET_KEY`. The daemon reads `.env` as fallback for `CADUX_SECRET_KEY` only.
- **The daemon exits after first success**: If the user mistypes the PIN and gets "Wrong code", the daemon is still running. They can retry with the same PIN within the TTL. If TTL expires, restart with a fresh PIN.
- **UDP broadcast may not work on all networks**: Corporate WiFi, Docker networks, and some VPNs block UDP broadcast. Use the manual IP fallback in this case.

## Task: Debug Pairing Failures (Cadux Side)

### Steps

1. **Discovery fails ("Could not find Hermes on your network")**:
   - Check that paird is running on the host: `curl http://<host>:8643/discover`
   - Try the "Enter Manually" link in the dialog and type the host IP directly
   - Check firewall: port 8643 (TCP) and 8642 (UDP) must be open on the host
2. **Wrong code error**:
   - PIN is case-insensitive on entry (uppercased automatically) but must match exactly
   - The daemon is still alive — retry with the correct PIN
   - Check paird logs for the expected PIN
3. **"Could not decrypt config"**:
   - MD5 verification failed — the encrypted blob was corrupted or tampered with
   - This should not happen on a LAN unless there's a proxy modifying the response
   - Restart paird with a fresh PIN and retry
4. **Daemon exits before Cadux connects**:
   - Check the TTL hasn't expired (default 60s). Increase with `--ttl 120`.
   - If the daemon log says "Pairing claimed", it exited because a successful claim happened

### Verify

- [ ] `curl http://<host>:8643/discover` returns `{"service":"cadux-paird",...}`
- [ ] `curl -X POST http://<host>:8643/register -H "Content-Type: application/json" -d '{"code":"TEST"}'` with `--pin TEST` returns `{"session_id":"...","status":"ready","config_encrypted":"...","md5_sig":"..."}`
- [ ] Wrong PIN returns HTTP 403 with `{"error":"Wrong code"}`
- [ ] Cadux shows "Found Hermes at <ip>" after successful discovery
- [ ] After successful pairing, Cadux auto-connects and the status dot turns green

## Update Scaffold

- [ ] Update `.mex/ROUTER.md` "Current Project State" if pairing behavior has changed
- [ ] Update `context/pairing.md` if encryption scheme, ports, or flow changes
- [ ] If this is a new task type without a pattern, create one in `.mex/patterns/` and add to `patterns/INDEX.md`
