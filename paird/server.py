"""
Cadux Pairing Daemon — lightweight companion server for Hermes.

Runs alongside the Hermes gateway on tc5 (or any Hermes host) on port 8643.
Provides a zero-typing pairing flow for Cadux clients on the LAN.

Flow:
  1. Cadux auto-discovers paird on the LAN via GET /discover
  2. Cadux calls POST /start → gets 3 codes (no config yet)
  3. Cadux shows the 3 codes on screen as tappable buttons
  4. Server operator opens http://<host>:8643/ and reads the live code aloud
  5. User taps the matching code on Cadux → POST /confirm/<session> {code}
  6. Server encrypts config with that code and returns it
  7. Wrong code → 403, no config leaked

Quick start on Hermes host:
    uv run paird/server.py

Endpoints:
    GET  /          HTML pairing UI (for server operator)
    GET  /discover  JSON identity for auto-discovery
    POST /start     Returns {codes: ["K47", "X2B", "M9Q"]}
    POST /confirm/<session>  Body: {code} → returns {config_encrypted} or 403
"""

import asyncio
import base64
import hashlib
import html
import json
import logging
import os
import random
import time
import uuid

import aiohttp
from aiohttp import web

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("paird")

# ── Session store ────────────────────────────────────────────────────
# session_id -> {codes, config, created_at}

_sessions: dict[str, dict] = {}
_SESSION_TTL = 120  # seconds
_CLEANUP_INTERVAL = 15

# ── Helpers ──────────────────────────────────────────────────────────


_CHARS = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no I/O/0/1 for readability


def _generate_code(n=3):
    """Generate a short alphanumeric code like 'K47'."""
    return "".join(random.choice(_CHARS) for _ in range(n))


def _generate_codes(count=3):
    """Generate *count* unique short codes. The first is the 'live' one."""
    seen = set()
    codes = []
    for _ in range(count):
        while True:
            c = _generate_code()
            if c not in seen:
                seen.add(c)
                codes.append(c)
                break
    return codes


def _load_server_config():
    """Load the Hermes API URL and key from the environment."""
    api_url = os.environ.get(
        "CADUX_API_URL",
        os.environ.get("HERMES_API_URL", "http://localhost:8642"),
    )
    secret_key = os.environ.get("CADUX_SECRET_KEY", "")
    if not secret_key:
        env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
        try:
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("CADUX_SECRET_KEY="):
                        secret_key = line.split("=", 1)[1].strip().strip('"').strip("'")
        except FileNotFoundError:
            pass
    return {"api_url": api_url.rstrip("/"), "secret_key": secret_key}


def _encrypt(data: bytes, password: str) -> str:
    """XOR-encrypt with a SHA256-derived key. Returns base64."""
    key = hashlib.sha256(password.encode()).digest()
    enc = bytes(data[i] ^ key[i % len(key)] for i in range(len(data)))
    return base64.b64encode(enc).decode()


def _decrypt(encoded: str, password: str) -> bytes:
    key = hashlib.sha256(password.encode()).digest()
    raw = base64.b64decode(encoded)
    return bytes(raw[i] ^ key[i % len(key)] for i in range(len(raw)))


def _get_local_ip():
    """Best-effort local LAN IP."""
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.1)
        s.connect(("192.168.0.1", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


# ── Route handlers ───────────────────────────────────────────────────


async def handle_discover(request):
    return web.json_response({
        "service": "cadux-paird",
        "version": "1.0",
        "host": _get_local_ip(),
    })


async def handle_start(request):
    """Generate 3 codes. Config is stored server-side until confirmation."""
    now = time.time()
    codes = _generate_codes(3)
    correct = codes[0]  # first code is the live one

    config = _load_server_config()
    session_id = str(uuid.uuid4())
    _sessions[session_id] = {
        "codes": codes,
        "config": config,
        "created_at": now,
    }

    logger.info("Pairing started — codes: %s  (correct: %s)", codes, correct)
    return web.json_response({"codes": codes, "session": session_id})


async def handle_confirm(request):
    """User tapped a code. If correct, encrypt config and return it."""
    session_id = request.match_info["session"]
    session = _sessions.get(session_id)
    if not session or (time.time() - session["created_at"]) > _SESSION_TTL:
        return web.json_response({"error": "session expired"}, status=404)

    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "bad json"}, status=400)

    code = str(data.get("code", ""))
    if code not in session["codes"]:
        return web.json_response({"error": "invalid code"}, status=400)

    if code != session["codes"][0]:
        # Wrong code — human made a visual mismatch
        logger.info("Wrong code %s submitted for session %s", code, session_id[:8])
        return web.json_response({"error": "wrong code"}, status=403)

    # Correct code — encrypt config and return
    config_json = json.dumps(session["config"]).encode()
    config_encrypted = _encrypt(config_json, code)
    logger.info("Session %s confirmed with code %s", session_id[:8], code)
    return web.json_response({"config_encrypted": config_encrypted})


