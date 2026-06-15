import asyncio
import logging
import sys

import flet as ft

from src import chat_ui
from src.config import load_config

logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main(page: ft.Page):
    page.title = "Cadux"
    page.theme_mode = ft.ThemeMode.SYSTEM
    page.theme = ft.Theme(color_scheme_seed="indigo")
    page.padding = 4

    # ── Config ───────────────────────────────────────────────────────
    config = load_config(page)
    page.session.store.set("_config", config)

    # ── Refs ─────────────────────────────────────────────────────────
    status_dot = ft.Container(
        width=10,
        height=10,
        border_radius=5,
        bgcolor="grey",
        tooltip="Disconnected",
    )
    session_dropdown = ft.Dropdown(
        text_size=12,
        label="Session",
        expand=True,
    )
    model_dropdown = ft.Dropdown(
        text_size=12,
        label="Model",
        expand=True,
    )
    sessions_list = []

    # ── Unconfigured Banner ──────────────────────────────────────────
    missing_banner = None
    if config is None:
        missing_banner = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.WARNING_AMBER_ROUNDED, size=18, color=ft.Colors.ON_ERROR_CONTAINER),
                            ft.Text(
                                "Not configured — open Settings or auto-discover",
                                size=13,
                                color=ft.Colors.ON_ERROR_CONTAINER,
                                expand=True,
                            ),
                        ],
                        spacing=6,
                    ),
                    ft.ElevatedButton(
                        "🔍 Find Server",
                        icon=ft.Icons.SEARCH,
                        on_click=lambda e: page.run_task(_pairing_flow, page),
                        style=ft.ButtonStyle(text_style=ft.TextStyle(size=12)),
                    ),
                ],
                spacing=6,
            ),
            bgcolor=ft.Colors.ERROR_CONTAINER,
            padding=ft.padding.Padding.symmetric(horizontal=12, vertical=8),
            border_radius=6,
            margin=ft.margin.Margin.only(bottom=4),
        )

    # ── UI Components ────────────────────────────────────────────────
    chat_column = chat_ui.build_chat_column()
    empty_state = chat_ui.build_empty_state()

    # Send callback — uses Hermes REST API chat/stream endpoint
    async def send_fn(command: str):
        from src.ws_client import create_session, send_message

        sid = None
        try:
            sid = page.session.store.get("active_session_id")
        except AttributeError:
            pass
        if not sid:
            http = page.session.store.get("http_session")
            if http is None:
                return
            sid = await create_session(http, page, sessions_list, session_dropdown)
            if sid is None:
                return
            page.session.store.set("active_session_id", sid)

        await send_message(page, sid, command, chat_column, empty_state)

    async def reconnect_fn():
        from src.ws_client import rest_listener

        page.run_task(
            rest_listener,
            page,
            chat_column,
            config,
            status_dot,
            session_dropdown,
            empty_state,
            sessions_list,
            model_dropdown,
        )

    input_area = chat_ui.build_input_area(
        page,
        chat_column,
        empty_state,
        session_dropdown,
        sessions_list,
        status_dot,
        send_fn,
        model_dropdown=model_dropdown,
        reconnect_fn=reconnect_fn,
    )

    # ── App Bar ──────────────────────────────────────────────────────
    page.appbar = ft.AppBar(
        leading=ft.IconButton(
            ft.Icons.MENU,
            tooltip="Menu",
            on_click=lambda e: page.run_task(page.show_drawer),
        ),
        title=ft.Row(
            [
                ft.Icon(ft.Icons.FORUM, size=20),
                ft.Text("Cadux", weight=ft.FontWeight.BOLD, size=18),
            ],
            spacing=6,
        ),
        actions=[
            status_dot,
            ft.IconButton(
                ft.Icons.SETTINGS,
                tooltip="Settings",
                on_click=lambda e: _show_settings_dialog(page, existing_config=config),
            ),
        ],
    )

    # ── Navigation Drawer ───────────────────────────────────────────
    async def _drawer_cmd_help(e):
        await send_fn("/help")

    async def _drawer_cmd_forget(e):
        chat_column.controls.clear()
        chat_ui.update_empty_state(chat_column, empty_state)
        page.update()
        await send_fn("/forget")

    async def _drawer_on_model(e):
        await send_fn(f"/model {model_dropdown.value}")

    model_dropdown.on_change = _drawer_on_model

    async def _drawer_on_session_change(e):
        sid = session_dropdown.value
        if sid:
            from src.ws_client import _activate_session

            http = page.session.store.get("http_session")
            if http is not None:
                await _activate_session(http, page, sid, chat_column, empty_state)

    session_dropdown.on_change = _drawer_on_session_change

    drawer = ft.NavigationDrawer(
        controls=[
            ft.Container(
                content=ft.Column(
                    [
                        ft.Text("Controls", size=16, weight=ft.FontWeight.BOLD),
                        ft.Divider(height=1),
                        ft.Text("Session", size=11, weight=ft.FontWeight.W_500),
                        session_dropdown,
                        ft.Text("Model", size=11, weight=ft.FontWeight.W_500),
                        model_dropdown,
                        ft.Divider(height=1),
                        ft.ElevatedButton(
                            "/help",
                            icon=ft.Icons.HELP_OUTLINE,
                            on_click=_drawer_cmd_help,
                            style=ft.ButtonStyle(text_style=ft.TextStyle(size=12)),
                        ),
                        ft.ElevatedButton(
                            "/forget",
                            icon=ft.Icons.DELETE_OUTLINE,
                            on_click=_drawer_cmd_forget,
                            style=ft.ButtonStyle(text_style=ft.TextStyle(size=12)),
                        ),
                        ft.ElevatedButton(
                            "Reconnect",
                            icon=ft.Icons.REFRESH,
                            on_click=lambda e: page.run_task(reconnect_fn()),
                            style=ft.ButtonStyle(text_style=ft.TextStyle(size=12)),
                        ),
                    ],
                    spacing=8,
                    scroll=ft.ScrollMode.AUTO,
                ),
                padding=ft.padding.Padding.symmetric(horizontal=16, vertical=12),
            ),
        ],
    )
    page.drawer = drawer

    # ── Layout ───────────────────────────────────────────────────────
    # Stack: empty_state layered behind chat_column
    stack = ft.Stack(
        [empty_state, chat_column],
        expand=True,
    )

    content = ft.Column(
        [missing_banner, stack, input_area] if missing_banner else [stack, input_area],
        spacing=0,
        expand=True,
    )
    page.add(content)

    # ── Responsive Padding ───────────────────────────────────────────
    def _on_resize(e):
        w = page.width
        chat_ui.set_page_width(w)
        if w < 400:
            page.padding = 2
        elif w < 600:
            page.padding = 4
        else:
            page.padding = ft.padding.Padding.only(left=64, right=64, top=4, bottom=4)
        page.update()

    page.on_resized = _on_resize
    _on_resize(None)

    # ── Start REST Listener (only if configured) ─────────────────────
    if config is not None:
        from src.ws_client import rest_listener

        page.run_task(
            rest_listener,
            page,
            chat_column,
            config,
            status_dot,
            session_dropdown,
            empty_state,
            sessions_list,
            model_dropdown,
        )

    page.update()


