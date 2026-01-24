#!/bin/bash

# Gmail Cleaner Bot - Management Script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PATH="$SCRIPT_DIR/venv"
PYTHON="$VENV_PATH/bin/python"

# Load variables from .env if exists
if [ -f "$SCRIPT_DIR/.env" ]; then
    PYTHON_PATH=$(grep -E "^PYTHON_PATH=" "$SCRIPT_DIR/.env" | cut -d'=' -f2)
    DEPLOY_SSH_HOST=$(grep -E "^DEPLOY_SSH_HOST=" "$SCRIPT_DIR/.env" | cut -d'=' -f2)
    DEPLOY_PLESK_DOMAIN=$(grep -E "^DEPLOY_PLESK_DOMAIN=" "$SCRIPT_DIR/.env" | cut -d'=' -f2)
    DEPLOY_PLESK_REPO=$(grep -E "^DEPLOY_PLESK_REPO=" "$SCRIPT_DIR/.env" | cut -d'=' -f2)
fi

# Determine system Python: .env > alt-python311 > python3
if [ -n "$PYTHON_PATH" ] && [ -x "$PYTHON_PATH" ]; then
    SYSTEM_PYTHON="$PYTHON_PATH"
elif [ -x "/opt/alt/python311/bin/python3" ]; then
    SYSTEM_PYTHON="/opt/alt/python311/bin/python3"
else
    SYSTEM_PYTHON="python3"
fi

# Check if venv exists
if [ ! -f "$PYTHON" ]; then
    echo "Virtual environment not found. Creating with $SYSTEM_PYTHON..."
    "$SYSTEM_PYTHON" -m venv "$VENV_PATH"
    "$PYTHON" -m pip install -q -r "$SCRIPT_DIR/requirements.txt"
    echo "Done."
fi

case "$1" in
    tui|ui|"")
        "$PYTHON" "$SCRIPT_DIR/tui.py"
        ;;
    run)
        "$PYTHON" "$SCRIPT_DIR/cleaner.py"
        ;;
    run-dry|dry)
        "$PYTHON" "$SCRIPT_DIR/cleaner.py" --dry-run
        ;;
    test)
        "$PYTHON" "$SCRIPT_DIR/cleaner.py" --test
        ;;
    install|update)
        "$PYTHON" -m pip install -r "$SCRIPT_DIR/requirements.txt"
        ;;
    deploy)
        if [ -z "$DEPLOY_SSH_HOST" ] || [ -z "$DEPLOY_PLESK_DOMAIN" ] || [ -z "$DEPLOY_PLESK_REPO" ]; then
            echo "Error: DEPLOY_SSH_HOST, DEPLOY_PLESK_DOMAIN and DEPLOY_PLESK_REPO must be set in .env"
            exit 1
        fi
        echo "Deploying to $DEPLOY_SSH_HOST via Plesk Git..."
        echo "  Fetching from remote..."
        ssh "$DEPLOY_SSH_HOST" "plesk ext git --fetch -domain $DEPLOY_PLESK_DOMAIN -name $DEPLOY_PLESK_REPO"
        echo "  Deploying files..."
        ssh "$DEPLOY_SSH_HOST" "plesk ext git --deploy -domain $DEPLOY_PLESK_DOMAIN -name $DEPLOY_PLESK_REPO"
        echo "Done."
        ;;
    *)
        echo "Gmail Cleaner Bot"
        echo ""
        echo "Usage: $0 [command]"
        echo ""
        echo "Commands:"
        echo "  tui, ui     Open the TUI interface (default)"
        echo "  run         Run all enabled rules"
        echo "  dry         Run in dry-run mode (no changes)"
        echo "  test        Test Gmail connection"
        echo "  install     Install/update dependencies"
        echo "  deploy      Deploy to prod via Plesk Git"
        echo ""
        ;;
esac
