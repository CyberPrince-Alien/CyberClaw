@echo off
title CyberClaw Automatic Setup Wizard
color 0B
clear

echo ======================================================================
echo          🌌 CYBERCLAW AUTOMATIC INSTALLER & ENVIRONMENT WIZARD 🌌
echo ======================================================================
echo   Brought to you with ❤️ by Cyber Prince (Sourov)
echo   Optimizing your system, creating stable environments, and setting up...
echo ======================================================================
echo.

:: 1. Check Python Installation
echo [🔎] Checking for Python installation...
where python >nul 2>nul
if %errorlevel% neq 0 (
    color 0C
    echo [❌] ERROR: Python is not installed on your system!
    echo      Please download and install Python 3.12 (Stable) from:
    echo      https://www.python.org/downloads/
    echo      Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b
)

:: 2. Check for UV Package Manager
echo [🔎] Checking for uv package manager...
where uv >nul 2>nul
set HAS_UV=0
if %errorlevel% == 0 (
    set HAS_UV=1
    echo [✨] Found ultra-fast uv package manager!
) else (
    echo [ℹ️] uv is not installed. We will use standard python venv.
)

:: 3. Setup Virtual Environment (Ensuring Stable Python v3.11/v3.12 context)
echo.
echo [⚙️] Step 1: Setting up isolated stable Virtual Environment (.venv)...
if %HAS_UV% == 1 (
    echo [⚙️] Creating environment using uv (forcing stable Python 3.12 compatibility)...
    uv venv --python 3.12
) else (
    echo [⚙️] Creating standard Python virtual environment...
    python -m venv .venv
)

if not exist .venv (
    color 0C
    echo [❌] ERROR: Failed to create Virtual Environment!
    pause
    exit /b
)
echo [✅] Virtual Environment successfully created!

:: 4. Activating Virtual Environment
echo.
echo [⚙️] Step 2: Activating environment...
call .venv\Scripts\activate.bat
if %errorlevel% neq 0 (
    color 0C
    echo [❌] ERROR: Failed to activate virtual environment!
    pause
    exit /b
)
echo [✅] Environment active!

:: 5. Upgrading pip and Installing Dependencies
echo.
echo [⚙️] Step 3: Upgrading package managers and installing CyberClaw...
python -m pip install --upgrade pip

if %HAS_UV% == 1 (
    echo [⚙️] Running ultra-fast uv pip sync...
    uv pip install -e .
) else (
    echo [⚙️] Running standard pip install...
    pip install -e .
)

if %errorlevel% neq 0 (
    color 0C
    echo [❌] ERROR: Installation failed! This is usually due to python versions.
    echo      Please ensure you have a stable Python 3.10 - 3.12 version active.
    pause
    exit /b
)
echo [✅] CyberClaw dependencies successfully installed!

:: 6. Running Onboarding Wizard
echo.
echo [⚙️] Step 4: Running onboarding setup...
cyberclaw onboard
if %errorlevel% neq 0 (
    echo [⚠️] Onboarding returned warning, continuing...
)

:: 7. Running Diagnostics check
echo.
echo [⚙️] Step 5: Running health diagnostics...
cyberclaw doctor

:: 8. Create dynamic one-click startup launchers
echo.
echo [⚙️] Step 6: Generating one-click startup scripts...

:: Create Start Web UI Dashboard script
(
echo @echo off
echo title CyberClaw Web UI Gateway
echo color 0A
echo echo ==============================================================
echo echo          🌌 LAUNCHING CYBERCLAW CONTROL PANEL 🌌
echo echo ==============================================================
echo call .venv\Scripts\activate.bat
echo echo Starting server on http://localhost:8000/ui ...
echo cyberclaw gateway start
echo pause
) > start_dashboard.cmd

:: Create Start CLI Chat script
(
echo @echo off
echo title CyberClaw Interactive CLI Chat
echo color 0B
echo echo ==============================================================
echo echo          🤖 LAUNCHING INTERACTIVE CYBERCLAW CHAT 🤖
echo echo ==============================================================
echo call .venv\Scripts\activate.bat
echo cyberclaw chat
echo pause
) > start_chat.cmd

echo [✅] Created 'start_dashboard.cmd' (One-click Web UI Control Panel launch)
echo [✅] Created 'start_chat.cmd' (One-click terminal CLI Chat launch)

color 0A
echo.
echo ======================================================================
echo 🎉 CONGRATULATIONS! CYBERCLAW SETUP IS 100%% COMPLETE! 🎉
echo ======================================================================
echo  1. Double-click 'start_dashboard.cmd' to launch the space Web UI!
echo  2. Double-click 'start_chat.cmd' to talk directly in the console!
echo ======================================================================
echo.
pause
exit /b
