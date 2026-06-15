# Cadux — Flat Implementation Plan

## Backend: Hermes Dashboard

1. **Install Hermes Agent** — Clone or pip-install the Hermes agent from `NousResearch/hermes-agent` on the local dev machine.

2. **Set loopback environment variables** — Export `HERMES_WEB_HOST=127.0.0.1` and `HERMES_WEB_PORT=3582` in the shell profile (`.bashrc` / `.zshrc` / `$PROFILE`) so the dashboard always binds to localhost only.

3. **Start dashboard in background** — Run `hermes dashboard --no-browser` and confirm the process stays alive. Check `http://127.0.0.1:3582` returns a response (even a 404 or redirect is fine — just confirm the port is alive).

4. **Verify WebSocket endpoint locally** — Use a CLI WebSocket tool (e.g. `websocat ws://127.0.0.1:3582/api/ws` or a minimal Python `websockets.connect`) to open a raw connection. Confirm the handshake completes without error.

5. **Send a JSON-RPC handshake** — Over the local WebSocket, send `{"jsonrpc":"2.0","method":"session.list","id":1}` and confirm a valid JSON-RPC response comes back (even an empty list is fine).

6. **Auto-start on boot (optional)** — Create a systemd unit (Linux) or scheduled task (Windows) so the dashboard restarts automatically after reboots.

## Network: Nginx Reverse Proxy

7. **Install Caddy on edge host** — Ensure Caddy is installed and running on the Oracle Linux cloud instance that has a public IP.

8. **Register a dynamic DNS hostname** — Use DuckDNS or similar to get a stable public hostname (e.g. `your-box.duckdns.org`) pointing at the cloud instance's public IP.

9. **Set up SSL with Let's Encrypt** — Configure Caddy to automatically obtain and renew SSL certificates for the hostname. Confirm `https://your-box.duckdns.org` loads without certificate warnings.

10. **Generate the shared secret** — Create a long random hex string (e.g. `openssl rand -hex 32`) to use as the `X-Hermes-Auth` header value. Store it securely; both Caddy and the Flet client need it.

11. **Create the Caddy proxy config file** — Write `/etc/caddy/Caddyfile` with the `reverse_proxy` block, the `tls` block for SSL certs, and the `/api/ws` route as specified in the spec.

12. **Wire the auth gate check** — Inside the `/api/ws` route, add the `if ($http_x_hermes_auth != "...") { return 403; }` guard exactly as spec'd.

13. **Wire the WebSocket upgrade headers** — Ensure `proxy_http_version 1.1`, `proxy_set_header Upgrade $http_upgrade`, and `proxy_set_header Connection $connection_upgrade` are present.

14. **Point proxy_pass to the backend** — Set `proxy_pass http://127.0.0.1:3582;` (Caddy runs on the same box as Hermes, or adjust IP if separate).

15. **Test Caddy config and reload** — Run `caddy validate --config /etc/caddy/Caddyfile` to validate syntax, then `systemctl reload caddy` to apply.

16. **Test auth rejection** — From an external machine, run `curl -i https://your-box.duckdns.org/api/ws` without the header and confirm a `403 Forbidden` response.

17. **Test WebSocket end-to-end with auth** — From an external machine, use `websocat` or a Python script to connect to `wss://your-box.duckdns.org/api/ws` with the `X-Hermes-Auth` header set. Confirm the connection upgrades and a JSON-RPC call works through the proxy.

 

## Flet Client: Project Scaffolding

19. **Initialize Python project with uv** — In the `src/` folder, run `uv init` (or create `pyproject.toml`) to set up the project environment.

20. **Add Flet dependency** — Run `uv add flet` to pull in the Flet framework.

21. **Add websockets dependency** — Run `uv add websockets` for the async WebSocket client library.

22. **Create main entry point** — Create `src/main.py` as the app entry point with a minimal `ft.app(target=main)` call that opens a blank window.

23. **Verify Flet runs on desktop** — Run `uv run src/main.py` and confirm a blank Flet window appears on the dev machine.

## Flet Client: Configuration & Secrets