# ── Web UI (for server operator) ────────────────────────────────────


async def handle_web_ui(request):
    now = time.time()
    rows = ""
    for sid, s in sorted(_sessions.items(), key=lambda x: x[1]["created_at"], reverse=True):
        if (now - s["created_at"]) > _SESSION_TTL:
            continue
        age = int(now - s["created_at"])
        remaining = max(0, _SESSION_TTL - age)
        correct = s["codes"][0]
        btns = " ".join(
            f'<span class="code {"live" if c == correct else "off"}">{html.escape(c)}</span>'
            for c in s["codes"]
        )
        rows += f"""
        <tr>
            <td>{btns}</td>
            <td><span class="dim">{remaining}s</span></td>
        </tr>"""

    if not rows:
        rows = '<tr><td colspan="2" style="text-align:center;color:#888;padding:2em">No active pairing sessions — open Cadux to start one.</td></tr>'

    html_page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Cadux Pairing</title>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ font-family:-apple-system,sans-serif; background:#1a1a2e; color:#eee; min-height:100vh; display:flex; flex-direction:column; align-items:center; padding:2rem 1rem; }}
  h1 {{ font-size:1.4rem; margin-bottom:0.25rem; }}
  .sub {{ color:#888; font-size:0.85rem; margin-bottom:1.5rem; }}
  table {{ width:100%; max-width:420px; border-collapse:collapse; }}
  td {{ padding:0.75rem 0.5rem; border-top:1px solid #333; vertical-align:middle; }}
  .code {{ display:inline-block; padding:0.6rem 1.2rem; margin:0.1rem; font-size:1.3rem; font-weight:bold; border-radius:10px; }}
  .live {{ background:#e94560; color:#fff; }}
  .off {{ background:#2a2a4a; color:#666; }}
  .dim {{ color:#666; font-size:0.8rem; }}
</style>
</head>
<body>
  <h1>🔗 Cadux Pairing</h1>
  <p class="sub">Say the <strong style="color:#e94560">highlighted</strong> code to the person with Cadux</p>
  <table><tbody>{rows}</tbody></table>
  <p class="sub" style="margin-top:2rem">Codes expire after 2 minutes</p>
</body>
</html>"""
    return web.Response(text=html_page, content_type="text/html")


# ── Background cleanup ──────────────────────────────────────────────


async def _cleanup_loop():
    while True:
        await asyncio.sleep(_CLEANUP_INTERVAL)
        now = time.time()
        expired = [sid for sid, s in _sessions.items()
                   if (now - s["created_at"]) > _SESSION_TTL]
        for sid in expired:
            del _sessions[sid]
        if expired:
            logger.debug("Cleaned up %d expired sessions", len(expired))


# ── Main ─────────────────────────────────────────────────────────────


def main():
    port = int(os.environ.get("PAIRD_PORT", "8643"))
    app = web.Application()
    app.router.add_get("/", handle_web_ui)
    app.router.add_get("/discover", handle_discover)
    app.router.add_post("/start", handle_start)
    app.router.add_post("/confirm/{session}", handle_confirm)

    config = _load_server_config()
    if config["secret_key"]:
        logger.info("Loaded Hermes config — API: %s", config["api_url"])
    else:
        logger.warning("No CADUX_SECRET_KEY found! Pairing will produce unusable config.")

    logger.info("Pairing daemon starting on port %d", port)
    web.run_app(app, host="0.0.0.0", port=port, print=lambda _: None)


if __name__ == "__main__":
    main()
