---
name: debug-sse-streaming
description: Diagnosing failures in the SSE streaming path — messages not appearing, streams hanging, or status dot not turning green.
triggers:
  - "SSE"
  - "streaming"
  - "stream"
  - "messages not appearing"
  - "connection"
  - "status dot"
  - "listener"
  - "reconnect"
edges:
  - target: context/architecture.md
    condition: when understanding the REST+SSE flow end-to-end
  - target: context/stack.md
    condition: when checking aiohttp version or connection settings
  - target: patterns/add-slash-command.md
    condition: when the issue is with a specific slash command not streaming
last_updated: 2026-06-17
---

# Debug SSE Streaming

## Context

The critical data path in Cadux is: user sends message → `send_message()` POSTs to Hermes SSE endpoint → `resp.content.readline()` parses SSE lines → `_handle_sse_chunk()` updates the UI bubble via `append_delta()`.

The REST listener (`rest_listener()` in `ws_client.py`) runs as a background task managing the HTTP session and polling `/api/sessions` every 5 seconds. The status dot reflects the listener's health.

Before starting, read `context/architecture.md` for the full flow.

## Task: Diagnose "Messages Not Appearing"

### Steps

1. **Check the status dot** in the app bar:
   - Grey = listener hasn't started (no config)
   - Green = listener is running and sessions are reachable
   - Red = listener encountered an error on last poll
2. **If grey**: Open Settings (gear icon) and verify API URL + secret key are set. Tap Reconnect in the drawer.
3. **If red**: The Hermes server may be unreachable. Check:
   - Is the Hermes host running? `curl <api_url>/api/sessions` with the Bearer token
   - Is the API URL correct? Include the port (usually 8642)
   - Is the secret key valid? A 403 means the key is wrong
4. **If green but messages don't appear**: The SSE stream may be failing silently.
   - Check the terminal output for `send_message error:` or `chat stream returned` warnings
   - The SSE parser expects `event: assistant.delta` + `data: {"delta":"..."}` lines. Check `docs/hermes-sse-format.md` for the expected format.
   - If Hermes sends `data:` without `event:`, the parser ignores it (line starts with `data:` but `current_event` is `None` → `_handle_sse_chunk` receives `event_name=None`)

### Gotchas

- **SSE format is `event:` + `data:` lines, not plain `data:`**: The Hermes SSE format is non-standard. Cadux tracks `current_event` across lines. If Hermes changes its format, the parser in `send_message()` must be updated.
- **`[DONE]` signals end of stream**: The parser looks for `data: [DONE]` to finalize the bubble and remove the typing indicator.
- **Typing indicator is "…"**: A temporary assistant bubble with text "…" is added optimistically before sending. If the stream fails, this bubble stays. Use `/forget` or Reconnect to clear it.
- **`TCPConnector(force_close=True)` prevents connection reuse issues**: This is intentional — without it, aiohttp may reuse a stale connection after a network change.
- **The listener polls every 5 seconds**: New sessions may take up to 5 seconds to appear in the dropdown.

### Verify

- [ ] `curl -H "Authorization: Bearer <key>" <api_url>/api/sessions` returns HTTP 200 with session data
- [ ] Sending a message shows a user bubble immediately, then a "…" typing bubble
- [ ] The "…" bubble is replaced by streamed text within a few seconds
- [ ] The assistant bubble finalizes (no "…" remains) after the stream completes
- [ ] `[DONE]` is received and handled without errors in the terminal

## Task: Diagnose Listener Failures

### Steps

1. Check terminal output for `session list error:` warnings — these indicate the 5-second poll is failing.
2. Common causes:
   - **Wrong API URL format**: URL should not have trailing slash (the code strips it via `.rstrip("/")` but an extra path segment will break).
   - **Wrong auth**: 401/403 from Hermes. Verify the secret key.
   - **Network timeout**: Check if the Hermes host is reachable.
3. Tap **Reconnect** in the drawer to restart the listener. This cancels the old task and starts a fresh one.

### Gotchas

- **Profile switch kills the listener**: `_switch_profile()` cancels the old listener task before rebuilding. This is intentional.
- **Restarting the listener creates a new aiohttp session**: The old session's `http_session` in `page.session.store` is replaced.

## Update Scaffold

- [ ] Update `.mex/ROUTER.md` "Current Project State" if a new streaming issue is discovered
- [ ] Update `context/architecture.md` if the SSE format or endpoint changes
- [ ] If this is a new task type without a pattern, create one in `.mex/patterns/` and add to `patterns/INDEX.md`
