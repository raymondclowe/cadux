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
    GET  /qrcode        HTML QR pairing page (browser-based scan)
    GET  /qr-ascii      Plain-text ASCII QR for terminal (curl-friendly)
    GET  /discover      JSON identity for auto-discovery
    POST /register      Register pairing intent → {session_id, status:"waiting"}
    GET  /session/{id}  Poll for session state → {status, codes?, config_encrypted?, md5_sig?}
    POST /initiate      Hermes triggers pairing → {correct_code, session_id}
    GET  /qr-session/{id}  JSON {encrypted, code, md5_sig} for QR session
"""

import asyncio
import base64
import hashlib
import html
import io
import json
import logging
import os
import random
import time
import uuid

import qrcode
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
    """Cadux registers intent to pair — optionally with a code for code-claim flow."""
    now = time.time()
    config = _load_server_config()
    session_id = str(uuid.uuid4())
    code = None
    try:
        body = await request.json()
        code = (body.get("code") or "").strip() or None
    except Exception:
        pass
    _sessions[session_id] = {
        "config": config,
        "created_at": now,
        "status": "waiting",
        "code": code,
    }
    if code:
        logger.info("Registration — session %s with code %s", session_id[:8], code)
    else:
        logger.info("Registration — session %s waiting for Hermes", session_id[:8])
    return web.json_response({"session_id": session_id, "status": "waiting"})


async def handle_initiate(request):
    """Hermes triggers pairing: encrypts config and marks session ready.

    Accepts optional {"code": "K47M"} — if provided, finds the waiting session
    with that code and uses it as the encryption key. Otherwise falls back to
    legacy mode: finds the most recent waiting session, generates 6 codes.

    Returns {correct_code, session_id, status} or 404.
    """
    now = time.time()
    code = None
    try:
        body = await request.json()
        code = (body.get("code") or "").strip().upper() or None
    except Exception:
        pass

    pending = None
    pending_sid = None

    if code:
        # Code-pairing mode: find the exact session with this code
        for sid, s in _sessions.items():
            if s.get("status") != "waiting":
                continue
            if (now - s["created_at"]) > _SESSION_TTL:
                continue
            if s.get("code") == code:
                pending = s
                pending_sid = sid
                break

        if not pending:
            return web.json_response(
                {"error": f"No waiting session with code '{code}'. Open Cadux first and try again."},
                status=404,
            )

        # Use the provided code directly — no need to generate 6 codes
        correct = code
        config_json = json.dumps(pending["config"]).encode()
        config_encrypted, md5_sig = _encrypt(config_json, correct)
        pending["codes"] = [correct]
        pending["correct_code"] = correct
        pending["config_encrypted"] = config_encrypted
        pending["md5_sig"] = md5_sig
        pending["status"] = "ready"
        logger.info("Initiated (code mode) — session %s code=%s", pending_sid[:8], correct)
        return web.json_response({
            "correct_code": correct,
            "session_id": pending_sid,
            "status": "ready",
        })

    # Legacy mode: find most recent waiting session, generate 6 codes
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
        "Initiated (6-code mode) — session %s codes=%s (correct: %s)",
        pending_sid[:8], codes, correct,
    )
    return web.json_response({"correct_code": correct, "session_id": pending_sid})


async def handle_claim(request):
    """Claim a waiting session by code — encrypts config and marks ready.

    Accepts JSON {"code": "K47M"} or form POST code=K47M.
    Returns {correct_code, session_id} on success, or 404 if code not found.
    """
    code = ""
    if request.content_type == "application/x-www-form-urlencoded":
        data = await request.post()
        code = (data.get("code") or "").strip().upper()
    else:
        try:
            body = await request.json()
            code = (body.get("code") or "").strip().upper()
        except Exception:
            pass

    if not code:
        return web.json_response({"error": "Missing code"}, status=400)

    now = time.time()
    # Find waiting session with matching code
    for sid, s in list(_sessions.items()):
        if s.get("status") != "waiting":
            continue
        if (now - s["created_at"]) > _SESSION_TTL:
            continue
        if s.get("code") == code:
            config_json = json.dumps(s["config"]).encode()
            config_encrypted, md5_sig = _encrypt(config_json, code)
            s["codes"] = [code]
            s["correct_code"] = code
            s["config_encrypted"] = config_encrypted
            s["md5_sig"] = md5_sig
            s["status"] = "ready"
            logger.info("Claimed — session %s code=%s", sid[:8], code)
            return web.json_response({"session_id": sid, "status": "ready"})

    return web.json_response({"error": "No waiting session with that code"}, status=404)


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
  <p class="sub">Type the code shown on your Cadux phone app, then tap Claim.</p>
  <form method="POST" action="/claim" enctype="application/x-www-form-urlencoded" style="margin:1rem 0;display:flex;gap:0.5rem;align-items:center;flex-wrap:wrap;justify-content:center;">
    <input name="code" placeholder="e.g. K47M" required
      style="padding:0.6rem 1rem;font-size:1.3rem;width:140px;text-align:center;border:2px solid #e94560;border-radius:10px;background:#2a2a4a;color:#eee;letter-spacing:0.15em;text-transform:uppercase;"
      maxlength="4" autofocus>
    <button type="submit" style="padding:0.6rem 1.5rem;font-size:1rem;background:#e94560;color:#fff;border:none;border-radius:10px;cursor:pointer;font-weight:bold;">Claim</button>
  </form>
  <p style="margin:0.5rem 0 1rem"><a href="/qrcode" style="color:#4ecca3;font-size:0.9rem;">📱 Use QR Code instead (no LAN scan)</a></p>
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


# ── QR-code Pairing ──────────────────────────────────────────────────

_QR_SESSIONS: dict[str, dict] = {}
_QR_TTL = 120  # seconds


async def handle_qrcode_page(request):
    """Serve the QR-code pairing page.

    Each load generates a fresh encrypted session with a random decryption code.
    """
    config = _load_server_config()
    if not config["secret_key"]:
        return web.Response(
            text="<h1>Not configured</h1><p>Set CADUX_API_URL and CADUX_SECRET_KEY in the environment.</p>",
            content_type="text/html",
            status=503,
        )

    # Generate a fresh session
    code = _generate_code(4)  # 4-char for QR mode (extra entropy vs 3-char tap codes)
    config_json = json.dumps(config).encode()
    config_encrypted, md5_sig = _encrypt(config_json, code)
    session_id = str(uuid.uuid4())

    _QR_SESSIONS[session_id] = {
        "code": code,
        "config_encrypted": config_encrypted,
        "md5_sig": md5_sig,
        "created_at": time.time(),
    }

    html_page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Cadux QR Pairing</title>
<script src="https://cdn.jsdelivr.net/npm/qrcodejs@1.0.0/qrcode.min.js"><{"/script>"}
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ font-family:-apple-system,sans-serif; background:#1a1a2e; color:#eee; min-height:100vh; display:flex; flex-direction:column; align-items:center; justify-content:center; padding:2rem 1rem; text-align:center; }}
  h1 {{ font-size:1.6rem; margin-bottom:0.25rem; }}
  .sub {{ color:#888; font-size:0.85rem; margin-bottom:0.5rem; max-width:400px; }}
  .qr-wrap {{ background:#fff; padding:1.25rem; border-radius:16px; display:inline-block; margin:1rem 0; }}
  #qr {{ display:flex; justify-content:center; }}
  #qr img {{ display:block; }}
  .code-label {{ color:#888; font-size:0.8rem; margin-top:0.25rem; }}
  .code {{ font-size:3rem; font-weight:bold; color:#e94560; letter-spacing:0.15em; margin:0.25rem 0; }}
  .hint {{ color:#888; font-size:0.8rem; margin-top:1rem; }}
  .steps {{ text-align:left; margin:1rem auto; max-width:360px; font-size:0.85rem; line-height:1.6; }}
  .steps li {{ margin-bottom:0.5rem; }}
  .refresh {{ margin-top:1.5rem; background:#2a2a4a; color:#eee; border:1px solid #444; padding:0.5rem 1.5rem; border-radius:8px; cursor:pointer; font-size:0.85rem; }}
  .refresh:hover {{ background:#3a3a5a; }}
  .footer {{ color:#555; font-size:0.75rem; margin-top:2rem; }}
</style>
</head>
<body>
  <h1>📱 Cadux QR Pairing</h1>
  <p class="sub">Scan with your phone's camera, then paste the blob into Cadux with the code below.</p>

  <div class="qr-wrap">
    <div id="qr"></div>
  </div>

  <div class="code-label">Decryption Code</div>
  <div class="code" id="decrypt-code">{html.escape(code)}</div>

  <div class="hint">Scan the QR → copy the text → open Cadux → Settings → "Use QR Code"</div>

  <ol class="steps">
    <li>Scan the <strong>QR code</strong> with your phone camera</li>
    <li>Copy the <strong>full encrypted text</strong> it shows</li>
    <li>Open <strong>Cadux</strong> → tap Settings ⚙ → "Use QR Code"</li>
    <li>Paste the blob and type the <strong>decryption code</strong> above</li>
    <li>Tap <strong>Decrypt & Connect</strong> — done!</li>
  </ol>

  <button class="refresh" onclick="location.reload()">🔄 Generate New QR</button>
  <div class="footer">Session expires after 2 minutes • Refresh for a fresh code</div>

  <script>
    var encrypted = {json.dumps(config_encrypted)};
    new QRCode(document.getElementById("qr"), {{
      text: encrypted,
      width: 220,
      height: 220,
      colorDark: "#1a1a2e",
      colorLight: "#ffffff",
      correctLevel: QRCode.CorrectLevel.H
    }});
  <{"/script>"}
</body>
</html>"""
    return web.Response(text=html_page, content_type="text/html", charset="utf-8")