# ── Settings Dialog ──────────────────────────────────────────────────


def _show_settings_dialog(page, existing_config=None):
    url_field = ft.TextField(
        label="API URL",
        value=(existing_config or {}).get("api_url", ""),
        width=350,
        hint_text="http://192.168.0.83:8642",
    )
    key_field = ft.TextField(
        label="Secret Key",
        value=(existing_config or {}).get("secret_key", ""),
        width=350,
        password=True,
        can_reveal_password=True,
        hint_text="Bearer token / API key",
    )

    def _on_save(e):
        url = url_field.value.strip()
        key = key_field.value.strip()
        if url and key:
            try:
                page.session.store.set("api_url", url)
                page.session.store.set("secret_key", key)
            except AttributeError:
                pass
            page.pop_dialog()
            # Clean and re-initialise so the listener starts
            page.clean()
            main(page)

    dialog = ft.AlertDialog(
        title=ft.Text("Cadux Settings"),
        content=ft.Column(
            [url_field, key_field],
            spacing=12,
            tight=True,
        ),
        actions=[
            ft.TextButton("Find Server", on_click=lambda e: page.run_task(_pairing_flow, page)),
            ft.TextButton("Save", on_click=_on_save),
        ],
    )

    page.show_dialog(dialog)


# ── Auto-Pairing Flow ────────────────────────────────────────────────


