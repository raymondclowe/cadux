import datetime
import json
import logging

import flet as ft

logger = logging.getLogger(__name__)

# ── Helpers ──────────────────────────────────────────────────────────

_PAGE_WIDTH_REF = {"value": 800}  # updated by main.py on resize


def set_page_width(w):
    _PAGE_WIDTH_REF["value"] = w


def _is_narrow():
    return _PAGE_WIDTH_REF["value"] < 400


def _max_bubble_width():
    return 300 if _is_narrow() else 500


# ── Chat Column ──────────────────────────────────────────────────────


def build_chat_column():
    return ft.Column(scroll=ft.ScrollMode.AUTO, expand=True, spacing=4)


# ── Message Bubbles ──────────────────────────────────────────────────


def build_message_bubble(role, text, timestamp=None):
    """Return a styled chat-bubble Container.

    ``data`` is set to the role so we can identify bubbles later.
    """
    is_user = role == "user"
    ts = timestamp or datetime.datetime.now().strftime("%H:%M")

    text_col = ft.Column(
        [
            ft.Text(
                text,
                selectable=True,
                size=15,
                weight=ft.FontWeight.NORMAL,
            ),
            ft.Text(ts, size=10, color=ft.Colors.OUTLINE),
        ],
        spacing=2,
        tight=True,
    )

    container = ft.Container(
        content=text_col,
        padding=ft.padding.Padding.only(left=12, right=12, top=8, bottom=8),
        border_radius=ft.BorderRadius(
            top_left=16 if is_user else 4,
            top_right=4 if is_user else 16,
            bottom_left=16,
            bottom_right=16,
        ),
        bgcolor=ft.Colors.PRIMARY_CONTAINER if is_user else ft.Colors.SURFACE_CONTAINER_HIGHEST,
        data=role,
        animate_opacity=100,
    )

    row = ft.Row(
        [container],
        alignment=ft.MainAxisAlignment.END if is_user else ft.MainAxisAlignment.START,
    )

    # Long-press to copy
    row.data = {"role": role, "text": text}
    return row


def _set_bubble_text(bubble_row, new_text):
    """Replace the text inside an existing bubble row."""
    container = bubble_row.controls[0]
    text_col = container.content
    text_col.controls[0].value = new_text


def _get_bubble_text(bubble_row):
    container = bubble_row.controls[0]
    return container.content.controls[0].value


# ── Delta Streaming ──────────────────────────────────────────────────


def append_delta(chat_column, chunk):
    """Append a delta chunk to the current assistant bubble, or create one."""
    last = chat_column.controls[-1] if chat_column.controls else None
    if last is not None and last.data is not None and last.data.get("role") == "assistant":
        # Append to existing bubble
        current = _get_bubble_text(last)
        _set_bubble_text(last, current + chunk)
    else:
        # Start a new assistant bubble
        row = build_message_bubble("assistant", chunk)
        chat_column.controls.append(row)


def finalize_bubble(chat_column):
    """Mark the current assistant bubble as complete (no-op unless we add animations)."""
    pass


# ── Session Chip ─────────────────────────────────────────────────────