24. **Create a config module** — Create `src/config.py` to hold `WSS_URL` and `SECRET_KEY` constants, read from environment variables with sensible fallback defaults for dev.

25. **Add .env file support** — Optionally use `python-dotenv` so secrets can live in a `.env` file (gitignored) rather than hardcoded.

26. **Add client_storage persistence for settings** — On first launch, if `WSS_URL` / `SECRET_KEY` are not set in env, show text fields for the user to enter them, then persist with `page.client_storage.set(...)` so they survive app restarts.

27. **Load persisted settings on startup** — In `main()`, read `page.client_storage` for saved URL/key and feed them into the config before connecting.

## Flet Client: WebSocket Connection

28. **Write the async WebSocket listener skeleton** — Create an `async def websocket_listener(page, chat_column)` function that opens a `websockets.connect` to `WSS_URL` with the `X-Hermes-Auth` extra header.

29. **Store connection on page session** — After connect, call `page.session.set("ws_conn", ws)` so other handlers can access the WebSocket.

30. **Send session.list on connect** — Immediately after connect, send `{"jsonrpc":"2.0","method":"session.list","id":100}` to bootstrap the session list.

31. **Enter the async message loop** — Use `async for message in ws:` to read messages indefinitely. Parse each message with `json.loads`.

32. **Handle connection errors gracefully** — Wrap the connect + loop in try/except, show a red banner (`ft.Banner`) on the page if connection fails, and offer a "Retry" button.

33. **Auto-reconnect with backoff** — On disconnect, wait N seconds (exponential backoff: 1s, 2s, 4s, 8s, max 30s), then retry the connection automatically.

## Flet Client: Chat Message Rendering

34. **Create the chat Column** — A `ft.Column` with `scroll=ft.ScrollMode.AUTO`, `expand=True`, placed inside a `ft.Container` that fills available height.

35. **Define a message bubble widget** — A reusable function `build_message_bubble(role, text)` that returns a `ft.Container` styled differently for "user" vs "assistant" (different background colors, alignment).

36. **Render incoming `message.delta` chunks** — When the listener receives `{"method":"message.delta","params":{"text":"..."}}`, append the text to the current assistant bubble. If no assistant bubble exists as the last message, create one first.

37. **Render full `message.complete` events** — On `message.complete`, mark the current assistant bubble as finished (e.g. remove a typing indicator).

38. **Render `session.activated` notifications** — When `session.activated` arrives, insert an info-style chip/divider in the chat showing "Switched to session: X".

39. **Scroll to bottom on new messages** — After each `page.update()`, scroll the chat Column to the bottom so the latest content is always visible.

40. **Auto-scroll toggle** — Add a small floating "↓" button that appears when the user has scrolled up away from the bottom. Tapping it resumes auto-scroll.

## Flet Client: Message Input

41. **Create the input bar** — A `ft.Row` at the bottom of the page containing a `ft.TextField` (expandable, multiline) and a send `ft.IconButton`.

42. **Wire the send action** — On send button tap (or Enter key), construct a JSON-RPC payload: `{"jsonrpc":"2.0","method":"command.dispatch","params":{"command":"<user text>"},"id":<auto-increment>}`, send it through the stored WebSocket, then clear the input field.

43. **Show sent message immediately** — Append the user's message as a user-styled bubble to the chat Column right away (optimistic UI), before the server echoes it back.

44. **Increment message ID counter** — Maintain a simple `msg_id` counter that increments with each sent payload so every JSON-RPC request has a unique `id`.

## Flet Client: Command Buttons

45. **Create a command bar** — A horizontal `ft.Row` of small `ft.ElevatedButton` / `ft.Chip` widgets above the input bar for quick actions.

46. **Wire `/forget` button** — Sends `{"jsonrpc":"2.0","method":"command.dispatch","params":{"command":"/forget"},"id":X}`. On success, clear the local chat Column to match server state.

47. **Wire `/model` switcher** — A dropdown or button that sends `{"jsonrpc":"2.0","method":"command.dispatch","params":{"command":"/model <model_name>"},"id":X}`. Populate the model list from a hardcoded list or from a `session.config` response.

