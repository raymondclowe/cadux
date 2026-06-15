import asyncio
import logging
import sys

import flet as ft

from src import chat_ui
from src.config import load_config
from src.profiles import (
    load_profiles,
    get_active_profile,
    get_active_profile_id,
    set_active_profile_id,
    create_profile,
    delete_profile,
    Profile,
)

logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main(page: ft.Page):
    page.title = "Cadux"
    page.theme_mode = ft.ThemeMode.SYSTEM
    page.theme = ft.Theme(color_scheme_seed="indigo")
    page.padding = 4

    # ── Config: profiles first, then env/session fallback ───────────
    config = load_config(page)
    active_profile = get_active_profile(page)

    if active_profile is not None:
        # Profile takes priority over env/session config
        config = {"api_url": active_profile.api_url, "secret_key": active_profile.secret_key}
        page.session.store.set("_active_profile", active_profile)
    elif config is not None:
        # Env/session config exists but no profile yet — seed a Default profile
        active_profile = create_profile(page, "Default", config["api_url"], config["secret_key"])
        set_active_profile_id(page, active_profile.id)
        page.session.store.set("_active_profile", active_profile)

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
    sessions_list: list = []

    profile_dropdown = ft.Dropdown(
        text_size=12,
        label="Profile",
        expand=True,
    )

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
                                "Not configured — open Settings or use a pairing method",
                                size=13,
                                color=ft.Colors.ON_ERROR_CONTAINER,
                                expand=True,
                            ),
                        ],
                        spacing=6,
                    ),
                    ft.Row(
                        [
                            ft.ElevatedButton(
                                "🔍 LAN Scan",
                                icon=ft.Icons.SEARCH,
                                on_click=lambda e: page.run_task(_pairing_flow, page),
                                style=ft.ButtonStyle(text_style=ft.TextStyle(size=12)),
                            ),
                            ft.OutlinedButton(
                                "� Code Pair",
                                icon=ft.Icons.VPN_KEY,
                                on_click=lambda e: _show_settings_dialog(page),
                                style=ft.ButtonStyle(text_style=ft.TextStyle(size=12)),
                            ),
                        ],
                        spacing=8,
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

        listener_task = page.run_task(
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
        page.session.store.set("_listener_task", listener_task)

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
                on_click=lambda e: _show_settings_dialog(
                    page,
                    existing_config=config,
                    edit_profile=page.session.store.get("_active_profile"),
                ),
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

    async def _drawer_on_profile_change(e):
        new_pid = profile_dropdown.value
        if new_pid and new_pid != get_active_profile_id(page):
            await _switch_profile(page, new_pid)

    profile_dropdown.on_change = _drawer_on_profile_change

    def _refresh_profile_dropdown():
        """Rebuild profile dropdown options from saved profiles."""
        profiles = load_profiles(page)
        active_pid = get_active_profile_id(page)
        profile_dropdown.options.clear()
        for p in profiles:
            profile_dropdown.options.append(ft.dropdown.Option(key=p.id, text=p.name))
        profile_dropdown.value = active_pid if any(p.id == active_pid for p in profiles) else None
        try:
            profile_dropdown.update()
        except Exception:
            pass

    _refresh_profile_dropdown()

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
                        ft.Text("Profile", size=11, weight=ft.FontWeight.W_500),
                        profile_dropdown,
                        ft.Row(
                            [
                                ft.ElevatedButton(
                                    "Add",
                                    icon=ft.Icons.ADD,
                                    on_click=lambda e: page.run_task(_show_add_profile_dialog, page),
                                    style=ft.ButtonStyle(text_style=ft.TextStyle(size=11)),
                                ),
                                ft.ElevatedButton(
                                    "Delete",
                                    icon=ft.Icons.DELETE_OUTLINE,
                                    on_click=lambda e: page.run_task(_delete_current_profile, page),
                                    style=ft.ButtonStyle(text_style=ft.TextStyle(size=11)),
                                ),
                            ],
                            spacing=8,
                        ),
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

        listener_task = page.run_task(
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
        page.session.store.set("_listener_task", listener_task)

    page.update()


# ── Profile Management ──────────────────────────────────────────────


async def _switch_profile(page, new_pid: str):
    """Switch to a different profile — cancel current listener, reconnect."""
    # Save active session back to current profile
    current_pid = get_active_profile_id(page)
    current_sid = None
    try:
        current_sid = page.session.store.get("active_session_id")
    except AttributeError:
        pass
    if current_pid and current_sid:
        profiles = load_profiles(page)
        for p in profiles:
            if p.id == current_pid:
                p.active_session_id = current_sid
                from src.profiles import save_profiles as _sp
                _sp(page, profiles)
                break

    # Cancel old listener task
    old_task = page.session.store.get("_listener_task")
    if old_task and not old_task.done():
        old_task.cancel()
        try:
            await old_task
        except (asyncio.CancelledError, Exception):
            pass

    # Switch active profile
    set_active_profile_id(page, new_pid)

    # Rebuild UI with new profile
    try:
        page.clean()
    except Exception:
        pass
    main(page)


async def _show_add_profile_dialog(page: ft.Page):
    """Dialog to add a new profile."""
    name_field = ft.TextField(label="Profile Name", width=320, hint_text="e.g. Home, Work, Dad")
    url_field = ft.TextField(label="API URL", width=320, hint_text="http://192.168.0.83:8642")
    key_field = ft.TextField(
        label="Secret Key", width=320, password=True, can_reveal_password=True, hint_text="Bearer token"
    )

    async def _on_add(e):
        name = name_field.value.strip() or "New Profile"
        url = url_field.value.strip()
        key = key_field.value.strip()
        if not url or not key:
            return
        profile = create_profile(page, name, url, key)
        page.pop_dialog()
        await _switch_profile(page, profile.id)

    dlg = ft.AlertDialog(
        title=ft.Text("Add Profile"),
        content=ft.Column([name_field, url_field, key_field], spacing=10, tight=True),
        actions=[
            ft.TextButton("Cancel", on_click=lambda e: page.pop_dialog()),
            ft.TextButton("Save & Switch", on_click=_on_add),
        ],
    )
    page.show_dialog(dlg)
    page.update()


async def _delete_current_profile(page: ft.Page):
    """Delete the active profile (with confirmation)."""
    pid = get_active_profile_id(page)
    if not pid:
        return
    profiles = load_profiles(page)
    target = next((p for p in profiles if p.id == pid), None)
    if not target:
        return

    async def _confirm(e):
        page.pop_dialog()

        # Cancel old listener
        old_task = page.session.store.get("_listener_task")
        if old_task and not old_task.done():
            old_task.cancel()
            try:
                await old_task
            except (asyncio.CancelledError, Exception):
                pass

        delete_profile(page, pid)

        # Rebuild — will show missing_banner since no profiles left
        try:
            page.clean()
        except Exception:
            pass
        main(page)

    dlg = ft.AlertDialog(
        title=ft.Text(f'Delete "{target.name}"?'),
        content=ft.Text("This profile's URL and key will be removed.", size=14),
        actions=[
            ft.TextButton("Cancel", on_click=lambda e: page.pop_dialog()),
            ft.TextButton("Delete", on_click=_confirm),
        ],
    )
    page.show_dialog(dlg)
    page.update()


# ── Settings Dialog ──────────────────────────────────────────────────


def _show_settings_dialog(page, existing_config=None, edit_profile: Profile = None):
    """Show settings dialog.

    If *edit_profile* is given, the dialog pre-fills fields from that profile
    and updates it on save instead of creating a new one.
    """
    # ── Tab 1: Manual entry ──────────────────────────────────────────
    profile_name = edit_profile.name if edit_profile else ""
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
    name_field = ft.TextField(
        label="Profile Name",
        value=profile_name,
        width=350,
        hint_text="e.g. Home, Work, Dad",
    )

    def _on_save(e):
        url = url_field.value.strip()
        key = key_field.value.strip()
        name = name_field.value.strip() or "Default"
        if url and key:
            _save_config(page, url, key, name, edit_profile=edit_profile)

    manual_tab = ft.Column(
        [name_field, url_field, key_field],
        spacing=12,
        tight=True,
    )

    dialog = ft.AlertDialog(
        title=ft.Text("Cadux Settings"),
        content=manual_tab,
        actions=[
            ft.TextButton("Save", on_click=_on_save),
        ],
    )

    page.show_dialog(dialog)


def _save_config(page, api_url: str, secret_key: str, name: str = "Default", edit_profile: Profile = None):
    """Save config (as a profile) and restart the UI with connection active."""
    if edit_profile is not None:
        # Update existing profile
        edit_profile.api_url = api_url
        edit_profile.secret_key = secret_key
        edit_profile.name = name
        from src.profiles import update_profile as _up

        _up(page, edit_profile)
        set_active_profile_id(page, edit_profile.id)
    else:
        # Create new profile
        profiles = load_profiles(page)
        # Check if same URL already exists
        existing = next((p for p in profiles if p.api_url.rstrip("/") == api_url.rstrip("/")), None)
        if existing:
            existing.secret_key = secret_key
            existing.name = name
            from src.profiles import update_profile as _up

            _up(page, existing)
            set_active_profile_id(page, existing.id)
        else:
            profile = create_profile(page, name, api_url, secret_key)
            set_active_profile_id(page, profile.id)

    try:
        page.session.store.set("api_url", api_url)
        page.session.store.set("secret_key", secret_key)
    except AttributeError:
        pass
    try:
        page.pop_dialog()
    except Exception:
        pass
    page.clean()
    main(page)





if __name__ == "__main__":
    ft.run(main=main)
