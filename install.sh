#!/bin/bash
# CyberClaw Installer — Thin wrapper for install.py

echo "======================================================================"
echo "          CYBERCLAW AUTOMATIC INSTALLER"
echo "======================================================================"
echo "  Detecting Python and launching cross-platform installer..."
echo "======================================================================"
echo

# Try python3 first, then python
if command -v python3 &> /dev/null; then
    python3 install.py
elif command -v python &> /dev/null; then
    python install.py
else
    echo "[XX] ERROR: Python 3.11+ not found!"
    echo
    echo "  Please install Python from: https://www.python.org/downloads/"
    echo "  Or use your package manager:"
    echo "    Ubuntu/Debian: sudo apt install python3"
    echo "    macOS:         brew install python3"
    echo "    Fedora:        sudo dnf install python3"
    exit 1
fi
