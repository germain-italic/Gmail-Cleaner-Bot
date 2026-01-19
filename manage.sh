#!/bin/bash

# Gmail Cleaner Bot - Management Script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PATH="$SCRIPT_DIR/venv"
PYTHON="$VENV_PATH/bin/python"

# Load PYTHON_PATH from .env if exists
if [ -f "$SCRIPT_DIR/.env" ]; then
    PYTHON_PATH=$(grep -E "^PYTHON_PATH=" "$SCRIPT_DIR/.env" | cut -d'=' -f2)
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
        echo ""
        ;;
esac
