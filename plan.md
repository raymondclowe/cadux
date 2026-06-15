Phase 1: Environment & "Hello World" (Validation)
Before building the full stack, verify that your core technologies can talk to each other. Do not try to build the UI yet; focus on the connection.

Backend Proof-of-Concept: Ensure your local machine can run the Hermes dashboard background service and bind to your specified localhost port (3582).

Proxy Tunneling: Verify you can reach that port from an external device (like your phone on a different network) through your Nginx proxy. Test this using a simple tool like curl or a WebSocket testing client (not your app yet) to confirm the custom header authentication (X-Hermes-Auth) is actually passing through.

Flet "Ping" Test: Create a minimal Flet app that does nothing but attempt to connect to your WebSocket URL and print "Connection Successful" to the debug console.

Phase 2: Building the "Mobile" Core (MVP)
Once the connection is stable, build the minimal interaction loop.

State Management: Implement the async loop mentioned in your spec.md using websockets and flet.

Message Rendering: Build a single, scrollable ft.Column that accepts and renders text chunks as they arrive from the WebSocket.

Command Dispatch: Create one simple button in your Flet UI that sends a pre-defined JSON payload to clear the session or switch models. Once that works, expand to other commands.

Phase 3: The "UX" Polish
Only after the data is flowing should you focus on how it looks.

Material Design: Utilize Flet's Material 3 controls to make the chat interface feel native.

Persistence: Add local storage (using Flet's page.client_storage) to save your connection string and credentials so you don't have to re-enter them every time the app restarts.