def insert_session_chip(chat_column, session_id):
    chip = ft.Container(
        content=ft.Row(
            [
                ft.Icon(ft.Icons.SWAP_HORIZ_ROUNDED, size=14, color=ft.Colors.ON_SURFACE_VARIANT),
                ft.Text(
                    f"Switched to session: {session_id}",
                    size=12,
                    italic=True,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
            ],
            spacing=4,
            alignment=ft.MainAxisAlignment.CENTER,
        ),
        padding=ft.padding.Padding.symmetric(horizontal=12, vertical=4),
        border_radius=20,
        bgcolor=ft.Colors.SURFACE_CONTAINER,
        alignment=ft.alignment.Alignment.CENTER,
    )
    chat_column.controls.append(chip)
    chat_column.controls.append(ft.Divider(height=1, thickness=0))


# ── Dropdown Refresh ─────────────────────────────────────────────────


def refresh_session_dropdown(dropdown, sessions):
    """Rebuild the options of the session switcher dropdown."""
    dropdown.options.clear()
    for s in sessions:
        sid = s.get("session_id", "?")
        label = s.get("title", sid) or sid
        dropdown.options.append(ft.dropdown.Option(key=sid, text=label))
    dropdown.update()


# ── Scroll ───────────────────────────────────────────────────────────


def scroll_to_bottom(chat_column):
    try:
        chat_column.scroll_to(offset=-1, duration=200)
    except Exception:
        pass


# ── Empty State ──────────────────────────────────────────────────────


def update_empty_state(chat_column, empty_state):
    """Show empty-state welcome when chat is clear, hide otherwise."""
    has_content = len(chat_column.controls) > 0
    empty_state.visible = not has_content
    empty_state.update()


def build_empty_state():
    return ft.Container(
        content=ft.Column(
            [
                ft.Icon(ft.Icons.FORUM, size=64, color=ft.Colors.PRIMARY),
                ft.Text("Cadux", size=28, weight=ft.FontWeight.BOLD),
                ft.Text(
                    "Connected to Hermes",
                    size=16,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
                ft.Text(
                    "Type a message or use /forget, /model, and session switcher below.",
                    size=13,
                    color=ft.Colors.OUTLINE,
                    text_align=ft.TextAlign.CENTER,
                ),
            ],
            spacing=8,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            alignment=ft.MainAxisAlignment.CENTER,
        ),
        alignment=ft.alignment.Alignment.CENTER,
        expand=True,
        visible=True,
    )


# ── Input Area ───────────────────────────────────────────────────────


def build_input_area(
    page,
    chat_column,
    empty_state,
    session_dropdown,
    sessions_list,
    status_dot,
    send_fn,
    reconnect_fn=None,
):
    """Build the bottom input bar + command bar.

    ``send_fn`` is a callable that takes the command string and sends it
    over the WebSocket (avoids circular import with ws_client).
    ``reconnect_fn`` is an optional async callable to trigger reconnection.
    """
    msg_field = ft.TextField(
        multiline=True,
        expand=True,
        hint_text="Message…",
        min_lines=1,
        max_lines=6,
        text_size=14,
    )

    async def _on_send(e):
        text = msg_field.value.strip()
        if not text:
            return
        msg_field.value = ""
        msg_field.update()

        # Optimistic user bubble
        row = build_message_bubble("user", text)
        chat_column.controls.append(row)
        # Add typing indicator assistant bubble
        typing = build_message_bubble("assistant", "…")
        chat_column.controls.append(typing)
        scroll_to_bottom(chat_column)
        update_empty_state(chat_column, empty_state)
        page.update()

        await send_fn(text)

    send_btn = ft.IconButton(
        ft.Icons.SEND_ROUNDED,
        on_click=_on_send,
        tooltip="Send",
    )

    def _on_key(e: ft.KeyboardEvent):
        if e.key == "Enter" and not e.shift:
            page.run_task(_on_send, None)

    page.on_keyboard_event = _on_key

    # ── Command Bar ──

    async def _cmd_forget(e):
        chat_column.controls.clear()
        update_empty_state(chat_column, empty_state)
        page.update()
        await send_fn("/forget")

    forget_btn = ft.ElevatedButton(
        "/forget",
        icon=ft.Icons.DELETE_OUTLINE,
        on_click=_cmd_forget,
        style=ft.ButtonStyle(text_style=ft.TextStyle(size=12)),
    )

    model_dd = ft.Dropdown(
        value="deepseek-chat",
        options=[
            ft.dropdown.Option("deepseek-chat"),
            ft.dropdown.Option("gpt-4o"),
            ft.dropdown.Option("claude-sonnet"),
        ],
        width=140,
        text_size=12,
        label="Model",
    )

    async def _on_model(e):
        await send_fn(f"/model {model_dd.value}")

    model_dd.on_change = _on_model

    async def _on_session_change(e):
        sid = session_dropdown.value
        if sid:
            await send_fn(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "method": "session.activate",
                        "params": {"session_id": sid},
                        "id": 9999,
                    }
                )
            )

    session_dropdown.on_change = _on_session_change

    reconnect_btn = ft.ElevatedButton(
        "Reconnect",
        icon=ft.Icons.REFRESH,
        on_click=lambda e: page.run_task(reconnect_fn()) if reconnect_fn else None,
        style=ft.ButtonStyle(text_style=ft.TextStyle(size=12)),
    )

    command_bar = ft.Row(
        [forget_btn, model_dd, session_dropdown, reconnect_btn],
        wrap=True,
        spacing=4,
        alignment=ft.MainAxisAlignment.START,
    )

    input_row = ft.Row(
        [msg_field, send_btn],
        spacing=4,
        vertical_alignment=ft.CrossAxisAlignment.END,
    )

    return ft.Column([command_bar, input_row], spacing=4)
