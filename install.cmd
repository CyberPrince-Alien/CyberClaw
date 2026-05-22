@echo off
title CyberClaw Installer
color 0B

echo ======================================================================
echo          CYBERCLAW ZERO-TOUCH AUTOMATIC INSTALLER
echo ======================================================================
echo   Checking system environment and bootstrapping Python...
echo ======================================================================
echo.

:: 1. Search for existing Python in standard locations
for /d %%P in ("%LOCALAPPDATA%\Programs\Python\Python3*") do (
    if exist "%%P\python.exe" (
        echo [OK] Found Python at: %%P\python.exe
        set "PYTHON_EXE=%%P\python.exe"
        goto :run_installer
    )
)

where py >nul 2>nul
if %errorlevel% == 0 (
    echo [OK] Found Python via 'py' launcher
    set "PYTHON_EXE=py"
    goto :run_installer
)

where python >nul 2>nul
if %errorlevel% == 0 (
    echo [OK] Found 'python' command
    set "PYTHON_EXE=python"
    goto :run_installer
)

where python3 >nul 2>nul
if %errorlevel% == 0 (
    echo [OK] Found 'python3' command
    set "PYTHON_EXE=python3"
    goto :run_installer
)

:: 2. Bootstrap Python installation if completely missing
echo [!] Python 3.11+ not found. Initializing automatic self-healing installation...

:: Try using Winget first
where winget >nul 2>nul
if %errorlevel% == 0 (
    echo [..] Installing Python 3.12 via winget...
    winget install --id Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements
    if %errorlevel% == 0 goto :refresh_path
)

:: If winget fails or is missing, download installer via PowerShell
echo [..] winget not available or failed. Downloading Python 3.12 installer...
powershell -NoProfile -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.12.3/python-3.12.3-amd64.exe' -OutFile '%TEMP%\python-installer.exe'"
if not exist "%TEMP%\python-installer.exe" (
    echo [XX] ERROR: Failed to download Python installer.
    pause
    exit /b 1
)

echo [..] Running Python installation silently (this may take a minute)...
"%TEMP%\python-installer.exe" /quiet InstallAllUsers=1 PrependPath=1 TargetDir="%ProgramFiles%\Python312"
del "%TEMP%\python-installer.exe" >nul 2>nul

:refresh_path
echo [..] Refreshing environment variables...
:: Read combined User and Machine Path environment variables from Registry
for /f "tokens=*" %%I in ('powershell -NoProfile -Command "[System.Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [System.Environment]::GetEnvironmentVariable('Path', 'User')"') do set "PATH=%%I"

:: Append common Python directories to PATH just in case registry updates are not yet propagated
set "PATH=%PATH%;%LOCALAPPDATA%\Programs\Python\Python312;%LOCALAPPDATA%\Programs\Python\Python312\Scripts;%ProgramFiles%\Python312;%ProgramFiles%\Python312\Scripts"

:: Recheck Python
where python >nul 2>nul
if %errorlevel% == 0 (
    echo [OK] Python successfully installed and configured!
    set "PYTHON_EXE=python"
    goto :run_installer
)

echo [XX] ERROR: Python installation completed but could not be located in PATH.
echo Please restart your terminal or install Python manually from: https://www.python.org/downloads/
pause
exit /b 1

:run_installer
echo [..] Launching cross-platform installer script...
"%PYTHON_EXE%" install.py
if %errorlevel% == 0 goto :done

echo.
echo [XX] Installer script returned an error code.
pause
exit /b 1

:done
echo.
pause
exit /b 0
