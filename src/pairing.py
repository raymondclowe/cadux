"""
Cadux pairing client — auto-discover and pair with Hermes on the LAN.

Flow:
  1. ``scan()`` — probe the local subnet for pairing daemons (port 8643)
  2. ``PairingSession(url).start()`` — request a session; returns 3 codes
  3. Cadux shows the 3 codes to the user
  4. User taps one → ``session.confirm(code)`` POSTs to daemon
  5. If correct → daemon encrypts config with that code, client decrypts
  6. If wrong → daemon returns 403, client gets ``None``
"""

import asyncio
import base64
import hashlib
import json
import logging
import os
import socket

import aiohttp

logger = logging.getLogger(__name__)

_PAIRD_PORT = int(os.environ.get("PAIRD_PORT", "8643"))


# ── Encryption (mirrors paird/server.py) ─────────────────────────────


def _decrypt(encoded: str, password: str) -> bytes:
    key = hashlib.sha256(password.encode()).digest()
    raw = base64.b64decode(encoded)
    return bytes(raw[i] ^ key[i % len(key)] for i in range(len(raw)))


# ── LAN utilities ────────────────────────────────────────────────────


def _get_local_ip() -> str:
    """Get the device's LAN IP address."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.1)
        s.connect(("192.168.0.1", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def _get_scan_targets() -> list[str]:
    """Generate candidate IPs on the local subnet (max 255)."""
    ip = _get_local_ip()
    if ip == "127.0.0.1":
        return ["127.0.0.1"]
    parts = ip.split(".")
    subnet = f"{parts[0]}.{parts[1]}.{parts[2]}."
    return [f"{subnet}{i}" for i in range(1, 256)]


# ── Discovery ────────────────────────────────────────────────────────


async def scan(timeout: float = 3.0, port: int | None = None) -> list[dict]:
    """Scan local subnet for paird servers.

    Returns a list of discovered servers::
        [{"url": "http://192.168.0.83:8643", "ip": "192.168.0.83", "version": "1.0"}, …]
    """
    port = port or _PAIRD_PORT
    targets = _get_scan_targets()
    logger.info("Scanning %d IPs on port %d …", len(targets), port)

    async def _probe(session, ip):
        try:
            async with session.get(
                f"http://{ip}:{port}/discover",
                timeout=aiohttp.ClientTimeout(total=0.8),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    logger.info("Found paird at %s:%d", ip, port)
                    return {"url": f"http://{ip}:{port}", "ip": ip, **data}
        except (asyncio.TimeoutError, OSError, Exception):
            pass
        return None

    async with aiohttp.ClientSession() as session:
        tasks = [_probe(session, ip) for ip in targets]
        results = await asyncio.gather(*tasks)

    found = [r for r in results if r]
    return found


# ── Pairing session ──────────────────────────────────────────────────


class PairingSession:
    """Manages a pairing session with a discovered daemon.

    Usage::

        session = PairingSession("http://192.168.0.83:8643")
        codes = await session.start()            # [3 codes]
        # … show codes, user picks one …
        config = await session.confirm(picked)   # POST /confirm -> decrypt
        if config:
            # correct code! config ready to apply
        else:
            # wrong code
    """

    def __init__(self, daemon_url: str):
        self.daemon_url = daemon_url.rstrip("/")
        self.session_id: str | None = None
        self.codes: list[str] = []
        self._http: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._http is None:
            self._http = aiohttp.ClientSession()
        return self._http

    async def start(self) -> list[str]:
        """Start a new pairing session. Returns the 3 candidate codes."""
        http = await self._get_session()
        async with http.post(f"{self.daemon_url}/start") as resp:
            if resp.status != 200:
                raise RuntimeError(f"paird /start returned {resp.status}")
            data = await resp.json()
        self.codes = data["codes"]
        self.session_id = data.get("session")  # for confirm endpoint
        logger.info("Pairing started — session=%s, codes: %s", self.session_id[:8] if self.session_id else "?", self.codes)
        return self.codes

    async def confirm(self, code: str) -> dict | None:
        """Send *code* to daemon for confirmation.

        If the server says it's correct, we receive the encrypted config
        and decrypt it locally. Returns the config dict, or ``None`` if
        the code was wrong.
        """
        http = await self._get_session()
        try:
            async with http.post(
                f"{self.daemon_url}/confirm/{self.session_id}",
                json={"code": code},
            ) as resp:
                if resp.status == 403:
                    return None  # wrong code
                if resp.status == 404:
                    raise RuntimeError("Pairing session expired")
                if resp.status != 200:
                    raise RuntimeError(f"confirm returned {resp.status}")
                data = await resp.json()
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            raise RuntimeError(f"Network error during confirm: {e}")

        encrypted = data["config_encrypted"]
        raw = _decrypt(encrypted, code)
        config = json.loads(raw)
        logger.info("Code confirmed! Config — API: %s", config.get("api_url"))
        return config

    async def close(self):
        if self._http:
            await self._http.close()
            self._http = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()
