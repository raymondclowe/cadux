import asyncio
import datetime
import logging

import flet as ft

logger = logging.getLogger(__name__)

# ── Helpers ──────────────────────────────────────────────────────────

_PAGE_WIDTH_REF = {"value": 800}

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
    is_user = role == "user"
    ts = timestamp or datetime.datetime.now().strftime("%H:%M")

    text_col = ft.Column(
        [
            ft.Text(text, selectable=True, size=15, weight=ft.FontWeight.NORMAL, no_wrap=False),
            ft.Text(ts, size=10, color=ft.Colors.OUTLINE),
        ],
        spacing=2, tight=True, width=_max_bubble_width(),
    )

    container = ft.Container(
        content=text_col,
        padding=ft.padding.Padding.only(left=12, right=12, top=8, bottom=8),
        border_radius=ft.BorderRadius(
            top_left=16 if is_user else 4, top_right=4 if is_user else 16,
            bottom_left=16, bottom_right=16,
        ),
        bgcolor=ft.Colors.PRIMARY_CONTAINER if is_user else ft.Colors.SURFACE_CONTAINER_HIGHEST,
        data=role,
        animate_opacity=100,
    )

    row = ft.Row([container], alignment=ft.MainAxisAlignment.END if is_user else ft.MainAxisAlignment.START)
    row.data = {"role": role, "text": text}
    return row

def add_message_bubble(chat_column, role, text, timestamp=None):
    chat_column.controls.append(build_message_bubble(role, text, timestamp=timestamp))

# ── Delta Streaming ──────────────────────────────────────────────────

def _get_bubble_text(bubble_row):
    return bubble_row.controls[0].content.controls[0].value

def _set_bubble_text(bubble_row, new_text):
    bubble_row.controls[0].content.controls[0].value = new_text
    bubble_row.controls[0].content.controls[0].update()

def append_delta(chat_column, chunk):
    last = chat_column.controls[-1] if chat_column.controls else None
    if last is not None and last.data is not None and last.data.get("role") == "assistant":
        _set_bubble_text(last, _get_bubble_text(last) + chunk)
    else:
        chat_column.controls.append(build_message_bubble("assistant", chunk))

def finalize_bubble(chat_column):
    pass

def remove_typing_indicator(chat_column):
    if not chat_column.controls: return
    last = chat_column.controls[-1]
    if last.data and last.data.get("role") == "assistant" and _get_bubble_text(last) == "…":
        chat_column.controls.pop()

# ── Session Chip ─────────────────────────────────────────────────────

def insert_session_chip(chat_column, session_id):
    chip = ft.Container(
        content=ft.Row([
            ft.Icon(ft.Icons.SWAP_HORIZ_ROUNDED, size=14, color=ft.Colors.ON_SURFACE_VARIANT),
            ft.Text(f"Switched to session: {session_id}", size=12, italic=True, color=ft.Colors.ON_SURFACE_VARIANT),
        ], spacing=4, alignment=ft.MainAxisAlignment.CENTER),
        padding=ft.padding.Padding.symmetric(horizontal=12, vertical=4),
        border_radius=20, bgcolor=ft.Colors.SURFACE_CONTAINER, alignment=ft.alignment.Alignment.CENTER,
    )
    chat_column.controls.append(chip)
    chat_column.controls.append(ft.Divider(height=1, thickness=0))

# ── Dropdown Refresh ─────────────────────────────────────────────────

def refresh_session_dropdown(dropdown, sessions):
    dropdown.options.clear()
    for s in sessions:
        sid = s.get("session_id", "?")
        label = s.get("title", sid) or sid
        dropdown.options.append(ft.dropdown.Option(key=sid, text=label))
    dropdown.update()

# ── Scroll / Empty State ─────────────────────────────────────────────

async def scroll_to_bottom(chat_column):
    try: await chat_column.scroll_to(offset=-1, duration=200)
    except Exception: pass

def update_empty_state(chat_column, empty_state):
    has_content = len(chat_column.controls) > 0
    empty_state.visible = not has_content
    empty_state.update()

def build_empty_state():
    return ft.Container(
        content=ft.Column([
            ft.Icon(ft.Icons.FORUM, size=64, color=ft.Colors.PRIMARY),
            ft.Text("Cadux", size=28, weight=ft.FontWeight.BOLD),
            ft.Text("Connected to Hermes", size=16, color=ft.Colors.ON_SURFACE_VARIANT),
            ft.Text("Type a message or use /forget, /model, /help.", size=13, color=ft.Colors.OUTLINE, text_align=ft.TextAlign.CENTER),
        ], spacing=8, horizontal_alignment=ft.CrossAxisAlignment.CENTER, alignment=ft.MainAxisAlignment.CENTER),
        alignment=ft.alignment.Alignment.CENTER, expand=True, visible=True,
    )

