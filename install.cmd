@echo off
title CyberClaw Installer
color 0B

echo ======================================================================
echo          CYBERCLAW AUTOMATIC INSTALLER
echo ======================================================================
echo   Detecting Python and launching cross-platform installer...
echo ======================================================================
echo.

:: Try python commands in order of preference
:: 1. Check AppData local install first (bypasses Windows Store alias)
for /d %%P in ("%LOCALAPPDATA%\Programs\Python\Python3*") do (
    if exist "%%P\python.exe" (
        echo [OK] Found Python at: %%P\python.exe
        "%%P\python.exe" install.py
        if %errorlevel% == 0 goto :done
    )
)

:: 2. Try 'py' launcher (Windows Python Launcher)
where py >nul 2>nul
if %errorlevel% == 0 (
    echo [OK] Found Python via 'py' launcher
    py -3 install.py
    if %errorlevel% == 0 goto :done
)

:: 3. Try 'python' command
where python >nul 2>nul
if %errorlevel% == 0 (
    echo [OK] Found 'python' command
    python install.py
    if %errorlevel% == 0 goto :done
)

:: 4. Try 'python3' command
where python3 >nul 2>nul
if %errorlevel% == 0 (
    echo [OK] Found 'python3' command
    python3 install.py
    if %errorlevel% == 0 goto :done
)

:: Nothing worked
color 0C
echo.
echo [XX] ERROR: Python 3.11+ not found on your system!
echo.
echo     Please download and install Python from:
echo     https://www.python.org/downloads/
echo.
echo     IMPORTANT: Check "Add Python to PATH" during installation!
echo.
echo     Windows Tip: Go to Settings ^> Apps ^> App Execution Aliases
echo     and disable the 'python.exe' and 'python3.exe' Store aliases.
echo.
pause
exit /b 1

:done
echo.
pause
exit /b 0