async def _pairing_flow(page: ft.Page):
    """Scan LAN → register → poll (waiting for Hermes) → 6-code grid → decrypt locally."""

    # ── Phase 1: scan LAN ────────────────────────────────────────────
    cancelled = False

    scan_progress = ft.ProgressBar(width=260, value=0)
    scan_label = ft.Text("Scanning local network… 0 / 255", size=13)
    scan_spinner = ft.ProgressRing(width=20, height=20)

    scan_content = ft.Column(
        [
            ft.Row([scan_spinner, scan_label], spacing=8, alignment=ft.MainAxisAlignment.CENTER),
            ft.Container(height=6),
            scan_progress,
        ],
        spacing=4,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        tight=True,
        width=300,
    )

    def _on_cancel_scan(e):
        nonlocal cancelled
        cancelled = True

    scan_dlg = ft.AlertDialog(
        title=ft.Text("🔍 Finding Hermes…", text_align=ft.TextAlign.CENTER),
        content=scan_content,
        actions=[ft.TextButton("Cancel", on_click=_on_cancel_scan)],
    )
    page.show_dialog(scan_dlg)
    page.update()

    from src.pairing import scan, PairingSession

    def _on_progress(completed: int, total: int):
        nonlocal cancelled
        if cancelled:
            return
        try:
            scan_label.value = f"Scanning local network… {completed} / {total}"
            scan_progress.value = completed / total if total else 0
            page.update()
        except Exception:
            pass

    servers = await scan(timeout=15.0, progress_callback=_on_progress)
    if cancelled or not servers:
        page.pop_dialog()
        if not cancelled:
            _show_error_dialog(page, "No pairing servers found.\nMake sure paird is running on the Hermes host (port 8643).")
        return

    daemon_url = servers[0]["url"]

    # ── Phase 2: register with paird ─────────────────────────────────
    session = PairingSession(daemon_url)
    try:
        await session.register()
    except Exception as e:
        page.pop_dialog()
        _show_error_dialog(page, f"Failed to register:\n{e}")
        return

    # ── Phase 3: show "waiting for Hermes" spinner ───────────────────
    waiting_text = ft.Text(
        "Ask Hermes:  \"Pair with cadux\"",
        size=14,
        text_align=ft.TextAlign.CENTER,
    )
    spinner = ft.ProgressRing(width=32, height=32)
    cancel_btn = ft.TextButton(
        "Cancel",
        on_click=lambda e: page.run_task(_cancel_pairing, page, session),
    )

    wait_dlg = ft.AlertDialog(
        title=ft.Text("⏳ Waiting for Hermes", text_align=ft.TextAlign.CENTER),
        content=ft.Column(
            [spinner, ft.Container(height=8), waiting_text],
            spacing=4,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            tight=True,
            width=280,
        ),
        actions=[cancel_btn],
    )
    page.pop_dialog()  # remove scan dialog
    page.show_dialog(wait_dlg)
    page.update()

    # ── Phase 4: poll until Hermes initiates ─────────────────────────
    result = await session.poll(timeout=120.0)
    if result is None:
        page.pop_dialog()
        _show_error_dialog(page, "Timed out waiting for Hermes.\nSay \"Pair with cadux\" and try again.")
        await session.close()
        return

    codes: list[str] = result["codes"]

    # ── Phase 5: show 6 codes in 2×3 grid ────────────────────────────
    status_text = ft.Text(
        "Tap the code that Hermes shows",
        size=13,
        color=ft.Colors.ON_SURFACE_VARIANT,
        text_align=ft.TextAlign.CENTER,
    )
    result_text = ft.Text("", size=14, text_align=ft.TextAlign.CENTER)
    # Wrong-code flash state
    wrong_container = ft.Container()  # placeholder, replaced below

    async def _on_tap_code(code):
        """User tapped a code — try decrypt locally with MD5 check."""
        nonlocal session
        config = session.try_code(code)

        if config is not None:
            # ✅ Correct code
            result_text.value = "✅ Paired!"
            result_text.color = ft.Colors.PRIMARY
            page.update()
            await asyncio.sleep(0.6)

            # Save config
            try:
                page.session.store.set("api_url", config["api_url"])
                page.session.store.set("secret_key", config["secret_key"])
            except AttributeError:
                pass

            page.pop_dialog()
            await session.close()

            # ── Phase 5b: post-pairing confirmation to Hermes ──
            _send_pairing_confirmation(page, config)

            # Rebuild UI with config active
            page.clean()
            main(page)
        else:
            # ❌ Wrong code — flash red
            result_text.value = "❌ Wrong code — try another"
            result_text.color = ft.Colors.ERROR
            page.update()
            await asyncio.sleep(0.5)
            result_text.value = ""
            page.update()

    def _make_code_button(code):
        return ft.Container(
            content=ft.Text(code, size=28, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
            width=90,
            height=72,
            border_radius=14,
            bgcolor=ft.Colors.PRIMARY,
            alignment=ft.alignment.Alignment.CENTER,
            on_click=lambda e, c=code: page.run_task(_on_tap_code, c),
            ink=True,
        )

    # Build 2×3 grid: two rows of 3
    code_buttons = [_make_code_button(c) for c in codes]
    code_grid = ft.Column(
        [
            ft.Row(code_buttons[0:3], alignment=ft.MainAxisAlignment.CENTER, spacing=14),
            ft.Container(height=8),
            ft.Row(code_buttons[3:6], alignment=ft.MainAxisAlignment.CENTER, spacing=14),
        ],
        spacing=0,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
    )

    pair_dlg = ft.AlertDialog(
        title=ft.Text("📱 Pick the matching code", text_align=ft.TextAlign.CENTER, size=16),
        content=ft.Column(
            [
                code_grid,
                ft.Container(height=6),
                status_text,
                result_text,
            ],
            spacing=4,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            tight=True,
            width=340,
        ),
        actions=[ft.TextButton("Cancel", on_click=lambda e: page.run_task(_cancel_pairing, page, session))],
    )

    page.pop_dialog()  # remove waiting dialog
    page.show_dialog(pair_dlg)
    page.update()


async def _cancel_pairing(page: ft.Page, session):
    await session.close()
    try:
        page.pop_dialog()
    except Exception:
        pass


def _send_pairing_confirmation(page: ft.Page, config: dict):
    """Fire-and-forget POST to Hermes announcing successful pairing."""
    import urllib.request
    import json

    api_url = config.get("api_url", "").rstrip("/")
    secret = config.get("secret_key", "")
    if not api_url or not secret:
        return

    try:
        req = urllib.request.Request(
            f"{api_url}/chat/message",
            method="POST",
            data=json.dumps({"message": "This is Cadux, pairing successful."}).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {secret}",
            },
        )
        # Non-blocking: fire and forget
        urllib.request.urlopen(req, timeout=3.0)
    except Exception:
        pass  # best-effort


def _show_error_dialog(page: ft.Page, message: str):
    dlg = ft.AlertDialog(
        title=ft.Text("Pairing failed"),
        content=ft.Text(message, size=14),
        actions=[ft.TextButton("OK", on_click=lambda e: page.pop_dialog())],
    )
    page.show_dialog(dlg)
    page.update()


if __name__ == "__main__":
    ft.run(main=main)
