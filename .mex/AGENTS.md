---
name: agents
description: Always-loaded project anchor. Read this first. Contains project identity, non-negotiables, commands, and pointer to ROUTER.md for full context.
last_updated: 2026-06-17
---

# Cadux

## What This Is
A cross-platform chat client (Android APK + desktop) for the Hermes Agent Gateway, using its REST API with SSE streaming.

## Non-Negotiables
- Never commit secrets or API keys — use `.env` (gitignored) or environment variables
- Never import `websockets` — the project uses REST+SSE over aiohttp, not WebSockets
- Never create new aiohttp sessions — use the one stored in `page.session.store.get("http_session")`
- Always run async Flet operations via `page.run_task()`, never `asyncio.run()`
- Always add dependencies with `uv add`, never `pip install`

## Commands
- Dev: uv run main.py
- Lint: `uv run --with ruff ruff check .`
- Build APK: `flet build apk`

## After Every Task
After meaningful work, run GROW:
- Ground: what changed in reality?
- Record: update `.mex/ROUTER.md` and relevant `.mex/context/` files
- Orient: create or update a `.mex/patterns/` runbook if this can recur
- Write: bump `last_updated` on changed scaffold files and run `mex log` when rationale matters

The scaffold grows from real work, not just setup. See the GROW step in `ROUTER.md` for details.

## Navigation
At the start of every session, read `ROUTER.md` before doing anything else.
For full project context, patterns, and task guidance — everything is there.
