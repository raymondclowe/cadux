"""Cadux pairing — QR code deep-link flow.

New flow:
  1. Hermes generates a QR code containing ``cadux://connect?url=&key=``
  2. User scans it with their phone camera
  3. Android opens Cadux via the ``cadux://`` intent
  4. Cadux parses the URL, creates a profile, connects

No LAN scanning, no UDP broadcasts, no subnet probes, no PIN codes.
"""

import asyncio
import json
import logging
import urllib.parse

import flet as ft

from src.profiles import create_profile, set_active_profile_id

logger = logging.getLogger(__name__)


# ── Deep Link Parsing ──────────────────────────────────────────────


def parse_deeplink(url: str) -> dict | None:
    """Parse a ``cadux://`` deep link URL.

    Expected format::

        cadux://connect?url=<api_url>&key=<secret_key>

    Both values are URL-encoded. Returns ``{api_url, secret_key}``
    or ``None`` if the URL is invalid.
    """
    if not url or not url.startswith("cadux://"):
        return None

    try:
        parsed = urllib.parse.urlparse(url)
        params = urllib.parse.parse_qs(parsed.query)
        api_url = params.get("url", [None])[0]
        secret_key = params.get("key", [None])[0]
        if api_url and secret_key:
            return {"api_url": api_url, "secret_key": secret_key}
    except Exception:
        pass
    return None


def build_deeplink(api_url: str, secret_key: str) -> str:
    """Build a ``cadux://`` deep link URL from Hermes config."""
    encoded_url = urllib.parse.quote(api_url, safe="")
    encoded_key = urllib.parse.quote(secret_key, safe="")
    return f"cadux://connect?url={encoded_url}&key={encoded_key}"


# ── Connect from Deep Link ─────────────────────────────────────────


async def connect_from_deeplink(page: ft.Page, config: dict) -> bool:
    """Create a profile from deep-link config and rebuild UI.

    Shows a brief "Connecting…" dialog, saves the profile, and
    re-renders the main UI.
    """
    dialog = ft.AlertDialog(
        title=ft.Text("🔗 Connecting…"),
        content=ft.Column(
            [ft.ProgressRing(width=24, height=24), ft.Text("Saving profile…", size=14)],
            spacing=10, horizontal_alignment=ft.CrossAxisAlignment.CENTER, tight=True,
        ),
    )
    page.show_dialog(dialog)
    page.update()
    await asyncio.sleep(0.3)

    profile = create_profile(
        page,
        name=f"Hermes ({config['api_url']})",
        api_url=config["api_url"],
        secret_key=config["secret_key"],
    )
    set_active_profile_id(page, profile.id)

    try:
        page.pop_dialog()
    except Exception:
        pass
    page.clean()
    from src.main import main
    main(page)
    return True


# ── Settings dialog shortcut ───────────────────────────────────────


def show_settings_from_deeplink(page: ft.Page):
    """Open the settings dialog when a deep link provides partial config."""
    from src.main import _show_settings_dialog
    _show_settings_dialog(page)
