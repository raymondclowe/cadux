Component Specification1. Backend: The Hermes WebSocket Daemon (tui_gateway/ws.py)Instead of launching via hermes gateway, you will call the visual dashboard wrapper which exposes the underlying JSON-RPC 2.0 protocol over WebSockets.Default Port: 3582 (Bound strictly to localhost 127.0.0.1 to prevent malicious external access).Protocol Layer: JSON-RPC 2.0 payloads handling persistent variables (session.activate, command.dispatch).2. Network Proxy Layer: Nginx Event-Driven ProxyA hardened instance of Nginx acts as the edge gateway. Nginx is selected because its asynchronous event-driven loop handles persistent, long-running WebSockets better than resource-heavy multi-threaded proxies.Authentication Enforcer: Intercepts traffic at the cloud edge and demands high-entropy custom headers to block random internet bots and scanners.TLS/SSL Termination: Encrypts raw traffic (ws://) into a secure stream (wss://) using a free Let's Encrypt certificate, preventing credential sniffing on mobile or public cellular networks.3. Client Frontend: Custom Android Flet EngineA native Python/Flutter app deployed directly onto your Android device as an APK.State Machine: Maintains local state for real-time string concatenation (message.delta chunk rendering) and interactive widget popups (approval.request alerts for automated tool steps).Step-by-Step Implementation SpecStep 1: Start the State-Aware BackendRun the Hermes dashboard background service. This initializes the FastAPI web stack and registers the WebSocket router. Ensure it is configured via system env to only listen on your local loopback address:bash# Force the web server to bind to local loopback only
export HERMES_WEB_HOST="127.0.0.1"
export HERMES_WEB_PORT="3582"

# Start the dashboard process in the background
hermes dashboard --no-browser
Use code with caution.Step 2: Configure the Nginx Dumb ProxyCreate an Nginx server block configuration on your Oracle Linux instance (typically at /etc/nginx/conf.d/hermes_proxy.conf).This configuration passes persistent websocket connections through the firewall, enforces an arbitrary secret handshake key (X-Hermes-Auth), and keeps connection tracking low on memory:nginxmap $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}

server {
    listen 443 ssl;
    server_name your-oracle-domain.duckdns.org; # Replace with your dynamic DNS/IP

    # SSL Security Parameters (Managed via Certbot)
    ssl_certificate /etc/letsencrypt/live/your-oracle-domain.duckdns.org/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-oracle-domain.duckdns.org/privkey.pem;

    # Adjust timeouts to prevent proxy drops during deep LLM thinking tasks
    proxy_read_timeout 3600s;
    proxy_send_timeout 3600s;

    location /api/ws {
        # Strict Dumb Gatekeeping Layer: Drops connection if the app misses the key
        if ($http_x_hermes_auth != "YOUR_GENERATED_LONG_HEX_SECRET_STRING") {
            return 403;
        }

        # Route directly to the internal TUI websocket handler
        proxy_pass http://127.0.0;
        
        # Mandatory WebSocket Protocol Upgrade Headers
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        
        # Forward Client Network Information safely
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
Use code with caution.Step 3: Implement the Flet Mobile Async Client LoopIn your Flet Python script, utilize the websockets library wrapped inside an asynchronous event handler. This structure maps the incoming JSON-RPC chunks straight into your customized Material Design chat view:pythonimport asyncio
import json
import flet as ft
import websockets

WSS_URL = "wss://your-oracle-domain.duckdns.org/api/ws"
SECRET_KEY = "YOUR_GENERATED_LONG_HEX_SECRET_STRING"

async def websocket_listener(page: ft.Page, chat_column: ft.Column):
    headers = {"X-Hermes-Auth": SECRET_KEY}
    
    # Establish persistent secure connection directly over the internet
    async with websockets.connect(WSS_URL, extra_headers=headers) as ws:
        page.session.set("ws_conn", ws)
        
        # Trigger an initial session retrieval to load native threads
        init_payload = {
            "jsonrpc": "2.0",
            "method": "session.list",
            "id": 100
        }
        await ws.send(json.dumps(init_payload))

        # Main Event Processing Loop
        async for message in ws:
            data = json.loads(message)
            
            # Handle real-time token streaming
            if data.get("method") == "message.delta":
                chunk = data["params"]["text"]
                # Logic to append chunk to the active message box goes here
                
            # Handle native context adjustments (Slash commands updating server state)
            elif data.get("method") == "session.activated":
                new_session_id = data["params"]["session_id"]
                chat_column.controls.append(ft.Text(f"[Switched to Session: {new_session_id}]", color="blue"))
                
            page.update()

def main(page: ft.Page):
    page.title = "Sane Mobile Hermes"
    chat_column = ft.Column(scroll=ft.ScrollMode.AUTO, expand=True)
    
    # Run the background async loop cleanly inside Flet's wrapper
    page.run_task(websocket_listener, chat_column)
    page.add(chat_column)

ft.app(target=main)
Use code with caution.Protocol Payloads Quick ReferenceWhen writing your Flet frontend button actions, use the following payload formats to interact with native Hermes functions over your proxy connection:To Switch/Resume a Thread:json{"jsonrpc": "2.0", "method": "session.activate", "params": {"session_id": "backup-logs-thread-xyz"}, "id": 3}
Use code with caution.To Clear/Forget Session State:json{"jsonrpc": "2.0", "method": "command.dispatch", "params": {"command": "/forget"}, "id": 4}
Use code with caution.To Change Backend Model Dynamically:json{"jsonrpc": "2.0", "method": "command.dispatch", "params": {"command": "/model openrouter/deepseek/deepseek-chat"}, "id": 5}
Use code with caution.If
