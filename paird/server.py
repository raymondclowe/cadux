"""
Cadux Pairing Daemon — ephemeral companion server for Hermes.

Runs at the user's command (via Hermes agent skill), not as a daemon.
Binds for a configurable TTL (default 60 s), then exits.
When --pin is set, any POST /register with matching PIN immediately
returns the encrypted Hermes config — no polling needed.

Quick start on Hermes host (via Hermes agent skill):
    cd paird
    CADUX_API_URL=http://localhost:8642 CADUX_SECRET_KEY=your-key \\
        uv run server.py --ttl 60 --pin K47M

Endpoints:
    GET  /discover      JSON identity for auto-discovery
    POST /register      Register with PIN → {session_id, status,
                          config_encrypted, md5_sig}
    GET  /session/{id}  Poll for session state
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

_PREAUTHORIZED_PIN: str | None = None  # set via --pin CLI arg
_TTL: int = 60                          # seconds before auto-exit
_sessions: dict[str, dict] = {}         # session_id -> {config, created_at, status, …}
_claim_event: threading.Event | None = None  # set when a claim succeeds
_shutdown_called = False

# ── Helpers ──────────────────────────────────────────────────────────

_CHARS = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no I/O/0/1 for readability


def _get_local_ip() -> str:
    """Best-effort local LAN IP."""
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
    """Load the Hermes API URL and key from the environment."""
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
    """XOR-encrypt with a SHA256-derived key.
    Returns (base64_encrypted, md5_of_plaintext).
    """
    key = hashlib.sha256(password.encode()).digest()
    enc = bytes(data[i] ^ key[i % len(key)] for i in range(len(data)))
    md5_sig = hashlib.md5(data).hexdigest()
    return base64.b64encode(enc).decode(), md5_sig


def _decrypt(encoded: str, password: str) -> bytes:
    """XOR-decrypt with a SHA256-derived key."""
    key = hashlib.sha256(password.encode()).digest()
    raw = base64.b64decode(encoded)
    return bytes(raw[i] ^ key[i % len(key)] for i in range(len(raw)))


# ── UDP Broadcast Responder ─────────────────────────────────────────


async def _udp_responder(udp_bind_port: int, http_port: int):
    """Listen for UDP broadcasts and respond to CADUX_DISCOVER pings."""
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


async def handle_register(request):
    """Register with a PIN. If PIN matches --pin, returns ready config immediately."""
    global _shutdown_called

    config = _load_server_config()
    pin = ""
    try:
        body = await request.json()
        pin = (body.get("code") or body.get("pin") or "").strip().upper()
    except Exception:
        pass

    if not pin:
        return web.json_response({"error": "Missing code"}, status=400)

    # PIN-preauthorize mode
    if _PREAUTHORIZED_PIN is not None:
        if pin != _PREAUTHORIZED_PIN:
            return web.json_response({"error": "Wrong code"}, status=403)

        # PIN matches — encrypt and return config immediately
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

        logger.info("Pairing claimed — session %s", session_id[:8])

        # Signal early exit
        if _claim_event is not None:
            _claim_event.set()

        return web.json_response({
            "session_id": session_id,
            "status": "ready",
            "config_encrypted": config_encrypted,
            "md5_sig": md5_sig,
        })

    # Fallback (no PIN set): create waiting session
    session_id = str(uuid.uuid4())
    _sessions[session_id] = {
        "config": config,
        "created_at": time.time(),
        "status": "waiting",
    }
    logger.info("Registration (no PIN mode) — session %s", session_id[:8])
    return web.json_response({"session_id": session_id, "status": "waiting"})


async def handle_session_status(request):
    """Poll session state."""
    session_id = request.match_info["session"]
    session = _sessions.get(session_id)
    if not session or (time.time() - session["created_at"]) > _TTL:
        return web.json_response({"status": "expired"}, status=404)

    status = session.get("status", "waiting")
    if status == "waiting":
        return web.json_response({"status": "waiting"})

    return web.json_response({
        "status": "ready",
        "config_encrypted": session["config_encrypted"],
        "md5_sig": session["md5_sig"],
    })


# ── TTL Timer (threading-based to avoid Windows asyncio issue) ───────


def _start_ttl_timer():
    """Exit the process after TTL seconds, or early if claimed.

    Uses a timer thread instead of an asyncio task because creating
    long-lived background tasks during ``on_startup`` prevents the
    aiohttp TCP server from binding on Windows + Python 3.14.
    """
    global _shutdown_called

    def _wait_and_exit():
        global _shutdown_called
        poll_interval = 0.5
        elapsed = 0.0
        while elapsed < _TTL:
            if _claim_event.is_set():
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
    parser.add_argument("--pin", type=str, default=None, help="Pre-authorized PIN code")
    args = parser.parse_args()

    _TTL = args.ttl
    _PREAUTHORIZED_PIN = args.pin.upper().strip() if args.pin else None
    _claim_event = threading.Event()

    port = int(os.environ.get("PAIRD_PORT", "8643"))
    udp_port = int(os.environ.get("PAIRD_UDP_PORT", str(port - 1)))  # default: one less than HTTP

    config = _load_server_config()
    if config["secret_key"]:
        logger.info("Loaded Hermes config — API: %s", config["api_url"])
    else:
        logger.warning("No CADUX_SECRET_KEY found! Pairing will produce unusable config.")

    if _PREAUTHORIZED_PIN:
        logger.info("PIN mode active — code: %s", _PREAUTHORIZED_PIN)
    else:
        logger.info("No PIN set — register will create waiting sessions")

    app = web.Application()
    app.router.add_get("/discover", handle_discover)
    app.router.add_post("/register", handle_register)
    app.router.add_get("/session/{session}", handle_session_status)

    # Start UDP responder as a fast startup task (completes quickly)
    app.on_startup.append(lambda _: asyncio.create_task(_udp_responder(udp_port, port)))

    logger.info("Pairing daemon starting on port %d (TTL: %d s, UDP: %d)", port, _TTL, udp_port)

    # Start TTL via thread (Windows asyncio issue: long-lived background
    # tasks in on_startup block the TCP server from binding)
    _start_ttl_timer()

    try:
        web.run_app(app, host="0.0.0.0", port=port)
    except OSError as exc:
        logger.error("Failed to bind port %d: %s", port, exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
