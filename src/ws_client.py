import asyncio
import json
import logging
import sys

import aiohttp
import flet as ft

from src.chat_ui import (
    append_delta,
    finalize_bubble,
    insert_session_chip,
    refresh_session_dropdown,
    remove_typing_indicator,
    scroll_to_bottom,
    update_empty_state,
)

logger = logging.getLogger(__name__)

# ── Headers ──────────────────────────────────────────────────────────


def _auth_headers(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"}


# ── REST Listener ────────────────────────────────────────────────────


async def rest_listener(
    page,
    chat_column,
    config,
    status_dot,
    session_dropdown,
    empty_state,
    sessions_list,
    model_dropdown=None,
):
    """Poll Hermes REST API and handle session management.

    Periodically refreshes the session list.
    Handles active-session message loading.
    Populates the model dropdown from real API data.
    Uses aiohttp for HTTP + SSE streaming.
    """
    base_url = config["api_url"].rstrip("/")
    headers = _auth_headers(config["secret_key"])
    connector = aiohttp.TCPConnector(force_close=True)

    async with aiohttp.ClientSession(
        base_url=base_url, headers=headers, connector=connector
    ) as http:
        page.session.store.set("http_session", http)
        _set_status(status_dot, ft.Colors.GREEN)

        # Restore active session
        saved = None
        try:
            saved = page.session.store.get("active_session_id")
        except AttributeError:
            pass

        # Bootstrap: fetch sessions, then poll every 5 seconds
        activated = False
        while True:
            try:
                raw_sessions = await _fetch_sessions(
                    http,
                    page,
                    sessions_list,
                    session_dropdown,
                    saved if not activated else None,
                    chat_column,
                    empty_state,
                )
                # Populate model dropdown from real data on first fetch
                if raw_sessions is not None and model_dropdown is not None:
                    _populate_model_dropdown(model_dropdown, raw_sessions)
            except Exception as exc:
                logger.warning("session list error: %s", exc)
                _set_status(status_dot, ft.Colors.RED)
            else:
                activated = True
                _set_status(status_dot, ft.Colors.GREEN)

            await asyncio.sleep(5)


def _populate_model_dropdown(dropdown, raw_sessions):
    """Extract unique model names from sessions and populate the dropdown.

    Also queries /v1/models for additional models.
    """
    models = set()
    for s in raw_sessions:
        m = s.get("model")
        if m:
            models.add(m)

    if not models:
        return

    sorted_models = sorted(models)
    dropdown.options.clear()
    for m in sorted_models:
        dropdown.options.append(ft.dropdown.Option(m))
    # Set default value to the most common model
    dropdown.value = sorted_models[0]
    try:
        dropdown.update()
    except Exception:
        pass


async def _fetch_sessions(
    http, page, sessions_list, session_dropdown, saved, chat_column, empty_state
):
    """GET /api/sessions and refresh the dropdown."""
    async with http.get("/api/sessions") as resp:
        if resp.status != 200:
            return
        body = await resp.json()
        raw_sessions = body.get("data") or []

        # Normalise to {session_id, title?, ...}
        sessions = []
        for s in raw_sessions:
            sessions.append(
                {
                    "session_id": s.get("id") or s.get("session_id", ""),
                    "title": s.get("title") or s.get("session_id", "")[:12],
                }
            )

        sessions_list.clear()
        sessions_list.extend(sessions)
        refresh_session_dropdown(session_dropdown, sessions)
        page.update()

        # Activate saved session on first load only
        if saved and any(s.get("session_id") == saved for s in sessions):
            await _activate_session(
                http, page, saved, chat_column, empty_state
            )

        return raw_sessions


# ── Session Activation ───────────────────────────────────────────────


async def _activate_session(
    http, page, session_id, chat_column, empty_state
):
    """Fetch messages for a session and display them."""
    try:
        async with http.get(f"/api/sessions/{session_id}/messages") as resp:
            if resp.status != 200:
                return
            body = await resp.json()
            messages = body.get("data") or []
    except Exception:
        messages = []

    chat_column.controls.clear()

    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        from src.chat_ui import add_message_bubble

        add_message_bubble(chat_column, role, content)

    insert_session_chip(chat_column, session_id)
    await scroll_to_bottom(chat_column)
    update_empty_state(chat_column, empty_state)

    try:
        page.session.store.set("active_session_id", session_id)
    except AttributeError:
        pass
    page.update()


# ── Send Message (SSE streaming) ────────────────────────────────────


async def send_message(
    page, session_id: str, text: str, chat_column, empty_state
):
    """POST /api/sessions/{id}/chat/stream and consume SSE events."""
    http = page.session.store.get("http_session")
    if http is None:
        logger.warning("no http session")
        return

    payload = {
        "message": text,
        "metadata": {
            "source": "cadux",
            "version": "0.3.0",
        }
    }

    try:
        async with http.post(
            f"/api/sessions/{session_id}/chat/stream",
            json=payload,
        ) as resp:
            if resp.status != 200:
                err_body = await resp.text()
                logger.warning("chat stream returned %s: %s", resp.status, err_body)
                return

            # Consume Hermes SSE stream
            current_event = None
            while True:
                line = await resp.content.readline()
                if not line:
                    break
                decoded = line.decode("utf-8").rstrip()
                if not decoded:
                    continue
                if decoded.startswith(":"):
                    continue
                if decoded.startswith("event: "):
                    current_event = decoded[7:]
                    continue
                if decoded.startswith("data: "):
                    raw_data = decoded[6:]
                    if raw_data == "[DONE]":
                        finalize_bubble(chat_column)
                        remove_typing_indicator(chat_column)
                        await scroll_to_bottom(chat_column)
                        update_empty_state(chat_column, empty_state)
                        page.update()
                        break
                    try:
                        chunk = json.loads(raw_data)
                    except json.JSONDecodeError:
                        continue

                    await _handle_sse_chunk(
                        page, chat_column, chunk, empty_state, current_event
                    )
                    page.update()
                    current_event = None

    except Exception as exc:
        logger.warning("send_message error: %s", exc)


async def _handle_sse_chunk(page, chat_column, chunk, empty_state, event_name=None):
    """Extract delta content from a Hermes SSE chunk and update UI."""
    if event_name == "assistant.delta":
        delta = chunk.get("delta", "")
        if delta:
            append_delta(chat_column, delta)
            await scroll_to_bottom(chat_column)
            update_empty_state(chat_column, empty_state)
    elif event_name == "assistant.completed":
        content = chunk.get("content", "")
        if content:
            append_delta(chat_column, content)
        finalize_bubble(chat_column)
        await scroll_to_bottom(chat_column)
        update_empty_state(chat_column, empty_state)
    elif event_name == "run.completed":
        finalize_bubble(chat_column)
        await scroll_to_bottom(chat_column)
        update_empty_state(chat_column, empty_state)
    elif event_name == "run.failed":
        finalize_bubble(chat_column)
        await scroll_to_bottom(chat_column)
        update_empty_state(chat_column, empty_state)
    elif event_name == "tool.progress":
        pass


# ── Session CRUD helpers ─────────────────────────────────────────────


async def create_session(
    http, page, sessions_list, session_dropdown
):
    """POST /api/sessions to create a new session."""
    try:
        async with http.post("/api/sessions", json={}) as resp:
            if resp.status not in (200, 201):
                return None
            body = await resp.json()
            sid = body.get("session", {}).get("id") or body.get("id") or body.get("session_id")
            if sid:
                # Refresh session list
                await _fetch_sessions(
                    http, page, sessions_list, session_dropdown,
                    None, None, None,
                )
                return sid
    except Exception as exc:
        logger.warning("create_session error: %s", exc)
    return None


async def delete_session(
    http, session_id: str, page, sessions_list, session_dropdown,
    chat_column, empty_state,
):
    """DELETE /api/sessions/{id}."""
    try:
        async with http.delete(f"/api/sessions/{session_id}") as resp:
            if resp.status not in (200, 204):
                return
    except Exception as exc:
        logger.warning("delete_session error: %s", exc)

    sessions_list[:] = [s for s in sessions_list if s.get("session_id") != session_id]
    refresh_session_dropdown(session_dropdown, sessions_list)

    active = None
    try:
        active = page.session.store.get("active_session_id")
    except AttributeError:
        pass
    if active == session_id:
        chat_column.controls.clear()
        try:
            page.session.store.set("active_session_id", None)
        except AttributeError:
            pass
        update_empty_state(chat_column, empty_state)
    page.update()


# ── Helpers ──────────────────────────────────────────────────────────


def _set_status(dot, color_key):
    dot.bgcolor = color_key
