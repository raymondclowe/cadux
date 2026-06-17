---
name: conventions
description: How code is written in this project — naming, structure, patterns, and style. Load when writing new code or reviewing existing code.
triggers:
  - "convention"
  - "pattern"
  - "naming"
  - "style"
  - "how should I"
  - "what's the right way"
edges:
  - target: context/architecture.md
    condition: when a convention depends on understanding the system structure
  - target: context/stack.md
    condition: when a convention relates to specific technology usage patterns
last_updated: 2026-06-17
---

# Conventions

## Naming

- Files: snake_case (chat_ui.py, ws_client.py, profiles.py)
- Functions: `snake_case`, verb-first (`load_config`, `build_chat_column`, `create_profile`, `append_delta`)
- Private helpers: `_leading_underscore` (`_is_narrow`, `_set_status`, `_activate_session`, `_slugify`)
- Constants: `UPPER_SNAKE_CASE` (`_PAIRD_PORT`, `_UDP_BROADCAST_MSG`, `_STORAGE_KEY_PROFILES`)
- Classes: `PascalCase` (`Profile` — the only dataclass in the codebase)
- Callbacks: `_on_<event>` or `_drawer_cmd_<action>` (`_on_send`, `_on_resize`, `_drawer_cmd_help`, `_drawer_cmd_forget`)

## Structure

- **UI widgets only in `chat_ui.py`** — all `build_*` functions that return Flet widgets live here. `main.py` composes them but does not define widget-building functions.
- **Network logic only in `ws_client.py`** — all HTTP calls, SSE parsing, session management. `main.py` calls into it via closures (`send_fn`, `reconnect_fn`) to avoid circular imports.
- **Entry point is thin** — `main.py` (root) imports and calls `ft.run(main=main)` from `src.main`. The real app logic is in `src/main.py`.
- **`src/__init__.py` is empty** — no re-exports. All imports are explicit (`from src.chat_ui import ...`).
- **No test files exist yet** — tests are planned but not implemented. When added, they should go in a tests directory at the project root.
- **Section comments use `──` dividers** — the codebase uses Unicode box-drawing characters for visual section separation (e.g., `# ── Config ──`).

## Patterns

**Async operations via `page.run_task()`** — All async work (network calls, dialogs) must be wrapped in `page.run_task()`. Flet manages the event loop; never create your own.

```python
# Correct
page.run_task(rest_listener, page, chat_column, config, status_dot, ...)

# Wrong — will block the Flet UI thread
asyncio.run(rest_listener(page, chat_column, config, ...))
```

**Callback closures avoid circular imports** — `main.py` defines `send_fn` and `reconnect_fn` as closures that import `ws_client` lazily inside the function body. This prevents `chat_ui.py` from depending on `ws_client.py`.

```python
# In main.py
async def send_fn(command: str):
    from src.ws_client import create_session, send_message  # lazy import
    ...
```

**SSE parsing is line-based, not event-source library** — The SSE stream from Hermes uses `event:` + `data:` lines (not plain `data:` like OpenAI). The parser in `send_message()` reads lines with `resp.content.readline()` and manually tracks `current_event`. Do not use an SSE library — the format is bespoke.

**Config flow: profile beats env** — When both a profile and env config exist, the profile takes priority. The env/session config is only used to seed a "Default" profile on first launch.

## Verify Checklist

Before presenting any code:
- [ ] New UI widgets are in `chat_ui.py`, not in `main.py` or network modules
- [ ] Network calls use `aiohttp` through the existing `http` session stored in `page.session.store`, never create a new session
- [ ] Async functions are invoked via `page.run_task()`, not `asyncio.run()` or bare `await` at module level
- [ ] New Python dependencies were added with `uv add <package>`, not `pip install`
- [ ] The code runs with uv run main.py without import errors
- [ ] No `websockets` library imports — the project uses REST+SSE, not WebSockets
- [ ] Callbacks that need the page reference use closures or `lambda`, not partial application that captures stale state