48. **Wire session switcher** — A dropdown populated from the `session.list` response. Selecting a session sends `{"jsonrpc":"2.0","method":"session.activate","params":{"session_id":"..."},"id":X}` and clears/reloads the chat view.

49. **Add a reconnect button** — A manual "Reconnect" button in the command bar that tears down the current WebSocket and re-runs the listener.

## Flet Client: UI Polish (Material Design)

50. **Apply a Material 3 theme** — Set `page.theme_mode = ft.ThemeMode.SYSTEM` and define a `page.theme = ft.Theme(color_scheme_seed="indigo")` for a coherent color palette.

51. **Style the app bar** — Add a `ft.AppBar` with the title "Cadux", a settings gear icon, and a connection status indicator (green dot = connected, red = disconnected).

52. **Style message bubbles** — User bubbles: right-aligned, filled background. Assistant bubbles: left-aligned, outlined or subtle fill. Add subtle border-radius (12-16px) for a chat-app feel.

53. **Add a typing indicator** — While waiting for `message.delta` after sending a message, show an animated "..." inside the assistant bubble.

54. **Add empty-state placeholder** — When the chat Column is empty, show a centered welcome message with the Cadux logo/name and a brief prompt.

55. **Responsive layout** — Use `page.width` / `page.height` to adjust padding and font sizes for phone vs tablet vs desktop. Target ~360-414dp wide (Android phone) as the primary breakpoint.

56. **Dark mode support** — Ensure all colors are derived from the theme rather than hardcoded, so `ThemeMode.SYSTEM` automatically gives a dark variant at night.

57. **Add haptic/tap feedback** — Use `page.haptic_feedback` or button `on_feedback` callbacks for tactile response on send and command buttons (Android-native feel).

## Flet Client: Session & Thread Management

58. **Parse `session.list` response** — When the listener receives the response to `id:100`, extract the array of sessions. Store them in a local list for the session switcher dropdown.

59. **Handle `session.created` events** — If the server pushes a new session creation event, append it to the session list and refresh the dropdown.

60. **Handle `session.deleted` events** — Remove the session from the local list and, if it was the active session, clear the chat view.

61. **Persist last active session ID** — Save the current session ID in `page.client_storage` so reconnecting brings the user back to the same thread.

62. **Restore last session on reconnect** — After a successful reconnect, send `session.activate` with the persisted session ID from client_storage.

## Flet Client: Package for Android

63. **Install Android SDK / build tools** — Set up the Android SDK, NDK, and required build tools on the dev machine (or use a CI pipeline).

64. **Configure Flet for Android build** — Follow Flet's Android packaging guide: set app name, package ID (`com.cadux.app`), icon assets, and signing keys.

65. **Run `flet build apk`** — Produce a debug APK. Install it on a physical Android device and verify it launches.

66. **Test end-to-end on device** — On the phone (on cellular or a different WiFi network), open Cadux, enter the WSS URL and secret, and confirm messages flow through the full stack: Phone → Nginx → Hermes → Nginx → Phone.

67. **Sign release APK** — Generate a proper keystore, sign the APK for release, and produce a production-signed build.

68. **Test notification handling** — Verify the app behaves correctly when backgrounded/foregrounded (WebSocket reconnects, state is preserved).

## Polish & Hardening

69. **Add error toasts** — Show `ft.SnackBar` notifications for connection drops, auth failures (403), timeouts, and invalid JSON responses.

70. **Add message timestamps** — Each bubble shows a small timestamp (e.g. "14:32") below the text.

71. **Add copy-to-clipboard** — Long-press or tap on a message bubble copies its text to the clipboard.

72. **Add connection quality indicator** — Show ping/latency in the app bar or settings page (send a lightweight ping JSON-RPC periodically).

73. **Add scroll-to-top "load more"** — If the user scrolls to the very top, send a request to load older messages (if the backend supports pagination).

74. **Write a README** — Document how to set up the full stack: Hermes, Nginx, and Cadux client, with config examples.

75. **Write a TEST_LOG.md entry** — Document each validation step result (local WebSocket ping, proxy auth rejection test, first end-to-end message on device).
