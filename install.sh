#!/bin/bash

# CyberClaw Cross-Platform Automatic Installer & Environment Wizard (macOS/Linux)
# Handcrafted by Cyber Prince

# Color codes
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${CYAN}======================================================================${NC}"
echo -e "${CYAN}          🌌 CYBERCLAW AUTOMATIC INSTALLER & ENVIRONMENT WIZARD 🌌${NC}"
echo -e "${CYAN}======================================================================${NC}"
echo -e "  Brought to you with ❤️ by Cyber Prince (Sourov)"
echo -e "  Optimizing your system, creating stable environments, and setting up..."
echo -e "${CYAN}======================================================================${NC}"
echo.

# 1. Check Python Installation
echo -e "${CYAN}[🔎] Checking for Python installation...${NC}"
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}[❌] ERROR: Python3 is not installed on your system!${NC}"
    echo -e "     Please install Python 3.10 - 3.12 (Stable) on your machine."
    exit 1
fi

# 2. Check for UV Package Manager
HAS_UV=0
if command -v uv &> /dev/null; then
    HAS_UV=1
    echo -e "${GREEN}[✨] Found ultra-fast uv package manager!${NC}"
else
    echo -e "${YELLOW}[ℹ️] uv is not installed. We will use standard python venv.${NC}"
fi

# 3. Setup Virtual Environment
echo.
echo -e "${CYAN}[⚙️] Step 1: Setting up isolated stable Virtual Environment (.venv)...${NC}"
if [ $HAS_UV -eq 1 ]; then
    echo -e "${CYAN}[⚙️] Creating environment using uv (forcing stable Python 3.12 compatibility)...${NC}"
    uv venv --python 3.12
else
    echo -e "${CYAN}[⚙️] Creating standard Python virtual environment...${NC}"
    python3 -m venv .venv
fi

if [ ! -d ".venv" ]; then
    echo -e "${RED}[❌] ERROR: Failed to create Virtual Environment!${NC}"
    exit 1
fi
echo -e "${GREEN}[✅] Virtual Environment successfully created!${NC}"

# 4. Activating Virtual Environment
echo.
echo -e "${CYAN}[⚙️] Step 2: Activating environment...${NC}"
source .venv/bin/activate
echo -e "${GREEN}[✅] Environment active!${NC}"

# 5. Upgrading pip and Installing Dependencies
echo.
echo -e "${CYAN}[⚙️] Step 3: Upgrading package managers and installing CyberClaw...${NC}"
python3 -m pip install --upgrade pip

if [ $HAS_UV -eq 1 ]; then
    echo -e "${CYAN}[⚙️] Running ultra-fast uv pip sync...${NC}"
    uv pip install -e .
else
    echo -e "${CYAN}[⚙️] Running standard pip install...${NC}"
    pip install -e .
fi

if [ $? -ne 0 ]; then
    echo -e "${RED}[❌] ERROR: Installation failed! This is usually due to python versions.${NC}"
    echo -e "     Please ensure you have a stable Python 3.10 - 3.12 version active."
    exit 1
fi
echo -e "${GREEN}[✅] CyberClaw dependencies successfully installed!${NC}"

# 6. Running Onboarding Wizard
echo.
echo -e "${CYAN}[⚙️] Step 4: Running onboarding setup...${NC}"
cyberclaw onboard

# 7. Running Diagnostics check
echo.
echo -e "${CYAN}[⚙️] Step 5: Running health diagnostics...${NC}"
cyberclaw doctor

# 8. Create one-click startup launchers
echo.
echo -e "${CYAN}[⚙️] Step 6: Generating startup scripts...${NC}"

# Create Start Web UI Dashboard script
cat << 'EOF' > start_dashboard.sh
#!/bin/bash
source .venv/bin/activate
echo "Starting CyberClaw Web UI on http://localhost:8000/ui ..."
cyberclaw gateway start
EOF
chmod +x start_dashboard.sh

# Create Start CLI Chat script
cat << 'EOF' > start_chat.sh
#!/bin/bash
source .venv/bin/activate
cyberclaw chat
EOF
chmod +x start_chat.sh

echo -e "${GREEN}[✅] Created 'start_dashboard.sh' (One-click Web UI Control Panel launch)${NC}"
echo -e "${GREEN}[✅] Created 'start_chat.sh' (One-click terminal CLI Chat launch)${NC}"

echo.
echo -e "${GREEN}======================================================================${NC}"
echo -e "🎉 CONGRATULATIONS! CYBERCLAW SETUP IS 100% COMPLETE! 🎉"
echo -e "${GREEN}======================================================================${NC}"
echo -e "  1. Run './start_dashboard.sh' to launch the space Web UI!"
echo -e "  2. Run './start_chat.sh' to talk directly in the console!"
echo -e "${GREEN}======================================================================${NC}"
echo.
exit 0
