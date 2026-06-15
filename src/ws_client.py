import asyncio
import json
import logging

import flet as ft
import websockets

from src.chat_ui import (
    append_delta,
    finalize_bubble,
    insert_session_chip,
    refresh_session_dropdown,
    scroll_to_bottom,
    update_empty_state,
)

logger = logging.getLogger(__name__)

# JSON-RPC message ID counter
_next_id = 100


def next_id() -> int:
    global _next_id
    _next_id += 1
    return _next_id


async def ws_listener(
    page,
    chat_column,
    config,
    status_dot,
    session_dropdown,
    empty_state,
    sessions_list,
):
    """Connect to Hermes gateway and process messages forever.

    Handles reconnection with exponential backoff (1s -> 30s max).
    Updates UI controls in-place via page.update().
    """
    backoff = 1
    max_backoff = 30

    while True:
        try:
            _set_status(status_dot, ft.Colors.AMBER)
            async with websockets.connect(
                config["wss_url"],
                extra_headers={"X-Hermes-Auth": config["secret_key"]},
                ping_interval=30,
                ping_timeout=10,
            ) as ws:
                page.session.store.set("ws_conn", ws)
                backoff = 1  # reset on successful connect
                _set_status(status_dot, ft.Colors.GREEN)

                # Bootstrap session list
                await ws.send(
                    json.dumps(
                        {
                            "jsonrpc": "2.0",
                            "method": "session.list",
                            "id": next_id(),
                        }
                    )
                )

                # Main message loop
                async for raw in ws:
                    try:
                        data = json.loads(raw)
                    except json.JSONDecodeError:
                        continue

                    _handle_message(
                        page,
                        chat_column,
                        data,
                        session_dropdown,
                        empty_state,
                        sessions_list,
                    )
                    page.update()

        except websockets.ConnectionClosed:
            logger.warning("WebSocket closed")
        except Exception as exc:
            logger.warning("WebSocket error: %s", exc)

        # Disconnected
        _set_status(status_dot, ft.Colors.RED)
        page.snack_bar = ft.SnackBar(
            ft.Text(f"Connection lost — reconnecting in {backoff}s…"),
            bgcolor=ft.Colors.ERROR_CONTAINER,
        )
        page.snack_bar.open = True
        page.update()

        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, max_backoff)


def _set_status(dot, color_key):
    dot.bgcolor = color_key


def _handle_message(
    page,
    chat_column,
    data,
    session_dropdown,
    empty_state,
    sessions_list,
):
    """Route a parsed JSON-RPC message to the right handler."""
    method = data.get("method")
    msg_id = data.get("id")

    # Response to session.list (id will be > 100)
    if msg_id is not None and isinstance(data.get("result"), list):
        sessions = data["result"]
        sessions_list.clear()
        sessions_list.extend(sessions)
        refresh_session_dropdown(session_dropdown, sessions)

        # Restore active session if we have one saved
        saved = None
        try:
            saved = page.session.store.get("active_session_id")
        except AttributeError:
            pass
        if saved and any(s.get("session_id") == saved for s in sessions):
            asyncio.ensure_future(
                _send_json(
                    page,
                    {
                        "jsonrpc": "2.0",
                        "method": "session.activate",
                        "params": {"session_id": saved},
                        "id": next_id(),
                    },
                )
            )
        return

    if method == "message.delta":
        text = data.get("params", {}).get("text", "")
        append_delta(chat_column, text)
        scroll_to_bottom(chat_column)
        update_empty_state(chat_column, empty_state)

    elif method == "message.complete":
        finalize_bubble(chat_column)

    elif method == "session.activated":
        sid = data.get("params", {}).get("session_id", "?")
        insert_session_chip(chat_column, sid)
        scroll_to_bottom(chat_column)
        try:
            page.session.store.set("active_session_id", sid)
        except AttributeError:
            pass

    elif method == "session.created":
        s = data.get("params", {})
        sessions_list.append(s)
        refresh_session_dropdown(session_dropdown, sessions_list)

    elif method == "session.deleted":
        sid = data.get("params", {}).get("session_id", "")
        sessions_list[:] = [s for s in sessions_list if s.get("session_id") != sid]
        refresh_session_dropdown(session_dropdown, sessions_list)

        active = None
        try:
            active = page.session.store.get("active_session_id")
        except AttributeError:
            pass
        if active == sid:
            chat_column.controls.clear()
            try:
                page.session.store.set("active_session_id", None)
            except AttributeError:
                pass
            update_empty_state(chat_column, empty_state)


async def _send_json(page, payload):
    ws = page.session.store.get("ws_conn")
    if ws is not None:
        try:
            await ws.send(json.dumps(payload))
        except Exception:
            pass