async def handle_qr_session_data(request):
    """Return encrypted config + code for a QR session (so native app can fetch directly)."""
    session_id = request.match_info["session"]
    session = _QR_SESSIONS.get(session_id)
    if not session or (time.time() - session["created_at"]) > _QR_TTL:
        return web.json_response({"error": "expired"}, status=404)
    return web.json_response({
        "encrypted": session["config_encrypted"],
        "code": session["code"],
        "md5_sig": session["md5_sig"],
    })


async def handle_qr_ascii(request):
    """Return a QR code as ASCII art for terminal display.

    Hermes can curl this endpoint to show the QR in its terminal.
    The user scans the ASCII QR with their phone camera.

    Response is plain text: ASCII QR art + decryption code + instructions.
    """
    config = _load_server_config()
    if not config["secret_key"]:
        return web.Response(
            text="ERROR: CADUX_API_URL and CADUX_SECRET_KEY not configured.\n",
            content_type="text/plain",
            status=503,
        )

    # Generate a fresh session (same as handle_qrcode_page)
    code = _generate_code(4)
    config_json = json.dumps(config).encode()
    config_encrypted, md5_sig = _encrypt(config_json, code)
    session_id = str(uuid.uuid4())

    _QR_SESSIONS[session_id] = {
        "code": code,
        "config_encrypted": config_encrypted,
        "md5_sig": md5_sig,
        "created_at": time.time(),
    }

    # Generate ASCII QR code
    qr = qrcode.QRCode(border=1, box_size=1)
    qr.add_data(config_encrypted)
    buf = io.StringIO()
    qr.print_ascii(out=buf, invert=False)
    ascii_qr = buf.getvalue()

    text = (
        f"\n"
        f"  ═══════════════════════════════════════\n"
        f"       CADUX QR PAIRING (TERMINAL)\n"
        f"  ═══════════════════════════════════════\n"
        f"\n"
        f"  Point your phone camera at the QR below to scan\n"
        f"  the encrypted config, or copy the code manually.\n"
        f"\n"
        f"  ── Scan this QR ────────────────────────\n"
        f"{ascii_qr}"
        f"  ────────────────────────────────────────\n"
        f"\n"
        f"  Decryption Code:  {code}\n"
        f"\n"
        f"  ── How to use ──────────────────────────\n"
        f"  1. Scan the QR above with your phone camera\n"
        f"  2. Copy the encrypted text your phone shows\n"
        f"  3. In Cadux → Settings → QR Code tab\n"
        f"  4. Paste the blob and type the code: {code}\n"
        f"  5. Tap Decrypt & Connect\n"
        f"\n"
        f"  Session expires in 2 minutes.\n"
        f"  Run this command again for a fresh code.\n"
        f"\n"
    )
    return web.Response(text=text, content_type="text/plain", charset="utf-8")


# ── Main ─────────────────────────────────────────────────────────────


def main():
    port = int(os.environ.get("PAIRD_PORT", "8643"))
    app = web.Application()
    app.router.add_get("/", handle_web_ui)
    app.router.add_get("/qrcode", handle_qrcode_page)
    app.router.add_get("/discover", handle_discover)
    app.router.add_post("/register", handle_register)
    app.router.add_get("/session/{session}", handle_session_status)
    app.router.add_post("/initiate", handle_initiate)
    app.router.add_post("/claim", handle_claim)
    app.router.add_get("/qr-session/{session}", handle_qr_session_data)
    app.router.add_get("/qr-ascii", handle_qr_ascii)

    config = _load_server_config()
    if config["secret_key"]:
        logger.info("Loaded Hermes config — API: %s", config["api_url"])
    else:
        logger.warning("No CADUX_SECRET_KEY found! Pairing will produce unusable config.")

    logger.info("Pairing daemon starting on port %d", port)
    web.run_app(app, host="0.0.0.0", port=port, print=lambda _: None)


if __name__ == "__main__":
    main()
