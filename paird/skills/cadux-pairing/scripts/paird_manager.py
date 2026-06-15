#!/usr/bin/env python3
"""
paird_manager.py — Hermes tool for the Cadux pairing daemon.

Commands:
  start     Start the paird daemon (reads Hermes API config automatically)
  stop      Stop the running daemon
  restart   Restart the daemon
  status    Check if paird is running and return its URL

Usage:
  python3 paird_manager.py start
  python3 paird_manager.py status
  python3 paird_manager.py stop
"""

import argparse
import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request

# ── Constants ────────────────────────────────────────────────────────

# Find server.py — supports both installed (../server.py) and dev (../../../../server.py) layouts
_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
for _rel in ("..", "../../..", "../../../paird"):
    _candidate = os.path.normpath(os.path.join(_SCRIPTS_DIR, _rel, "server.py"))
    if os.path.exists(_candidate):
        PAIRD_SCRIPT = _candidate
        break
else:
    PAIRD_SCRIPT = os.path.join(_SCRIPTS_DIR, "..", "server.py")  # best guess

PID_FILE = os.path.join(os.path.dirname(PAIRD_SCRIPT), "paird.pid")
LOG_FILE = os.path.join(os.path.dirname(PAIRD_SCRIPT), "paird.log")
DEFAULT_PORT = 8643

HERMES_HOME = os.environ.get(
    "HERMES_HOME",
    os.path.join(os.environ.get("LOCALAPPDATA", ""), "hermes"),
)


def _find_hermes_config():
    """Try to find Hermes API URL and secret key from common locations.

    Returns (api_url, secret_key) or (None, None).
    """
    # 1. Environment variables
    api_url = os.environ.get("CADUX_API_URL") or os.environ.get("HERMES_API_URL")
    secret_key = os.environ.get("CADUX_SECRET_KEY") or os.environ.get("HERMES_API_KEY")

    # 2. Hermes .env file
    if not api_url or not secret_key:
        env_paths = [
            os.path.join(HERMES_HOME, ".env"),
            os.path.join(os.path.dirname(PAIRD_SCRIPT), "..", ".env"),
            os.path.join(os.path.expanduser("~"), ".hermes", ".env"),
        ]
        for env_path in env_paths:
            if os.path.exists(env_path):
                try:
                    with open(env_path, encoding="utf-8", errors="replace") as f:
                        for line in f:
                            line = line.strip()
                            if line.startswith("CADUX_API_URL=") and not api_url:
                                api_url = line.split("=", 1)[1].strip().strip("\"'")
                            elif line.startswith("CADUX_SECRET_KEY=") and not secret_key:
                                secret_key = line.split("=", 1)[1].strip().strip("\"'")
                            elif line.startswith("HERMES_API_URL=") and not api_url:
                                api_url = line.split("=", 1)[1].strip().strip("\"'")
                            elif line.startswith("HERMES_API_KEY=") and not secret_key:
                                secret_key = line.split("=", 1)[1].strip().strip("\"'")
                except OSError:
                    pass

    # 3. Hermes gateway service env vars (API_SERVER_HOST/PORT/KEY)
    #    These are set by Hermes_Gateway.cmd / Hermes_Gateway.sh at launch.
    if not api_url or not secret_key:
        host = os.environ.get("API_SERVER_HOST") or "127.0.0.1"
        port = os.environ.get("API_SERVER_PORT") or "8642"
        key = os.environ.get("API_SERVER_KEY")
        if key and not secret_key:
            secret_key = key
        if not api_url:
            api_url = f"http://{host}:{port}"

    # 4. Hermes gateway .cmd/.sh file (hardcoded env vars)
    if not api_url or not secret_key:
        gateway_candidates = [
            os.path.join(HERMES_HOME, "gateway-service", "Hermes_Gateway.cmd"),
            os.path.join(HERMES_HOME, "gateway-service", "Hermes_Gateway.sh"),
        ]
        for gw_path in gateway_candidates:
            if os.path.exists(gw_path):
                try:
                    with open(gw_path, encoding="utf-8", errors="replace") as f:
                        gw_key = None
                        gw_host = None
                        gw_port = None
                        for line in f:
                            line = line.strip()
                            if line.startswith("set "):
                                parts = line[4:].split("=", 1)
                                if len(parts) == 2:
                                    k, v = parts[0].strip(), parts[1].strip()
                                    if k == "API_SERVER_KEY" and not gw_key:
                                        gw_key = v
                                    elif k == "API_SERVER_HOST" and not gw_host:
                                        gw_host = v
                                    elif k == "API_SERVER_PORT" and not gw_port:
                                        gw_port = v
                        if gw_key and not secret_key:
                            secret_key = gw_key
                        if not api_url:
                            gw_host = gw_host or "127.0.0.1"
                            gw_port = gw_port or "8642"
                            api_url = f"http://{gw_host}:{gw_port}"
                except OSError:
                    pass

    # 5. Hermes config.yaml
    if not api_url or not secret_key:
        config_yaml = os.path.join(HERMES_HOME, "config.yaml")
        if os.path.exists(config_yaml):
            try:
                with open(config_yaml, encoding="utf-8", errors="replace") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("api_url:") and not api_url:
                            api_url = line.split(":", 1)[1].strip()
                        elif line.startswith("api_key:") and not secret_key:
                            secret_key = line.split(":", 1)[1].strip()
                        elif line.startswith("secret_key:") and not secret_key:
                            secret_key = line.split(":", 1)[1].strip()
            except OSError:
                pass

    return api_url, secret_key


