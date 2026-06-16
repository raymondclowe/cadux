"""Cadux pairing — LAN discovery, PIN registration, config decryption.

Handles the Cadux side of the ephemeral PIN pairing flow:
  1. Discover paird on the LAN via UDP broadcast
  2. Register with the PIN the user typed
  3. Decrypt and verify the returned Hermes config
  4. Save as a profile and trigger connect
"""

import asyncio
import base64
import hashlib
import json
import logging
import socket

import flet as ft

from src.profiles import create_profile, set_active_profile_id

logger = logging.getLogger(__name__)

_PAIRD_PORT = 8643
_UDP_BROADCAST_MSG = b"CADUX_DISCOVER"
_UDP_TIMEOUT = 3.0


# ── Decryption (mirrors paird/server.py) ──────────────────────────────


def decrypt_config(encrypted_b64: str, password: str, expected_md5: str | None = None) -> dict | None:
    """XOR-decrypt a config blob with the given password.

    Returns ``{api_url, secret_key}`` on success, or ``None`` if
    verification fails.
    """
    key = hashlib.sha256(password.upper().encode()).digest()
    raw = base64.b64decode(encrypted_b64)
    plain = bytes(raw[i] ^ key[i % len(key)] for i in range(len(raw)))

    if expected_md5:
        actual_md5 = hashlib.md5(plain).hexdigest()
        if actual_md5 != expected_md5:
            logger.warning("MD5 mismatch — expected %s, got %s", expected_md5, actual_md5)
            return None

    config = json.loads(plain)
    return {"api_url": config["api_url"], "secret_key": config["secret_key"]}


# ── LAN Discovery via UDP Broadcast ──────────────────────────────────


async def discover_paird(timeout: float = _UDP_TIMEOUT, target_ip: str | None = None) -> dict | None:
    """Discover a Cadux paird instance on the LAN.

    Sends a ``CADUX_DISCOVER`` UDP broadcast to port 8643.
    If *target_ip* is provided, sends directly to that IP instead.

    Returns ``{"host": ip, "port": port}`` or ``None``.
    """
    loop = asyncio.get_running_loop()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(timeout)

    if target_ip:
        sock.sendto(_UDP_BROADCAST_MSG, (target_ip, _PAIRD_PORT))
    else:
        sock.sendto(_UDP_BROADCAST_MSG, ("255.255.255.255", _PAIRD_PORT))

    start = loop.time()
    while (loop.time() - start) < timeout:
        try:
            data = await loop.sock_recv(sock, 1024)
            # sock_recv may return (data, addr) on Unix or just data on Windows
            if isinstance(data, tuple):
                data, addr = data
            info = json.loads(data.decode())
            if info.get("service") == "cadux-paird":
                host = info.get("host") or "127.0.0.1"
                port = info.get("port", _PAIRD_PORT)
                sock.close()
                return {"host": host, "port": port}
        except (socket.timeout, json.JSONDecodeError, UnicodeDecodeError, OSError):
            continue

    sock.close()
    return None


# ── Registration with paird ──────────────────────────────────────────


async def register_with_paird(host: str, port: int, pin: str) -> dict:
    """POST /register to paird with the PIN.

    Returns the response dict. Success looks like:
    ``{"session_id": "...", "status": "ready",
       "config_encrypted": "...", "md5_sig": "..."}``
    """
    import aiohttp

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(f"http://{host}:{port}/register", json={"code": pin}) as resp:
                body = await resp.json()
                if resp.status == 200:
                    return body
                if resp.status == 403:
                    return {"error": "wrong_code"}
                return body | {"error": body.get("error", "unknown")}
    except (aiohttp.ClientConnectorError, OSError):
        return {"error": "not_found"}
    except Exception as exc:
        return {"error": str(exc)}


# ── Full Pairing Flow ────────────────────────────────────────────────


