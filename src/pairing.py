"""
Cadux pairing client — auto-discover and pair with Hermes on the LAN.

Flow (v2, Hermes-initiated):
  1. ``scan()`` — probe local subnet for pairing daemons
  2. ``PairingSession(url).register()`` — register intent; returns session_id
  3. User tells Hermes "Pair with cadux" → Hermes calls paird /initiate
  4. ``session.poll()`` — blocking poll until Hermes initiates (every 2s, 120s max)
  5. Returns {codes, config_encrypted, md5_sig}
  6. ``session.try_code(code)`` — XOR-decrypt config, verify MD5
  7. Returns config dict on success, None on wrong code
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


async def scan(
    timeout: float = 15.0,
    port: int | None = None,
    *,
    progress_callback: callable | None = None,
) -> list[dict]:
    """Scan local subnet for paird servers.

    Limits concurrent probes to avoid overwhelming mobile network stacks
    on Android.  Reports progress via *progress_callback(completed, total)*.

    Returns a list of discovered servers::
        [{"url": "http://192.168.0.83:8643", "ip": "192.168.0.83", "version": "1.0"}, …]
    """
    port = port or _PAIRD_PORT
    targets = _get_scan_targets()
    total = len(targets)
    logger.info("Scanning %d IPs on port %d …", total, port)

    # Limit concurrent outbound connections so mobile NICs aren't swamped
    sem = asyncio.Semaphore(20)

    async def _probe(session, ip):
        async with sem:
            try:
                async with session.get(
                    f"http://{ip}:{port}/discover",
                    timeout=aiohttp.ClientTimeout(total=2.0),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        logger.info("Found paird at %s:%d", ip, port)
                        return {"url": f"http://{ip}:{port}", "ip": ip, **data}
            except (asyncio.TimeoutError, OSError, Exception):
                pass
            return None

    found: list[dict] = []
    completed = 0

    async with aiohttp.ClientSession() as session:
        tasks = [_probe(session, ip) for ip in targets]

        try:
            for coro in asyncio.as_completed(tasks, timeout=timeout):
                try:
                    result = await coro
                    if result:
                        found.append(result)
                except (TimeoutError, asyncio.TimeoutError):
                    logger.warning("Scan timed out before all IPs were probed")
                    break
                completed += 1
                if progress_callback:
                    progress_callback(completed, total)
        except (TimeoutError, asyncio.TimeoutError):
            logger.warning("Scan timed out before all IPs were probed")
        # as_completed timeout raises outside the loop; session.cleanup()
        # runs on __aexit__ even if we break early

    return found


# ── Pairing session (v2: Hermes-initiated) ──────────────────────────


class PairingSession:
    """Manages a pairing session with Hermes-initiated flow.

    Usage::

        session = PairingSession("http://192.168.0.83:8643")
        sid = await session.register()               # step 1: register
        # user says "Pair with cadux" to Hermes ...
        result = await session.poll()                # step 2: poll until ready
        # 6 codes shown on screen, user taps one ...
        config = session.try_code("ABC")             # step 3: decrypt + verify
        if config:
            # paired!
        else:
            # wrong code
    """

    def __init__(self, daemon_url: str):
        self.daemon_url = daemon_url.rstrip("/")
        self.session_id: str | None = None
        self._http: aiohttp.ClientSession | None = None
        self._codes: list[str] = []
        self._config_encrypted: str | None = None
        self._md5_sig: str | None = None

    async def _ensure_http(self):
        if self._http is None:
            self._http = aiohttp.ClientSession()

    async def close(self):
        if self._http:
            await self._http.close()
            self._http = None

    async def register(self) -> str:
        """Register pairing intent. Returns session_id."""
        await self._ensure_http()
        async with self._http.post(
            f"{self.daemon_url}/register",
            json={},
        ) as resp:
            data = await resp.json()
            self.session_id = data["session_id"]
            logger.info("Registered session %s", self.session_id[:8])
            return self.session_id

    async def poll(self, timeout: float = 120.0, interval: float = 2.0) -> dict | None:
        """Poll until Hermes initiates pairing.

        Returns {codes, config_encrypted, md5_sig} or None on timeout.
        """
        if not self.session_id:
            raise RuntimeError("Call register() first")

        await self._ensure_http()
        deadline = asyncio.get_event_loop().time() + timeout

        while asyncio.get_event_loop().time() < deadline:
            async with self._http.get(
                f"{self.daemon_url}/session/{self.session_id}"
            ) as resp:
                if resp.status != 200:
                    await asyncio.sleep(interval)
                    continue
                data = await resp.json()
                if data.get("status") == "ready":
                    self._codes = data["codes"]
                    self._config_encrypted = data["config_encrypted"]
                    self._md5_sig = data["md5_sig"]
                    return {
                        "codes": data["codes"],
                        "config_encrypted": data["config_encrypted"],
                        "md5_sig": data["md5_sig"],
                    }
            await asyncio.sleep(interval)

        logger.warning("Poll timed out after %ds", timeout)
        return None

    @property
    def codes(self) -> list[str]:
        """The 6 codes (only available after poll() returns)."""
        return self._codes

    def try_code(self, code: str) -> dict | None:
        """Try a code: XOR-decrypt config, verify MD5.

        Returns config dict {api_url, secret_key}, or None if wrong code.
        """
        if not self._config_encrypted or not self._md5_sig:
            raise RuntimeError("Call poll() first to get encrypted data")

        decrypted = _decrypt(self._config_encrypted, code)
        md5 = hashlib.md5(decrypted).hexdigest()

        if md5 != self._md5_sig:
            return None

        return json.loads(decrypted.decode("utf-8"))

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()
