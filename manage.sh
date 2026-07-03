#!/bin/bash

# Gmail Cleaner Bot - Management Script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PATH="$SCRIPT_DIR/venv"
PYTHON="$VENV_PATH/bin/python"

# tui.py uses PEP 604 unions ("X | None") evaluated at runtime → needs Python >= 3.10.
# Falling back to an older interpreter builds a venv where the cron (cleaner.py) works
# but the TUI crashes with "TypeError: unsupported operand type(s) for |". So we require
# 3.10+ and fail loudly rather than silently building a half-working environment.
MIN_PY_MINOR=10

# Load variables from .env if exists
if [ -f "$SCRIPT_DIR/.env" ]; then
    PYTHON_PATH=$(grep -E "^PYTHON_PATH=" "$SCRIPT_DIR/.env" | cut -d'=' -f2)
    DEPLOY_SSH_HOST=$(grep -E "^DEPLOY_SSH_HOST=" "$SCRIPT_DIR/.env" | cut -d'=' -f2)
    DEPLOY_PLESK_DOMAIN=$(grep -E "^DEPLOY_PLESK_DOMAIN=" "$SCRIPT_DIR/.env" | cut -d'=' -f2)
    DEPLOY_PLESK_REPO=$(grep -E "^DEPLOY_PLESK_REPO=" "$SCRIPT_DIR/.env" | cut -d'=' -f2)
fi

# 0 if "$1" is a runnable Python interpreter with version >= 3.MIN_PY_MINOR
py_ok() {
    [ -n "$1" ] || return 1
    "$1" -c "import sys; sys.exit(0 if sys.version_info >= (3, $MIN_PY_MINOR) else 1)" >/dev/null 2>&1
}

# Pick a suitable system Python: .env PYTHON_PATH > alt-python311 > python3.11 > python3.10 > python3
SYSTEM_PYTHON=""
for _cand in "$PYTHON_PATH" /opt/alt/python311/bin/python3 python3.11 python3.10 python3; do
    if py_ok "$_cand"; then SYSTEM_PYTHON="$_cand"; break; fi
done

# (Re)build the venv when it is missing, broken (dead symlink), or too old (< 3.10).
# This self-heals the classic breakage: the interpreter the venv was built on gets
# removed/upgraded, leaving venv/bin/python dangling. `python -m venv` over an existing
# dir does NOT replace a dangling symlink, so we wipe and recreate from scratch.
ensure_venv() {
    if py_ok "$PYTHON"; then
        return 0
    fi
    if [ -z "$SYSTEM_PYTHON" ]; then
        echo "ERROR: no Python >= 3.$MIN_PY_MINOR found (required for the TUI)." >&2
        echo "       Checked: \$PYTHON_PATH, /opt/alt/python311, python3.11, python3.10, python3." >&2
        echo "       On this Plesk box: apt-get install -y alt-python311" >&2
        exit 1
    fi
    echo "Rebuilding virtual environment with $SYSTEM_PYTHON ($("$SYSTEM_PYTHON" --version 2>&1))..."
    rm -rf "$VENV_PATH"
    "$SYSTEM_PYTHON" -m venv "$VENV_PATH" || { echo "ERROR: venv creation failed." >&2; exit 1; }
    "$PYTHON" -m pip install --quiet --upgrade pip
    "$PYTHON" -m pip install --quiet -r "$SCRIPT_DIR/requirements.txt" \
        || { echo "ERROR: pip install failed." >&2; exit 1; }
    echo "Done."
}

case "$1" in
    tui|ui|"")
        ensure_venv
        "$PYTHON" "$SCRIPT_DIR/tui.py"
        ;;
    run)
        ensure_venv
        "$PYTHON" "$SCRIPT_DIR/cleaner.py"
        ;;
    run-dry|dry)
        ensure_venv
        "$PYTHON" "$SCRIPT_DIR/cleaner.py" --dry-run
        ;;
    test)
        ensure_venv
        "$PYTHON" "$SCRIPT_DIR/cleaner.py" --test
        ;;
    install|update)
        ensure_venv
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
