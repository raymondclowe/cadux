---
name: add-slash-command
description: Adding a new slash command (e.g., /help, /forget, /model) to the chat interface.
triggers:
  - "slash command"
  - "/command"
  - "add command"
  - "new command"
  - "chat command"
edges:
  - target: context/conventions.md
    condition: when unsure about naming or code structure conventions
  - target: context/architecture.md
    condition: when understanding how commands flow through the system
last_updated: 2026-06-17
---

# Add Slash Command

## Context

Slash commands are plain text messages starting with `/` that the Hermes backend interprets.
Cadux sends them via the same `send_message()` SSE streaming path as regular messages.
The UI for triggering commands lives in the navigation drawer (`src/main.py`).

Before starting, read `context/architecture.md` to understand the message flow:
user types text → `send_fn` in `main.py` → `ws_client.send_message()` → POST to Hermes SSE endpoint.

## Task: Add Command Button

### Steps

1. Open `src/main.py` and locate the navigation drawer section (around the `/help` and `/forget` buttons).
2. Define an async handler function following the `_drawer_cmd_<name>` naming pattern:
   ```python
   async def _drawer_cmd_status(e):
       await send_fn("/status")
   ```
3. Add an `ft.ElevatedButton` in the drawer's `controls` list. Use the existing button style for consistency:
   ```python
   ft.ElevatedButton(
       "/status",
       icon=ft.Icons.INFO_OUTLINE,
       on_click=_drawer_cmd_status,
       style=ft.ButtonStyle(text_style=ft.TextStyle(size=12)),
   ),
   ```
4. Run uv run main.py to verify the button appears in the drawer and sends the command.

### Gotchas

- **send_fn expects one argument (the command string)** — it's a closure defined in `main()` that captures `chat_column`, `empty_state`, `session_dropdown`, etc. Just pass the command text.
- **The drawer is rebuilt on every `main()` call** — no need to call `page.update()` for the drawer specifically; a profile switch rebuilds the whole page.
- **Commands that modify server state** (e.g., `/forget`) should also clear the local chat UI. See `_drawer_cmd_forget` for the pattern: `chat_column.controls.clear()` + `update_empty_state()` + `page.update()` before sending.
- **Don't add buttons to the input area** — command buttons go in the drawer, not in `chat_ui.build_input_area()`.

### Verify

- [ ] The button appears in the navigation drawer with the correct icon
- [ ] Tapping the button sends the command and shows a user bubble with the command text
- [ ] The Hermes backend responds (assistant bubble appears)
- [ ] No import errors — all imports are lazy or at the top of `main.py`

## Task: Add Auto-Command (no button)

Commands that don't need a UI button (e.g., auto-sent on connect) go in `ws_client.py`.

### Steps

1. Open `src/ws_client.py`.
2. Send the command via the existing `http` session. Example pattern from `_activate_session()`:
   ```python
   async with http.get(f"/api/sessions/{session_id}/messages") as resp:
       ...
   ```
3. For commands that use chat/stream, follow the `send_message()` pattern — POST to `/api/sessions/{id}/chat/stream` with `{"message": "/command"}`.

### Gotchas

- **Always use the `http` session from `page.session.store`** — never create a new `aiohttp.ClientSession`.
- **If the command needs the active session ID**, get it from `page.session.store.get("active_session_id")`. If `None`, call `create_session()` first.

## Update Scaffold

- [ ] Update `.mex/ROUTER.md` "Current Project State" if a new command capability was added
- [ ] Update any `.mex/context/` files that are now out of date
- [ ] If this is a new task type without a pattern, create one in `.mex/patterns/` and add to `patterns/INDEX.md`
