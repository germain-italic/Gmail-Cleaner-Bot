#!/bin/bash

# Gmail Cleaner Bot - Management Script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PATH="$SCRIPT_DIR/venv"
PYTHON="$VENV_PATH/bin/python"

# Check if venv exists
if [ ! -f "$PYTHON" ]; then
    echo "Virtual environment not found. Creating..."
    python3 -m venv "$VENV_PATH"
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