# ── GPS / TTS State (shared across sessions) ─────────────────────────

_gps_mode = {"value": "none"}  # none | general | precise
_tts_enabled = {"value": False}

def get_gps_mode():
    return _gps_mode["value"]

def set_gps_mode(mode):
    _gps_mode["value"] = mode

def get_tts_enabled():
    return _tts_enabled["value"]

def set_tts_enabled(enabled):
    _tts_enabled["value"] = enabled

def build_message_metadata(extra=None):
    """Build metadata dict to attach to outgoing messages."""
    meta = {"source": "cadux", "version": "0.3.0"}
    if _tts_enabled["value"]:
        meta["tts"] = True
    if _gps_mode["value"] != "none":
        meta["gps"] = {"accuracy": _gps_mode["value"]}
    if extra:
        meta.update(extra)
    return meta

# ── Settings: GPS / TTS dialog ───────────────────────────────────────

def _show_cadux_settings_dialog(page: ft.Page):
    """Cadux-specific settings: GPS mode, TTS toggle."""
    gps_dd = ft.Dropdown(
        label="GPS Location",
        options=[
            ft.dropdown.Option("none", "None"),
            ft.dropdown.Option("general", "General (~city)"),
            ft.dropdown.Option("precise", "Precise"),
        ],
        value=_gps_mode["value"],
        width=280,
    )
    tts_switch = ft.Switch(label="Read aloud (TTS)", value=_tts_enabled["value"])

    def _save(e):
        set_gps_mode(gps_dd.value)
        set_tts_enabled(tts_switch.value)
        page.pop_dialog()

    dlg = ft.AlertDialog(
        title=ft.Text("Cadux Settings"),
        content=ft.Column([gps_dd, tts_switch], spacing=12, tight=True, width=300),
        actions=[ft.TextButton("Save", on_click=_save)],
    )
    page.show_dialog(dlg)

# ── Input Area ───────────────────────────────────────────────────────

def build_input_area(
    page, chat_column, empty_state, session_dropdown,
    sessions_list, status_dot, send_fn,
    model_dropdown=None, reconnect_fn=None,
):
    msg_field = ft.TextField(
        multiline=True, expand=True, hint_text="Message…",
        min_lines=1, max_lines=6, text_size=14,
    )

    async def _on_send(e):
        text = msg_field.value.strip()
        if not text: return
        msg_field.value = ""; msg_field.update()

        row = build_message_bubble("user", text)
        chat_column.controls.append(row)
        typing = build_message_bubble("assistant", "…")
        chat_column.controls.append(typing)
        await scroll_to_bottom(chat_column)
        update_empty_state(chat_column, empty_state)
        page.update()
        await send_fn(text)

    send_btn = ft.IconButton(ft.Icons.SEND_ROUNDED, on_click=_on_send, tooltip="Send")

    # Camera button
    camera_btn = ft.IconButton(ft.Icons.CAMERA_ALT_ROUNDED, tooltip="Camera",
        on_click=lambda e: page.run_task(_take_photo, page, chat_column, empty_state, send_fn))

    # Mic button
    mic_btn = ft.IconButton(ft.Icons.MIC_ROUNDED, tooltip="Voice",
        on_click=lambda e: page.run_task(_send_voice_note, page, chat_column, empty_state, send_fn))

    # GPS toggle button
    gps_btn = ft.IconButton(
        ft.Icons.LOCATION_ON if _gps_mode["value"] != "none" else ft.Icons.LOCATION_OFF,
        tooltip=f"GPS: {_gps_mode['value']}",
        on_click=lambda e: _show_cadux_settings_dialog(page),
    )

    # TTS toggle button
    tts_btn = ft.IconButton(
        ft.Icons.VOLUME_UP if _tts_enabled["value"] else ft.Icons.VOLUME_OFF,
        tooltip=f"TTS: {'on' if _tts_enabled['value'] else 'off'}",
        on_click=lambda e: (
            set_tts_enabled(not _tts_enabled["value"]),
            setattr(tts_btn, 'icon', ft.Icons.VOLUME_UP if _tts_enabled["value"] else ft.Icons.VOLUME_OFF),
            tts_btn.update(),
        ),
    )

    def _on_key(e: ft.KeyboardEvent):
        if e.key == "Enter" and not e.shift:
            page.run_task(_on_send, None)
    page.on_keyboard_event = _on_key

    toolbar = ft.Row(
        [camera_btn, mic_btn, gps_btn, tts_btn],
        spacing=2, alignment=ft.MainAxisAlignment.START,
    )
    input_row = ft.Row([msg_field, send_btn], spacing=4, vertical_alignment=ft.CrossAxisAlignment.END)

    return ft.Column([toolbar, input_row], spacing=2)


