#!/usr/bin/env bash
# ISLI AI Unified Bootstrap Installer
# This script prepares the environment and hands off to the interactive CLI.

set -euo pipefail

echo "==> ISLI AI Installer Bootstrap"

# 1. Check for Python
if ! command -v python3 &>/dev/null; then
    echo "Error: python3 is required. Please install it first."
    exit 1
fi

# 2. Setup temporary venv for the management CLI
VENV_DIR=".isli-bootstrap-venv"
if [[ ! -d "$VENV_DIR" ]]; then
    echo "==> Creating bootstrap environment..."
    python3 -m venv "$VENV_DIR"
fi

# 3. Install management dependencies
echo "==> Installing management tools..."
"$VENV_DIR/bin/pip" install -q typer rich psutil python-dotenv

# 4. Hand off to isli.py
echo "==> Launching interactive setup..."
"$VENV_DIR/bin/python3" scripts/isli.py setup

# Cleanup optional (keep it for subsequent isli commands)
# rm -rf "$VENV_DIR"
