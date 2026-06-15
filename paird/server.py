"""
Cadux Pairing Daemon — lightweight companion server for Hermes.

Runs alongside the Hermes gateway on tc5 (or any Hermes host) on port 8643.
Provides a zero-typing pairing flow for Cadux clients on the LAN.

Flow:
  1. Cadux auto-discovers paird on the LAN via GET /discover
  2. Cadux calls POST /register → gets session_id, shows "Ask Hermes to pair"
  3. User tells Hermes "Pair with cadux"
  4. Hermes calls POST /initiate → generates 6 codes, encrypts config
  5. Hermes displays the correct code to the user
  6. Cadux polls GET /session/{id} → when ready, shows 6 code buttons
  7. User taps the matching code on Cadux
  8. Cadux XOR-decrypts config with the code, verifies MD5 signature
  9. Cadux auto-configures and sends "pairing successful" to Hermes

Quick start on Hermes host:
    cd paird
    CADUX_API_URL=http://localhost:8642 CADUX_SECRET_KEY=your-key uv run server.py

Endpoints:
    GET  /              HTML pairing UI (lists sessions + correct codes)
    GET  /discover      JSON identity for auto-discovery
    POST /register      Register pairing intent → {session_id, status:"waiting"}
    GET  /session/{id}  Poll for session state → {status, codes?, config_encrypted?, md5_sig?}
    POST /initiate      Hermes triggers pairing → {correct_code, session_id}
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
# session_id -> {codes, correct_code, config_encrypted, md5_sig, created_at, status}

_sessions: dict[str, dict] = {}
_SESSION_TTL = 120  # seconds
_CLEANUP_INTERVAL = 15

# ── Helpers ──────────────────────────────────────────────────────────


_CHARS = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no I/O/0/1 for readability


def _generate_code(n=3):
    """Generate a short alphanumeric code like 'K47'."""
    return "".join(random.choice(_CHARS) for _ in range(n))


def _generate_codes(count=6):
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
            with open(env_path, encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("CADUX_SECRET_KEY="):
                        secret_key = line.split("=", 1)[1].strip().strip('"').strip("'")
        except FileNotFoundError:
            pass
    return {"api_url": api_url.rstrip("/"), "secret_key": secret_key}


def _encrypt(data: bytes, password: str) -> tuple[str, str]:
    """XOR-encrypt with a SHA256-derived key.
    Returns (base64_encrypted, md5_of_plaintext)."""
    key = hashlib.sha256(password.encode()).digest()
    enc = bytes(data[i] ^ key[i % len(key)] for i in range(len(data)))
    md5_sig = hashlib.md5(data).hexdigest()
    return base64.b64encode(enc).decode(), md5_sig


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


async def handle_register(request):
    """Cadux registers intent to pair — no codes yet, waits for Hermes."""
    now = time.time()
    config = _load_server_config()
    session_id = str(uuid.uuid4())
    _sessions[session_id] = {
        "config": config,
        "created_at": now,
        "status": "waiting",
    }
    logger.info("Registration — session %s waiting for Hermes", session_id[:8])
    return web.json_response({"session_id": session_id, "status": "waiting"})


async def handle_initiate(request):
    """Hermes triggers pairing: generates 6 codes, encrypts config.
    Pairs with the most recent 'waiting' session.
    Returns {correct_code} for Hermes to display.
    """
    now = time.time()

    # Find the most recent pending session
    pending = None
    pending_sid = None
    for sid, s in _sessions.items():
        if s.get("status") == "waiting" and (now - s["created_at"]) <= _SESSION_TTL:
            if pending is None or s["created_at"] > pending["created_at"]:
                pending = s
                pending_sid = sid

    if not pending:
        return web.json_response(
            {"error": "No pending pairing request. Open Cadux first."}, status=404
        )

    codes = _generate_codes(6)
    correct = codes[0]
    config_json = json.dumps(pending["config"]).encode()
    config_encrypted, md5_sig = _encrypt(config_json, correct)

    pending["codes"] = codes
    pending["correct_code"] = correct
    pending["config_encrypted"] = config_encrypted
    pending["md5_sig"] = md5_sig
    pending["status"] = "ready"

    logger.info(
        "Initiated — session %s codes=%s (correct: %s)",
        pending_sid[:8], codes, correct,
    )
    return web.json_response({"correct_code": correct, "session_id": pending_sid})


async def handle_session_status(request):
    """Cadux polls this to check if Hermes has initiated yet."""
    session_id = request.match_info["session"]
    session = _sessions.get(session_id)
    if not session or (time.time() - session["created_at"]) > _SESSION_TTL:
        return web.json_response({"status": "expired"}, status=404)

    status = session.get("status", "waiting")
    if status == "waiting":
        return web.json_response({"status": "waiting"})

    # Ready — send codes (shuffled so correct isn't always first in transmission)
    codes = list(session["codes"])
    random.shuffle(codes)
    return web.json_response({
        "status": "ready",
        "codes": codes,
        "config_encrypted": session["config_encrypted"],
        "md5_sig": session["md5_sig"],
    })


# ── Web UI (for server operator) ────────────────────────────────────


async def handle_web_ui(request):
    now = time.time()
    rows = ""
    for sid, s in sorted(_sessions.items(), key=lambda x: x[1]["created_at"], reverse=True):
        if (now - s["created_at"]) > _SESSION_TTL:
            continue
        age = int(now - s["created_at"])
        remaining = max(0, _SESSION_TTL - age)
        status = s.get("status", "waiting")
        if status == "ready":
            codes = s.get("codes", [])
            correct = s.get("correct_code", "")
            btns = " ".join(
                f'<span class="code {"live" if c == correct else "off"}">{html.escape(c)}</span>'
                for c in codes
            )
            rows += f"""
        <tr>
            <td>{btns}</td>
            <td><span class="ready">READY</span></td>
            <td><span class="dim">{remaining}s</span></td>
        </tr>"""
        else:
            rows += f"""
        <tr>
            <td style="color:#666">Waiting for Hermes…</td>
            <td><span class="waiting">WAITING</span></td>
            <td><span class="dim">{remaining}s</span></td>
        </tr>"""

    if not rows:
        rows = '<tr><td colspan="3" style="text-align:center;color:#888;padding:2em">No active pairing sessions — open Cadux to start one.</td></tr>'

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
  table {{ width:100%; max-width:460px; border-collapse:collapse; }}
  td {{ padding:0.75rem 0.5rem; border-top:1px solid #333; vertical-align:middle; }}
  .code {{ display:inline-block; padding:0.5rem 1rem; margin:0.1rem; font-size:1.2rem; font-weight:bold; border-radius:10px; }}
  .live {{ background:#e94560; color:#fff; }}
  .off {{ background:#2a2a4a; color:#666; }}
  .ready {{ color:#4ecca3; font-weight:bold; font-size:0.8rem; }}
  .waiting {{ color:#f0a500; font-size:0.8rem; }}
  .dim {{ color:#666; font-size:0.8rem; }}
</style>
</head>
<body>
  <h1>🔗 Cadux Pairing</h1>
  <p class="sub">Sessions appear here when Cadux registers.  Use Hermes to initiate pairing.</p>
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
    app.router.add_post("/register", handle_register)
    app.router.add_get("/session/{session}", handle_session_status)
    app.router.add_post("/initiate", handle_initiate)

    config = _load_server_config()
    if config["secret_key"]:
        logger.info("Loaded Hermes config — API: %s", config["api_url"])
    else:
        logger.warning("No CADUX_SECRET_KEY found! Pairing will produce unusable config.")

    logger.info("Pairing daemon starting on port %d", port)
    web.run_app(app, host="0.0.0.0", port=port, print=lambda _: None)


if __name__ == "__main__":
    main()
