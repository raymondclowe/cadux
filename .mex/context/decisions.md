---
name: decisions
description: Key architectural and technical decisions with reasoning. Load when making design choices or understanding why something is built a certain way.
triggers:
  - "why do we"
  - "why is it"
  - "decision"
  - "alternative"
  - "we chose"
edges:
  - target: context/architecture.md
    condition: when a decision relates to system structure
  - target: context/stack.md
    condition: when a decision relates to technology choice
last_updated: 2026-06-17
---

# Decisions

## Decision Log

### REST + SSE instead of WebSockets for Hermes communication
**Date:** 2025-06
**Status:** Active
**Decision:** Use Hermes REST API with SSE streaming (`POST /api/sessions/{id}/chat/stream`) instead of raw WebSockets with JSON-RPC.
**Reasoning:** The Hermes agent gateway exposes a REST API natively. Using it directly avoids the need for a WebSocket proxy layer (nginx/Caddy with upgrade headers) that was spec'd in the original plan. The file `ws_client.py` retains its name for historical reasons but uses only HTTP.
**Alternatives considered:** WebSockets via `websockets` library with JSON-RPC 2.0 (rejected — required a proxy with WebSocket upgrade support, added deployment complexity).
**Consequences:** All communication is stateless HTTP. The REST listener polls `/api/sessions` every 5 seconds. No persistent connection to manage beyond the SSE stream duration. Auto-reconnect is simpler.

### Flet for cross-platform UI
**Date:** 2025-06
**Status:** Active
**Decision:** Use Flet as the UI framework for both Android (APK) and desktop (Windows/macOS/Linux) from a single Python codebase.
**Reasoning:** Flet compiles to native Android APKs via Flutter embedding and runs natively on desktop. One codebase, one language (Python), no JavaScript/ Dart required. Material Design widgets are built in.
**Alternatives considered:** Kivy (rejected — steeper learning curve, less polished Material widgets), React Native + separate Python backend (rejected — two codebases, two languages), Flutter/Dart directly (rejected — requires learning Dart, loses Python ecosystem).
**Consequences:** UI must use Flet's widget model (no HTML/CSS). Async must go through `page.run_task()`. Android builds require Android SDK + JDK 17+.

### XOR+SHA256 for pairing encryption (not a crypto library)
**Date:** 2025-06
**Status:** Active
**Decision:** Use XOR with a SHA256-derived key for encrypting the Hermes config during the PIN-based pairing exchange, with MD5 for integrity verification.
**Reasoning:** The pairing flow is ephemeral (60-second TTL), single-use, and the PIN is communicated out-of-band (user types it from Hermes chat). The encryption's job is to prevent passive eavesdropping on the LAN, not to resist active attacks. Using stdlib only (no `cryptography` dependency) keeps the APK smaller and avoids native compilation issues on Android.
**Alternatives considered:** Fernet symmetric encryption (rejected — adds `cryptography` dependency which complicates Android builds), TLS for the paird connection (rejected — requires certificate management on LAN IPs).
**Consequences:** The encryption is not authenticated (XOR, not AES-GCM). MD5 is used only as a checksum against accidental corruption, not as a security hash. An active MITM on the LAN could modify the config. Acceptable for the threat model (LAN pairing, 60-second window).

### Multi-profile via client_storage (not a database)
**Date:** 2025-06
**Status:** Active
**Decision:** Persist connection profiles in Flet's `page.client_storage` (platform key-value store) rather than a local database.
**Reasoning:** Profiles are small JSON blobs (a few hundred bytes each). The number of profiles is typically 1-5. A full database adds complexity, migration burden, and Android permissions for no benefit at this scale.
**Alternatives considered:** SQLite via `sqlite3` (rejected — overkill for 1-5 JSON records), a JSON file in the app directory (rejected — `client_storage` handles platform-specific paths automatically).
**Consequences:** Profile data is lost if the app data is cleared on Android. No migration system — profile schema changes require manual compatibility code in `load_profiles()`.

### No test framework yet
**Date:** 2025-06
**Status:** Active
**Decision:** Defer test infrastructure. The project is in strategy development/testing phase, not production hardening.
**Reasoning:** Per AGENTS.md: "This repo is currently for strategy development/testing, not production hardening. During strategy development, do not add defensive scaffolding unless explicitly requested."
**Alternatives considered:** pytest (deferred — will be added when the codebase stabilizes).
**Consequences:** No automated test coverage. `TEST_LOG.md` serves as a manual test checklist. Bugs may be discovered late.
