# Cadux Test Log

> Mark each checkpoint `✅ PASS` or `❌ FAIL` as you test.

## 1. App Launch

- [ ] **1.1** App starts without errors: `uv run python -m src.main`
- [ ] **1.2** No deprecation warnings in terminal output
- [ ] **1.3** Native Flet window appears with title "Cadux"
- [ ] **1.4** App bar shows Forum icon + "Cadux" text
- [ ] **1.5** Status dot visible in app bar (grey initially)

## 2. Settings Dialog

- [ ] **2.1** With no `.env` and no stored config, settings dialog appears on launch
- [ ] **2.2** Dialog has WSS URL and Secret Key fields
- [ ] **2.3** Saving with empty fields does nothing (dialog stays open)
- [ ] **2.4** Saving with valid values closes dialog and continues to main UI
- [ ] **2.5** Settings gear icon re-opens dialog with pre-filled values
- [ ] **2.6** After re-opening settings, changing values persists correctly

## 3. Connection

- [ ] **3.1** Status dot turns amber during connection attempt
- [ ] **3.2** Status dot turns green on successful WebSocket connection
- [ ] **3.3** Status dot turns red on connection failure
- [ ] **3.4** Auto-reconnect works: killing Hermes and restarting it reconnects
- [ ] **3.5** Exponential back-off visible (reconnect intervals increase)

## 4. Chat

- [ ] **4.1** Empty state ("Connected to Hermes") visible before any messages
- [ ] **4.2** Empty state hides after first message is sent
- [ ] **4.3** Empty state reappears after all sessions are deleted
- [ ] **4.4** Typing a message and pressing Enter sends it (user bubble appears)
- [ ] **4.5** Shift+Enter inserts a newline (does not send)
- [ ] **4.6** Streaming response renders token-by-token in an assistant bubble
- [ ] **4.7** Multiline messages display correctly in bubbles

## 5. Sessions

- [ ] **5.1** Session dropdown populated on connect (from `session.list` response)
- [ ] **5.2** Selecting a session from dropdown dispatches `session.activate`
- [ ] **5.3** Session chip appears in chat on `session.activated` event
- [ ] **5.4** A new session is created for first message if none active
- [ ] **5.5** `/forget` command clears chat and dispatches forget

## 6. UI / Responsiveness

- [ ] **6.1** Window width < 400 px: padding = 2 px
- [ ] **6.2** Window width 400–600 px: padding = 4 px
- [ ] **6.3** Window width ≥ 600 px: padding = 64 px sides
- [ ] **6.4** User bubbles right-aligned with primary container color
- [ ] **6.5** Assistant bubbles left-aligned with surface container color
- [ ] **6.6** Timestamps visible below bubbles
- [ ] **6.7** Send button works (IconButton next to text field)
- [ ] **6.8** Model dropdown shows available models

## 7. Error Handling

- [ ] **7.1** Invalid WSS URL shows connection failure (red dot)
- [ ] **7.2** Wrong secret key returns 403 / auth error
- [ ] **7.3** Network disconnection during streaming recovers gracefully
- [ ] **7.4** Reconnect button forces immediate reconnection attempt

## 8. Android Build

- [ ] **8.1** `flet build apk` completes without errors
- [ ] **8.2** APK installs on Android device
- [ ] **8.3** App opens and shows settings dialog (first launch)
- [ ] **8.4** Connection works over mobile data / WiFi

---

## History

| Date | Checkpoints | Result |
|------|-------------|--------|
|      |             |        |
