"""Cadux pairing — LAN discovery + auto-connect.

Single-tap flow: discover paird on LAN → fetch config → create profile.

Discovery tries in order:
  1. UDP broadcast (fast, ~1s)
  2. HTTP subnet probe (scans LAN IPs, ~3-4s)
"""

import asyncio
import json
import logging
import socket

import aiohttp
import flet as ft

from src.profiles import create_profile, set_active_profile_id

logger = logging.getLogger(__name__)

_PAIRD_PORT = 8643
_UDP_BROADCAST_MSG = b"CADUX_DISCOVER"

# ── QR Decryption (matches paird/server.py _encrypt) ──────────────

import base64
import hashlib
import json


def decrypt_blob(blob: str, code: str) -> dict | None:
    """Decrypt a config blob using the 4-char code.

    Encryption scheme (from paird/server.py _encrypt):
        key = sha256(code.encode())
        encrypted = data[i] XOR key[i % 32]
        blob  = base64(encrypted) + ":" + md5(original_data)

    Returns {api_url, secret_key} or None on failure.
    """
    try:
        if ":" in blob:
            enc_part, expected_md5 = blob.rsplit(":", 1)
        else:
            enc_part, expected_md5 = blob, None

        encrypted = base64.b64decode(enc_part)
        key = hashlib.sha256(code.encode()).digest()
        data = bytes(encrypted[i] ^ key[i % len(key)] for i in range(len(encrypted)))

        if expected_md5 and hashlib.md5(data).hexdigest() != expected_md5:
            return None

        config = json.loads(data)
        if config.get("api_url") and config.get("secret_key"):
            return config
    except Exception:
        pass
    return None


# ── LAN IP Detection ────────────────────────────────────────────────


def _get_local_ip() -> str | None:
    """Get the device's LAN IP by attempting a UDP connection."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.1)
        s.connect(("192.168.0.1", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return None


def _subnet_from_ip(ip: str) -> str | None:
    """Extract subnet prefix, e.g. '192.168.0' from '192.168.0.70'."""
    parts = ip.split(".")
    if len(parts) == 4:
        return ".".join(parts[:3])
    return None


# ── Phase 1: UDP Broadcast ──────────────────────────────────────────


async def _udp_discover(timeout: float = 2.0, target_ip: str | None = None) -> dict | None:
    """Sends CADUX_DISCOVER UDP broadcast and waits for a response."""
    loop = asyncio.get_running_loop()
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(timeout)

        dest = (target_ip, _PAIRD_PORT) if target_ip else ("255.255.255.255", _PAIRD_PORT)
        sock.sendto(_UDP_BROADCAST_MSG, dest)

        start = loop.time()
        while (loop.time() - start) < timeout:
            try:
                data, addr = sock.recvfrom(1024)
                info = json.loads(data.decode())
                if info.get("service") == "cadux-paird":
                    host = info.get("host") or addr[0]
                    port = info.get("port", _PAIRD_PORT)
                    sock.close()
                    return {"host": host, "port": port}
            except (socket.timeout, json.JSONDecodeError, UnicodeDecodeError, OSError):
                continue
        sock.close()
    except Exception:
        return None
    return None


# ── Phase 2: HTTP Subnet Probe ──────────────────────────────────────


async def _probe_host(session: aiohttp.ClientSession, ip: str, port: int) -> dict | None:
    """Try GET /discover on one host. Returns {host, port} if paird responds."""
    try:
        async with session.get(f"http://{ip}:{port}/discover", timeout=aiohttp.ClientTimeout(total=0.5)) as resp:
            if resp.status == 200:
                body = await resp.json()
                if body.get("service") == "cadux-paird":
                    return {"host": ip, "port": port}
    except Exception:
        pass
    return None


async def _http_subnet_probe(subnet: str, port: int = _PAIRD_PORT, timeout: float = 6.0) -> dict | None:
    """Probe all IPs in a /24 subnet for paird.

    Probes 253 IPs concurrently (limited by the connector's 30 concurrent
    connections). Returns as soon as one responds with ``cadux-paird``,
    cancels the rest.
    """
    connector = aiohttp.TCPConnector(force_close=True, limit=30, limit_per_host=1)
    async with aiohttp.ClientSession(connector=connector) as session:
        ips = [f"{subnet}.{i}" for i in range(1, 255)]
        tasks = [_probe_host(session, ip, port) for ip in ips]
        done, pending = await asyncio.wait(tasks, timeout=timeout, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            result = task.result()
            if result:
                for p in pending:
                    p.cancel()
                return result
    return None


# ── Fetch Config from paird ─────────────────────────────────────────


async def _fetch_config(host: str, port: int) -> dict | None:
    """GET /config from paird. Returns {api_url, secret_key} or None."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"http://{host}:{port}/config", timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status == 200:
                    body = await resp.json()
                    if body.get("api_url") and body.get("secret_key"):
                        return body
    except Exception:
        pass
    return None