async def _take_photo(page, chat_column, empty_state, send_fn):
    """Open camera/file picker and send image as metadata."""
    fp = ft.FilePicker()
    page.overlay.append(fp)
    page.update()

    # Flet FilePicker on Android should offer camera option
    result = await fp.pick_files_async(allow_multiple=False, file_type=ft.FilePickerFileType.IMAGE)
    if not result or not result.files: return

    # Send image description as message (Hermes can't see images via REST yet)
    f = result.files[0]
    name = f.name or "image.jpg"
    # Attach image info to metadata
    row = build_message_bubble("user", f"📷 {name}")
    chat_column.controls.append(row)
    typing = build_message_bubble("assistant", "…")
    chat_column.controls.append(typing)
    await scroll_to_bottom(chat_column)
    update_empty_state(chat_column, empty_state)
    page.update()
    # Send with image metadata
    await send_fn(f"[Image attached: {name}]")


async def _send_voice_note(page, chat_column, empty_state, send_fn):
    """Send a placeholder voice note (full audio capture needs Android SDK)."""
    row = build_message_bubble("user", "🎤 Voice note")
    chat_column.controls.append(row)
    typing = build_message_bubble("assistant", "…")
    chat_column.controls.append(typing)
    await scroll_to_bottom(chat_column)
    update_empty_state(chat_column, empty_state)
    page.update()
    await send_fn("[Voice note] — audio capture coming soon")


# ── Pairing Widgets ──────────────────────────────────────────────────

def build_pin_entry(page=None, on_submit=None):
    boxes: list[ft.TextField] = []
    error_text = ft.Text("", size=12, color=ft.Colors.ERROR)
    for i in range(4):
        box = ft.TextField(width=56, height=56, text_align=ft.TextAlign.CENTER,
            text_size=28, max_length=1, capitalization=ft.TextCapitalization.CHARACTERS,
            autofocus=i==0, content_padding=ft.padding.Padding.only(left=0,top=0,right=0,bottom=4))
        boxes.append(box)
    def _make_on_change(i):
        def handler(e):
            val = boxes[i].value.upper() if boxes[i].value else ""
            boxes[i].value = val
            if val and i < 3:
                if page is not None: page.run_task(boxes[i+1].focus_async)
                else: boxes[i+1].focus()
        return handler
    def _make_on_key(i):
        def handler(e: ft.KeyboardEvent):
            if e.key == "Backspace" and i > 0 and not boxes[i].value:
                boxes[i-1].value = ""
                if page is not None: page.run_task(boxes[i-1].focus_async)
                else: boxes[i-1].focus()
        return handler
    for i in range(4):
        boxes[i].on_change = _make_on_change(i)
        boxes[i].on_keyboard_event = _make_on_key(i)
    async def _on_connect(e):
        pin = "".join(b.value or "" for b in boxes).strip()
        if len(pin) < 4:
            error_text.value = "Enter the 4-character code from Hermes"
            return
        error_text.value = ""
        if on_submit: await on_submit(pin)
    connect_btn = ft.ElevatedButton("Connect", icon=ft.Icons.CHECK_CIRCLE_OUTLINE, on_click=_on_connect,
                                     style=ft.ButtonStyle(text_style=ft.TextStyle(size=14)))
    row = ft.Row(boxes, spacing=6, alignment=ft.MainAxisAlignment.CENTER)
    return ft.Column([
        ft.Text("Enter code from Hermes:", size=14, weight=ft.FontWeight.W_500),
        row, error_text, ft.Row([connect_btn], alignment=ft.MainAxisAlignment.CENTER),
    ], spacing=8, horizontal_alignment=ft.CrossAxisAlignment.CENTER, tight=True)

def build_discovery_status():
    return ft.Column([
        ft.ProgressRing(width=24, height=24),
        ft.Text("Searching for Hermes on your local network…", size=14, color=ft.Colors.ON_SURFACE_VARIANT),
    ], spacing=8, horizontal_alignment=ft.CrossAxisAlignment.CENTER, tight=True)
