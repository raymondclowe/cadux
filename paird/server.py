"""
Cadux Pairing Daemon — ephemeral companion server for Hermes.

Runs at the user's command (via Hermes agent skill), not as a daemon.
Binds for a configurable TTL (default 60 s), then exits.

NEW SIMPLE FLOW (no PIN needed):
  Hermes starts paird → Cadux taps "Find Hermes" → auto-connects

Quick start on Hermes host:
    cd paird
    CADUX_API_URL=http://localhost:8642 CADUX_SECRET_KEY=sk-... \
        uv run server.py

Endpoints:
    GET  /discover      JSON identity for auto-discovery
    GET  /config        Returns config directly (no PIN, no encrypt)
    POST /register      PIN mode only — register with code → encrypted config
    GET  /session/{id}  Poll session state
"""

import argparse
import asyncio
import base64
import hashlib
import json
import logging
import os
import socket
import sys
import threading
import time
import uuid

from aiohttp import web

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("paird")

# ── Globals ──────────────────────────────────────────────────────────

_PREAUTHORIZED_PIN: str | None = None
_TTL: int = 60
_sessions: dict[str, dict] = {}
_claim_event: threading.Event | None = None
_shutdown_called = False

_CHARS = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def _get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.1)
        s.connect(("192.168.0.1", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def _load_server_config() -> dict:
    api_url = os.environ.get(
        "CADUX_API_URL", os.environ.get("HERMES_API_URL", "http://localhost:8642")
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
    key = hashlib.sha256(password.encode()).digest()
    enc = bytes(data[i] ^ key[i % len(key)] for i in range(len(data)))
    md5_sig = hashlib.md5(data).hexdigest()
    return base64.b64encode(enc).decode(), md5_sig


# ── CORS Middleware (needed for Cadux HTTP probe) ────────────────────


@web.middleware
async def cors_middleware(request, handler):
    """Allow cross-origin requests from any origin (LAN-only)."""
    if request.method == "OPTIONS":
        resp = web.Response()
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
        return resp
    resp = await handler(request)
    resp.headers["Access-Control-Allow-Origin"] = "*"
    return resp


# ── UDP Broadcast Responder ─────────────────────────────────────────


async def _udp_responder(udp_bind_port: int, http_port: int):
    loop = asyncio.get_running_loop()
    transport: asyncio.DatagramTransport | None = None

    class _Protocol(asyncio.DatagramProtocol):
        def connection_made(self, tr):
            nonlocal transport
            transport = tr

        def datagram_received(self, data, addr):
            if data.strip() == b"CADUX_DISCOVER":
                local_ip = _get_local_ip()
                resp = json.dumps({
                    "service": "cadux-paird",
                    "host": local_ip,
                    "port": http_port,
                }).encode()
                transport.sendto(resp, addr)

        def error_received(self, exc):
            logger.debug("UDP error: %s", exc)

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("0.0.0.0", udp_bind_port))
        sock.setblocking(False)
        await loop.create_datagram_endpoint(_Protocol, sock=sock)
        logger.info("UDP responder listening on port %d", udp_bind_port)
    except Exception as exc:
        logger.warning("UDP responder failed to bind: %s", exc)


# ── Route Handlers ──────────────────────────────────────────────────


async def handle_discover(request):
    return web.json_response({
        "service": "cadux-paird",
        "version": "1.0",
        "host": _get_local_ip(),
    })


async def handle_config(request):
    """GET /config — return Hermes config directly (no PIN, plain JSON).
    
    This is the simple path: Cadux discovers paird, hits /config,
    gets {api_url, secret_key}, saves as profile. Done.
    """
    config = _load_server_config()
    if not config["secret_key"]:
        return web.json_response({"error": "CADUX_SECRET_KEY not set"}, status=503)
    return web.json_response(config)


async def handle_register(request):
    """POST /register — PIN mode. Returns encrypted config on PIN match."""
    global _shutdown_called

    config = _load_server_config()
    pin = ""
    try:
        body = await request.json()
        pin = (body.get("code") or body.get("pin") or "").strip().upper()
    except Exception:
        pass

    # If no PIN set on server, this acts like /config but via POST (backward compat)
    if _PREAUTHORIZED_PIN is None:
        # No-PIN mode: return config directly
        if not config["secret_key"]:
            return web.json_response({"error": "CADUX_SECRET_KEY not set"}, status=503)
        session_id = str(uuid.uuid4())
        _sessions[session_id] = {"config": config, "created_at": time.time(), "status": "ready"}
        logger.info("No-PIN claim — session %s", session_id[:8])
        return web.json_response({"session_id": session_id, "status": "ready", **config})

    if not pin:
        return web.json_response({"error": "Missing code"}, status=400)

    if pin != _PREAUTHORIZED_PIN:
        return web.json_response({"error": "Wrong code"}, status=403)

    session_id = str(uuid.uuid4())
    config_json = json.dumps(config).encode()
    config_encrypted, md5_sig = _encrypt(config_json, pin)

    _sessions[session_id] = {
        "config": config,
        "created_at": time.time(),
        "status": "ready",
        "config_encrypted": config_encrypted,
        "md5_sig": md5_sig,
    }

    logger.info("PIN claim — session %s", session_id[:8])

    if _claim_event is not None:
        _claim_event.set()

    return web.json_response({
        "session_id": session_id,
        "status": "ready",
        "config_encrypted": config_encrypted,
        "md5_sig": md5_sig,
    })


async def handle_session_status(request):
    session_id = request.match_info["session"]
    session = _sessions.get(session_id)
    if not session or (time.time() - session["created_at"]) > _TTL:
        return web.json_response({"status": "expired"}, status=404)

    status = session.get("status", "waiting")
    if status == "waiting":
        return web.json_response({"status": "waiting"})

    resp = {"status": "ready"}
    if "config_encrypted" in session:
        resp["config_encrypted"] = session["config_encrypted"]
        resp["md5_sig"] = session["md5_sig"]
    if "config" in session and _PREAUTHORIZED_PIN is None:
        resp.update(session["config"])
    return web.json_response(resp)


# ── TTL Timer ───────────────────────────────────────────────────────


def _start_ttl_timer():
    global _shutdown_called

    def _wait_and_exit():
        global _shutdown_called
        poll_interval = 0.5
        elapsed = 0.0
        while elapsed < _TTL:
            if _claim_event and _claim_event.is_set():
                break
            time.sleep(poll_interval)
            elapsed += poll_interval
        if not _shutdown_called:
            _shutdown_called = True
            logger.info("TTL expired — exiting")
            sys.exit(0)

    t = threading.Thread(target=_wait_and_exit, daemon=True)
    t.start()


# ── Main ─────────────────────────────────────────────────────────────


def main():
    global _PREAUTHORIZED_PIN, _TTL, _claim_event

    parser = argparse.ArgumentParser(description="Cadux ephemeral pairing daemon")
    parser.add_argument("--ttl", type=int, default=60, help="Seconds before auto-exit (default: 60)")
    parser.add_argument("--pin", type=str, default=None, help="Pre-authorized PIN code (optional)")
    args = parser.parse_args()

    _TTL = args.ttl
    if args.pin:
        _PREAUTHORIZED_PIN = args.pin.upper().strip()
        _claim_event = threading.Event()
        logger.info("PIN mode — code: %s", _PREAUTHORIZED_PIN)
    else:
        logger.info("No-PIN mode — any Cadux on the LAN can fetch config")

    port = int(os.environ.get("PAIRD_PORT", "8643"))
    udp_port = int(os.environ.get("PAIRD_UDP_PORT", str(port - 1)))

    config = _load_server_config()
    if config["secret_key"]:
        logger.info("Loaded Hermes config — API: %s", config["api_url"])
    else:
        logger.warning("No CADUX_SECRET_KEY found! Pairing will produce unusable config.")

    app = web.Application(middlewares=[cors_middleware])
    app.router.add_get("/discover", handle_discover)
    app.router.add_get("/config", handle_config)
    app.router.add_post("/register", handle_register)
    app.router.add_get("/session/{session}", handle_session_status)

    app.on_startup.append(lambda _: asyncio.create_task(_udp_responder(udp_port, port)))

    logger.info("Pairing daemon starting on port %d (TTL: %d s, UDP: %d)", port, _TTL, udp_port)
    _start_ttl_timer()

    try:
        web.run_app(app, host="0.0.0.0", port=port)
    except OSError as exc:
        logger.error("Failed to bind port %d: %s", port, exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
