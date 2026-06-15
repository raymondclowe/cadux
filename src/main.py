import json
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
        width=160,
        text_size=12,
        label="Session",
    )
    sessions_list = []

    # ── Unconfigured Banner ──────────────────────────────────────────
    missing_banner = None
    if config is None:
        missing_banner = ft.Container(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.WARNING_AMBER_ROUNDED, size=18, color=ft.Colors.ON_ERROR_CONTAINER),
                    ft.Text(
                        "Not configured — open Settings to enter WSS URL & Secret Key",
                        size=13,
                        color=ft.Colors.ON_ERROR_CONTAINER,
                        expand=True,
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

    # Send callback (avoids circular import with ws_client)
    async def send_fn(command: str):
        ws = page.session.store.get("ws_conn")
        if ws is None:
            return
        from src.ws_client import next_id

        payload = {
            "jsonrpc": "2.0",
            "method": "command.dispatch",
            "params": {"command": command},
            "id": next_id(),
        }
        try:
            await ws.send(json.dumps(payload))
        except Exception as exc:
            logger.warning("send error: %s", exc)

    async def reconnect_fn():
        ws = page.session.store.get("ws_conn")
        if ws is not None:
            await ws.close()
        from src.ws_client import ws_listener

        page.run_task(
            ws_listener,
            page,
            chat_column,
            config,
            status_dot,
            session_dropdown,
            empty_state,
            sessions_list,
        )

    input_area = chat_ui.build_input_area(
        page,
        chat_column,
        empty_state,
        session_dropdown,
        sessions_list,
        status_dot,
        send_fn,
        reconnect_fn=reconnect_fn,
    )

    # ── App Bar ──────────────────────────────────────────────────────
    page.appbar = ft.AppBar(
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

    # ── Start WebSocket Listener (only if configured) ────────────────
    if config is not None:
        from src.ws_client import ws_listener

        page.run_task(
            ws_listener,
            page,
            chat_column,
            config,
            status_dot,
            session_dropdown,
            empty_state,
            sessions_list,
        )

    page.update()


# ── Settings Dialog ──────────────────────────────────────────────────


def _show_settings_dialog(page, existing_config=None):
    url_field = ft.TextField(
        label="WSS URL",
        value=(existing_config or {}).get("wss_url", ""),
        width=350,
        hint_text="wss://your-box.duckdns.org/api/ws",
    )
    key_field = ft.TextField(
        label="Secret Key",
        value=(existing_config or {}).get("secret_key", ""),
        width=350,
        password=True,
        can_reveal_password=True,
        hint_text="hex secret",
    )

    def _on_save(e):
        url = url_field.value.strip()
        key = key_field.value.strip()
        if url and key:
            try:
                page.session.store.set("wss_url", url)
                page.session.store.set("secret_key", key)
            except AttributeError:
                pass
            page.dialog.open = False
            page.update()
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
            ft.TextButton("Save", on_click=_on_save),
        ],
    )

    page.dialog = dialog
    dialog.open = True
    page.update()


if __name__ == "__main__":
    ft.run(main=main)