# ── Daemon management ────────────────────────────────────────────────


def cmd_status(args) -> str:
    """Check if paird is running."""
    if not os.path.exists(PID_FILE):
        return json.dumps({"status": "stopped", "url": None, "port": DEFAULT_PORT})

    with open(PID_FILE) as f:
        pid = int(f.read().strip())

    running = _is_pid_alive(pid)
    if not running:
        os.remove(PID_FILE)
        return json.dumps({"status": "stopped", "url": None, "port": DEFAULT_PORT})

    port = args.port or DEFAULT_PORT
    url = f"http://0.0.0.0:{port}"

    # Quick health check
    healthy = _check_health(port)
    return json.dumps({
        "status": "running" if healthy else "starting",
        "pid": pid,
        "url": url,
        "port": port,
        "healthy": healthy,
    })


def cmd_start(args) -> str:
    """Start the paird daemon as a background process."""
    # Check if already running
    status = json.loads(cmd_status(args))
    if status["status"] == "running":
        return json.dumps({"status": "already_running", "url": status["url"], "pid": status["pid"]})

    # Find Hermes config
    api_url, secret_key = _find_hermes_config()
    if not api_url or not secret_key:
        return json.dumps({
            "status": "error",
            "error": "Could not find Hermes API config. Set CADUX_API_URL and CADUX_SECRET_KEY env vars, or ensure Hermes is configured.",
        })

    port = args.port or DEFAULT_PORT

    # Build env for the subprocess
    proc_env = os.environ.copy()
    proc_env["CADUX_API_URL"] = api_url
    proc_env["CADUX_SECRET_KEY"] = secret_key
    proc_env["PAIRD_PORT"] = str(port)

    # Start the daemon
    try:
        proc = subprocess.Popen(
            [sys.executable, PAIRD_SCRIPT],
            env=proc_env,
            stdout=open(LOG_FILE, "a"),
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
            start_new_session=True,
        )
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)})

    # Write PID file
    with open(PID_FILE, "w") as f:
        f.write(str(proc.pid))

    # Wait for health
    for _ in range(10):
        time.sleep(0.5)
        if _check_health(port):
            return json.dumps({
                "status": "started",
                "pid": proc.pid,
                "url": f"http://<server-ip>:{port}",
                "port": port,
                "note": "Use the IP of this machine (not localhost) for devices on the LAN.",
            })

    return json.dumps({
        "status": "started_but_unhealthy",
        "pid": proc.pid,
        "port": port,
        "url": f"http://<server-ip>:{port}",
        "warning": "Daemon started but health check failed. Check logs: " + LOG_FILE,
    })


def cmd_initiate(args) -> str:
    """Tell paird to initiate pairing now (Hermes has approved).
    Calls POST /initiate on the daemon and returns the correct code.
    """
    port = args.port or DEFAULT_PORT
    # Find the paird daemon URL
    paird_url = f"http://127.0.0.1:{port}"
    try:
        req = urllib.request.Request(
            f"{paird_url}/initiate",
            method="POST",
            data=b"{}",
            headers={"Content-Type": "application/json"},
        )
        resp = urllib.request.urlopen(req, timeout=5.0)
        data = json.loads(resp.read().decode())
        return json.dumps({
            "status": "success",
            "correct_code": data["correct_code"],
            "session_id": data.get("session_id"),
        })
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        try:
            err_data = json.loads(body)
            return json.dumps({"status": "error", "error": err_data.get("error", body)})
        except json.JSONDecodeError:
            return json.dumps({"status": "error", "error": body})
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)})


def cmd_stop(args) -> str:
    """Stop the running paird daemon."""
    if not os.path.exists(PID_FILE):
        return json.dumps({"status": "not_running"})

    with open(PID_FILE) as f:
        pid = int(f.read().strip())

    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
        else:
            os.kill(pid, signal.SIGTERM)
            # Give it a moment, then force kill
            try:
                os.kill(pid, 0)  # check if alive
                time.sleep(1)
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    except Exception as e:
        # If PID is stale, clean up
        pass

    os.remove(PID_FILE)
    return json.dumps({"status": "stopped", "pid": pid})


# ── Helpers ──────────────────────────────────────────────────────────


def _is_pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False
    except OSError:
        return False


def _check_health(port: int) -> bool:
    try:
        resp = urllib.request.urlopen(
            f"http://127.0.0.1:{port}/discover",
            timeout=1.0,
        )
        return resp.status == 200
    except (urllib.error.URLError, OSError):
        return False


# ── Main ─────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="Cadux Pairing Daemon Manager")
    parser.add_argument("command", choices=["start", "stop", "restart", "status", "initiate"])
    parser.add_argument("--port", type=int, default=None, help="Port for paird (default: 8643)")
    args = parser.parse_args()

    if args.command == "status":
        output = cmd_status(args)
    elif args.command == "start":
        output = cmd_start(args)
    elif args.command == "stop":
        output = cmd_stop(args)
    elif args.command == "initiate":
        output = cmd_initiate(args)
    elif args.command == "restart":
        stop_out = cmd_stop(args)
        start_out = cmd_start(args)
        output = json.dumps({"stop": json.loads(stop_out), "start": json.loads(start_out)})

    print(output)


if __name__ == "__main__":
    main()