# ── Full Auto-Discovery + Connect ───────────────────────────────────


async def discover_and_connect(page: ft.Page) -> bool:
    """Discover paird on LAN and auto-connect.

    Shows a modal dialog with progress. Returns True on success.
    One-tap from the user's perspective.
    """
    status_text = ft.Text("Finding Hermes on your network…", size=14)
    spinner = ft.ProgressRing(width=24, height=24)
    error_text = ft.Text("", size=13, color=ft.Colors.ERROR)
    manual_ip = ft.TextField(label="IP Address", hint_text="e.g. 192.168.0.83", width=280)
    manual_button = ft.ElevatedButton("Connect to this IP")

    content_col = ft.Column(
        [ft.Row([spinner, status_text], spacing=10)],
        spacing=10, tight=True, width=360,
    )

    dialog = ft.AlertDialog(title=ft.Text("🔗 Connect to Hermes"), content=content_col)
    page.show_dialog(dialog)
    page.update()

    # ── Phase 1: UDP broadcast ──────────────────────────────────
    paird = await _udp_discover(timeout=1.5)

    # ── Phase 2: HTTP subnet probe ──────────────────────────────
    if paird is None:
        local_ip = _get_local_ip()
        subnet = _subnet_from_ip(local_ip) if local_ip else None
        if subnet:
            status_text.value = f"Scanning {subnet}.x…"
            page.update()
            paird = await _http_subnet_probe(subnet, timeout=3.0)

    # ── Result ──────────────────────────────────────────────────
    if paird is None:
        status_text.value = "Could not find Hermes on your network"
        status_text.color = ft.Colors.ERROR
        spinner.visible = False

        async def _try_manual(e):
            ip = manual_ip.value.strip()
            if not ip:
                return
            status_text.value = f"Checking {ip}:{_PAIRD_PORT}…"
            status_text.color = ft.Colors.ON_SURFACE
            spinner.visible = True
            page.update()
            found = await _udp_discover(target_ip=ip, timeout=1.0)
            if found is None:
                found = await _probe_host(
                    aiohttp.ClientSession(), ip, _PAIRD_PORT
                ) if ip else None
            if found is None:
                status_text.value = f"No response from {ip}:{_PAIRD_PORT}"
                status_text.color = ft.Colors.ERROR
                spinner.visible = False
                page.update()
                return
            await _do_connect(page, found, status_text, spinner, error_text)

        manual_button.on_click = lambda e: page.run_task(_try_manual, e)
        content_col.controls = [status_text, error_text, manual_ip, manual_button]
        page.update()
        return False

    return await _do_connect(page, paird, status_text, spinner, error_text)


async def _do_connect(page, paird, status_text, spinner, error_text) -> bool:
    """Fetch config from paird and save as profile."""
    host, port = paird["host"], paird["port"]
    status_text.value = f"Connecting to {host}…"
    status_text.color = ft.Colors.GREEN
    page.update()

    config = await _fetch_config(host, port)
    if config is None:
        status_text.value = f"Connected to {host} but couldn't get config"
        status_text.color = ft.Colors.ERROR
        spinner.visible = False
        page.update()
        return False

    # Save as profile and connect
    profile = create_profile(
        page, name=f"Hermes ({host})",
        api_url=config["api_url"],
        secret_key=config["secret_key"],
    )
    set_active_profile_id(page, profile.id)

    status_text.value = "✅ Connected!"
    status_text.color = ft.Colors.GREEN
    spinner.visible = False
    page.update()

    await asyncio.sleep(0.8)
    try:
        page.pop_dialog()
    except Exception:
        pass
    page.clean()
    from src.main import main
    main(page)
    return True
