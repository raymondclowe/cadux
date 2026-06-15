#!/usr/bin/env bash
# ── Cadux Pairing — Hermes Skill Installer (Linux/macOS) ────────────
# Installs paird daemon + Hermes skill into the current user's
# Hermes installation.
#
# Usage:
#   bash install.sh              # auto-detect HERMES_HOME
#   HERMES_HOME=... bash install.sh   # explicit path
#
# Run this from the paird/ directory (or adjust SKILL_SRC below).
set -euo pipefail

SKILL_NAME="cadux-pairing"
SKILL_SRC="$(cd "$(dirname "$0")/skills/$SKILL_NAME" && pwd)"
PAIRD_SRC="$(cd "$(dirname "$0")" && pwd)/server.py"

# Detect Hermes home
if [ -z "${HERMES_HOME:-}" ]; then
    if [ -d "$HOME/.hermes" ]; then
        HERMES_HOME="$HOME/.hermes"
    elif [ -d "$HOME/AppData/Local/hermes" ]; then
        HERMES_HOME="$HOME/AppData/Local/hermes"
    else
        echo "ERROR: Could not find Hermes installation."
        echo "Set HERMES_HOME and re-run, e.g.:"
        echo "  HERMES_HOME=/path/to/hermes bash install.sh"
        exit 1
    fi
fi

SKILL_DIR="$HERMES_HOME/skills/$SKILL_NAME"
SCRIPTS_DIR="$SKILL_DIR/scripts"
PAIRD_DIR="$(dirname "$SKILL_DIR")/.."

echo "Installing Cadux Pairing skill..."
echo "  Hermes home:  $HERMES_HOME"
echo "  Skill dir:    $SKILL_DIR"
echo "  Paird src:    $PAIRD_SRC"

# Create skill directory structure
mkdir -p "$SCRIPTS_DIR"

# Copy skill files
cp "$SKILL_SRC/SKILL.md" "$SKILL_DIR/"
cp "$SKILL_SRC/scripts/paird_manager.py" "$SCRIPTS_DIR/"
chmod +x "$SCRIPTS_DIR/paird_manager.py"

# Copy paird daemon to hermes/skills/cadux-pairing/ (sibling to scripts/)
cp "$PAIRD_SRC" "$SKILL_DIR/"
chmod +x "$SKILL_DIR/server.py"

# Install aiohttp if needed
if ! python3 -c "import aiohttp" 2>/dev/null; then
    echo "Installing aiohttp dependency..."
    pip install aiohttp 2>/dev/null || python3 -m pip install aiohttp 2>/dev/null || {
        echo "WARNING: Could not install aiohttp. Install it manually:"
        echo "  pip install aiohttp"
    }
fi

echo ""
echo "✓ Cadux Pairing skill installed!"
echo ""
echo "To verify:"
echo "  python3 $SCRIPTS_DIR/paird_manager.py status"
echo ""
echo "To start the pairing daemon:"
echo "  python3 $SCRIPTS_DIR/paird_manager.py start"
echo ""
echo "For Cadux to connect, the daemon needs to know your Hermes API URL and key."
echo "The manager auto-detects them from your Hermes config, or you can set:"
echo "  export CADUX_API_URL=http://localhost:8642"
echo "  export CADUX_SECRET_KEY=your-api-key"
echo ""
echo "Refresh Hermes skills to activate:"
echo "  (Restart Hermes or run the skills refresh command)"
