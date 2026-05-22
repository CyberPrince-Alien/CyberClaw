#!/bin/bash
# CyberClaw Unix-based Bootstrap Installer
# Supports macOS, Linux, Android/Termux, iOS/iSH

echo "======================================================================"
echo "          CYBERCLAW ZERO-TOUCH AUTOMATIC INSTALLER"
echo "======================================================================"
echo "  Checking system environment and bootstrapping Python..."
echo "======================================================================"
echo

# 1. Detect environment / OS
OS_TYPE="unknown"
if [[ "$OSTYPE" == "darwin"* ]]; then
    OS_TYPE="macos"
elif [[ -d "/data/data/com.termux" ]] || [ -n "$TERMUX_VERSION" ]; then
    OS_TYPE="termux"
elif [ -f /etc/alpine-release ] || grep -q "Alpine" /etc/os-release 2>/dev/null; then
    OS_TYPE="ish" # iSH or Alpine Linux
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    OS_TYPE="linux"
fi

echo "[..] Detected Environment: $OS_TYPE"

# 2. Check if python3 is available
PYTHON_CMD=""
if command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
elif command -v python &> /dev/null; then
    PYTHON_CMD="python"
fi

if [ -n "$PYTHON_CMD" ]; then
    # Verify Python version >= 3.11
    PY_VER=$($PYTHON_CMD -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    PY_MAJOR=$(echo "$PY_VER" | cut -d. -f1)
    PY_MINOR=$(echo "$PY_VER" | cut -d. -f2)
    if [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -ge 11 ]; then
        echo "[OK] Found compatible Python $PY_VER"
    else
        echo "[!] Python $PY_VER found but version is < 3.11."
        PYTHON_CMD=""
    fi
fi

# 3. Bootstrap python if missing
if [ -z "$PYTHON_CMD" ]; then
    echo "[!] Python 3.11+ not found. Attempting self-healing install..."
    
    if [ "$OS_TYPE" == "macos" ]; then
        if ! command -v brew &> /dev/null; then
            echo "[..] Homebrew not found. Installing Homebrew..."
            /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
            eval "$(/opt/homebrew/bin/brew shellenv)" 2>/dev/null || eval "$(/usr/local/bin/brew shellenv)" 2>/dev/null
        fi
        echo "[..] Installing Python via Homebrew..."
        brew install python
        PYTHON_CMD="python3"
        
    elif [ "$OS_TYPE" == "termux" ]; then
        echo "[..] Installing Python via Termux pkg manager..."
        pkg update -y && pkg install -y python git nodejs-lts
        PYTHON_CMD="python"
        
    elif [ "$OS_TYPE" == "ish" ]; then
        echo "[..] Installing Python via Alpine apk manager..."
        apk update && apk add python3 py3-pip git nodejs npm build-base python3-dev
        PYTHON_CMD="python3"
        
    elif [ "$OS_TYPE" == "linux" ]; then
        if command -v apt-get &> /dev/null; then
            echo "[..] Installing Python via apt..."
            sudo apt-get update && sudo apt-get install -y python3 python3-pip python3-venv git nodejs npm
        elif command -v dnf &> /dev/null; then
            echo "[..] Installing Python via dnf..."
            sudo dnf install -y python3 git nodejs
        elif command -v pacman &> /dev/null; then
            echo "[..] Installing Python via pacman..."
            sudo pacman -S --noconfirm python git nodejs npm
        else
            echo "[XX] ERROR: Could not identify Linux package manager. Please install Python 3.11+ manually."
            exit 1
        fi
        PYTHON_CMD="python3"
    else
        echo "[XX] ERROR: Unsupported platform. Please install Python 3.11+ manually."
        exit 1
    fi
fi

# Double check Python installation
if ! command -v $PYTHON_CMD &> /dev/null; then
    echo "[XX] ERROR: Failed to bootstrap Python. Please install Python 3.11+ manually."
    exit 1
fi

echo "[..] Launching cross-platform installer script..."
$PYTHON_CMD install.py
exit $?