async def pairing_flow(page: ft.Page) -> bool:
    """Orchestrate the full pairing flow inside a modal dialog.

    1. Discovers paird on the LAN via UDP broadcast
    2. Shows PIN entry UI
    3. Registers with PIN
    4. Decrypts config
    5. Saves as a profile → caller rebuilds UI

    Returns True on success, False on failure.
    """
    status_text = ft.Text("Searching for Hermes on your local network…", size=14)
    spinner = ft.ProgressRing(width=24, height=24)
    error_text = ft.Text("", size=13, color=ft.Colors.ERROR)
    manual_ip = ft.TextField(label="IP Address", hint_text="e.g. 192.168.0.83", width=280, visible=False)
    manual_link = ft.TextButton("Enter Manually", visible=False)

    content_col = ft.Column(
        [ft.Row([spinner, status_text], spacing=10)],
        spacing=10, tight=True, width=360,
    )

    dialog = ft.AlertDialog(title=ft.Text("📱 Set Up Connection"), content=content_col)
    page.show_dialog(dialog)
    page.update()

    # ── Discover paird ──────────────────────────────────────────────
    paird = await discover_paird()

    if paird is None:
        status_text.value = "Could not find Hermes on your network."
        status_text.color = ft.Colors.ERROR
        spinner.visible = False

        async def _retry_manual(e):
            ip = manual_ip.value.strip()
            if not ip:
                return
            status_text.value = f"Checking {ip}:{_PAIRD_PORT}…"
            status_text.color = ft.Colors.ON_SURFACE
            spinner.visible = True
            manual_ip.visible = False
            manual_link.visible = False
            error_text.value = ""
            page.update()
            found = await discover_paird(target_ip=ip)
            if found is None:
                status_text.value = f"No response from {ip}:{_PAIRD_PORT}."
                status_text.color = ft.Colors.ERROR
                spinner.visible = False
                manual_ip.visible = True
                manual_link.visible = True
                page.update()
                return
            await _show_pin_entry(page, dialog, content_col, found, status_text, spinner, error_text, manual_ip, manual_link)

        manual_btn = ft.ElevatedButton("Try Manual IP")
        manual_btn.on_click = lambda e: page.run_task(_retry_manual, e)
        manual_link.on_click = lambda e: (
            setattr(manual_ip, "visible", True)
            or setattr(manual_link, "visible", False)
            or page.update()
        )
        manual_link.visible = True

        content_col.controls = [status_text, error_text, manual_ip, manual_btn, manual_link]
        page.update()
        return False

    return await _show_pin_entry(page, dialog, content_col, paird, status_text, spinner, error_text, manual_ip, manual_link)


async def _show_pin_entry(page, dialog, content_col, paird, status_text, spinner, error_text, manual_ip, manual_link):
    """Show PIN entry after discovery success."""
    host, port = paird["host"], paird["port"]
    status_text.value = f"Found Hermes at {host}"
    status_text.color = ft.Colors.GREEN
    spinner.visible = False

    from src.chat_ui import build_pin_entry

    async def _on_pin_submit(pin: str):
        status_text.value = f"Connecting to {host}:{port}…"
        status_text.color = ft.Colors.ON_SURFACE
        error_text.value = ""
        page.update()

        result = await register_with_paird(host, port, pin)

        if result.get("error") == "wrong_code":
            error_text.value = "Wrong code — check the code Hermes gave you"
            page.update()
            return

        if result.get("error") or result.get("status") != "ready":
            error_text.value = f"Pairing failed: {result.get('error', 'unknown')}"
            manual_ip.visible = True
            manual_link.visible = True
            page.update()
            return

        encrypted = result.get("config_encrypted", "")
        md5_sig = result.get("md5_sig", "")
        config = decrypt_config(encrypted, pin, md5_sig)
        if config is None:
            error_text.value = "Could not decrypt config — try again"
            page.update()
            return

        # Save profile and reconnect
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

    pin_widget = build_pin_entry(page=page, on_submit=_on_pin_submit)
    content_col.controls = [status_text, pin_widget, error_text]
    page.update()
    return True