#!/usr/bin/env python3
"""
CyberClaw Cross-Platform Installer — Works on Windows, macOS, Linux
====================================================================
Auto-detects Python in common locations, sets up venv, installs
CyberClaw, runs onboard + doctor, and creates launch scripts.

Usage:
    python install.py          # Standard install
    python3 install.py         # Linux/macOS
    py install.py              # Windows py launcher
"""

import os
import sys
import glob
import platform
import subprocess
from pathlib import Path

# ── Colours (ANSI, works in modern terminals) ──────────────────────────
GREEN = "\033[92m"
CYAN = "\033[96m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"

IS_WIN = platform.system() == "Windows"


def banner():
    print(f"""
{CYAN}{'=' * 70}
          CYBERCLAW CROSS-PLATFORM INSTALLER
{'=' * 70}{RESET}
  {DIM}Brought to you with love by Cyber Prince (Sourov){RESET}
  {DIM}Detecting Python, creating environment, installing CyberClaw...{RESET}
{CYAN}{'=' * 70}{RESET}
""")


def ok(msg):
    print(f"  {GREEN}[OK]{RESET} {msg}")


def warn(msg):
    print(f"  {YELLOW}[!!]{RESET} {msg}")


def fail(msg):
    print(f"  {RED}[XX]{RESET} {msg}")


def info(msg):
    print(f"  {CYAN}[..]{RESET} {msg}")


# ── Step 1: Find Python ────────────────────────────────────────────────
def find_python():
    """Auto-detect a working Python >=3.11 binary."""
    candidates = ["python3", "python", "py"]

    # Windows: add common install paths
    if IS_WIN:
        home = Path.home()
        # AppData local install (most common)
        local_programs = home / "AppData" / "Local" / "Programs" / "Python"
        if local_programs.exists():
            for p in sorted(local_programs.iterdir(), reverse=True):
                exe = p / "python.exe"
                if exe.exists():
                    candidates.insert(0, str(exe))

        # System-wide installs
        for drive in ["C:", "D:"]:
            for pattern in [f"{drive}\\Python3*", f"{drive}\\Program Files\\Python*"]:
                for match in glob.glob(pattern):
                    exe = Path(match) / "python.exe"
                    if exe.exists():
                        candidates.append(str(exe))

    for cmd in candidates:
        try:
            result = subprocess.run(
                [cmd, "--version"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                version_str = result.stdout.strip().split()[-1]
                parts = version_str.split(".")
                major, minor = int(parts[0]), int(parts[1])
                if major == 3 and minor >= 11:
                    ok(f"Found Python {version_str} at: {cmd}")
                    return cmd
                else:
                    warn(f"Found Python {version_str} at {cmd} (need >=3.11, skipping)")
        except (FileNotFoundError, subprocess.TimeoutExpired, ValueError, IndexError):
            continue

    return None


# ── Step 2: Check for uv ──────────────────────────────────────────────
def has_uv():
    try:
        subprocess.run(["uv", "--version"], capture_output=True, timeout=5)
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


# ── Step 3: Create venv ───────────────────────────────────────────────
def create_venv(python_cmd, use_uv):
    print(f"\n{CYAN}[**] Step 1: Creating virtual environment (.venv)...{RESET}")
    venv_dir = Path(".venv")

    if venv_dir.exists():
        warn("Existing .venv found - reusing it.")
        return True

    if use_uv:
        info("Using uv for fast environment creation...")
        result = subprocess.run(["uv", "venv", "--python", "3.12"],
                                capture_output=True, text=True)
    else:
        info("Using standard python -m venv...")
        result = subprocess.run([python_cmd, "-m", "venv", ".venv"],
                                capture_output=True, text=True)

    if venv_dir.exists():
        ok("Virtual environment created!")
        return True
    else:
        fail(f"Failed to create .venv! {result.stderr}")
        return False


# ── Step 4: Get venv paths ────────────────────────────────────────────
def get_venv_python():
    if IS_WIN:
        return str(Path(".venv") / "Scripts" / "python.exe")
    return str(Path(".venv") / "bin" / "python")


def get_venv_pip():
    if IS_WIN:
        return str(Path(".venv") / "Scripts" / "pip.exe")
    return str(Path(".venv") / "bin" / "pip")


def get_venv_cyberclaw():
    if IS_WIN:
        return str(Path(".venv") / "Scripts" / "cyberclaw.exe")
    return str(Path(".venv") / "bin" / "cyberclaw")


# ── Step 5: Install CyberClaw ─────────────────────────────────────────
def install_cyberclaw(use_uv):
    print(f"\n{CYAN}[**] Step 2: Installing CyberClaw and dependencies...{RESET}")
    venv_python = get_venv_python()

    # Upgrade pip
    subprocess.run([venv_python, "-m", "pip", "install", "--upgrade", "pip"],
                   capture_output=True, text=True)

    if use_uv:
        info("Running uv pip install (ultra-fast)...")
        result = subprocess.run(["uv", "pip", "install", "-e", "."],
                                capture_output=True, text=True)
    else:
        info("Running pip install (standard)...")
        result = subprocess.run([get_venv_pip(), "install", "-e", "."],
                                capture_output=True, text=True)

    if result.returncode == 0:
        ok("CyberClaw installed successfully!")
        return True
    else:
        fail(f"Installation failed!\n{result.stderr}")
        print(f"\n{DIM}Common fixes:")
        print(f"  - Make sure you have Python 3.11-3.14 (stable)")
        print(f"  - Try: pip install -e .{RESET}")
        return False


# ── Step 6: Run onboard + doctor ──────────────────────────────────────
def run_post_install():
    cyberclaw = get_venv_cyberclaw()

    print(f"\n{CYAN}[**] Step 3: Running onboarding setup...{RESET}")
    subprocess.run([cyberclaw, "onboard"])

    print(f"\n{CYAN}[**] Step 4: Running health diagnostics...{RESET}")
    subprocess.run([cyberclaw, "doctor"])


# ── Step 7: Generate launcher scripts ─────────────────────────────────
def create_launchers():
    print(f"\n{CYAN}[**] Step 5: Generating one-click startup scripts...{RESET}")

    if IS_WIN:
        Path("start_chat.cmd").write_text(
            "@echo off\n"
            "title CyberClaw Interactive Chat\n"
            "color 0B\n"
            "echo ============================================================\n"
            "echo          LAUNCHING CYBERCLAW CHAT\n"
            "echo ============================================================\n"
            "call .venv\\Scripts\\activate.bat\n"
            "cyberclaw chat\n"
            "pause\n",
            encoding="utf-8",
        )
        Path("start_dashboard.cmd").write_text(
            "@echo off\n"
            "title CyberClaw Web Dashboard\n"
            "color 0A\n"
            "echo ============================================================\n"
            "echo          LAUNCHING CYBERCLAW DASHBOARD\n"
            "echo ============================================================\n"
            "call .venv\\Scripts\\activate.bat\n"
            "echo Starting server on http://localhost:8000/ui ...\n"
            "cyberclaw gateway start\n"
            "pause\n",
            encoding="utf-8",
        )
        ok("Created 'start_chat.cmd'     - double-click to chat!")
        ok("Created 'start_dashboard.cmd' - double-click for Web UI!")
    else:
        for name, cmd in [("start_chat.sh", "cyberclaw chat"),
                          ("start_dashboard.sh", "cyberclaw gateway start")]:
            Path(name).write_text(
                f"#!/bin/bash\nsource .venv/bin/activate\n{cmd}\n",
                encoding="utf-8",
            )
            os.chmod(name, 0o755)
        ok("Created 'start_chat.sh'     - run to chat!")
        ok("Created 'start_dashboard.sh' - run for Web UI!")


# ── Main ──────────────────────────────────────────────────────────────
def main():
    # Enable ANSI on Windows
    if IS_WIN:
        os.system("")  # enables ANSI escape codes on Windows 10+

    banner()

    # Step 1: Find Python
    info("Searching for Python installation...")
    python_cmd = find_python()
    if not python_cmd:
        fail("Python 3.11+ not found on your system!")
        print(f"\n  {BOLD}Please install Python from:{RESET}")
        print(f"  {CYAN}https://www.python.org/downloads/{RESET}")
        print(f"\n  {DIM}Make sure to check 'Add Python to PATH' during installation.{RESET}")
        if IS_WIN:
            print(f"\n  {YELLOW}Windows Tip:{RESET} Go to Settings > Apps > App Execution Aliases")
            print(f"  and disable the 'python.exe' and 'python3.exe' Store aliases.")
        sys.exit(1)

    # Step 2: Check for uv
    use_uv = has_uv()
    if use_uv:
        ok("Found ultra-fast uv package manager!")
    else:
        info("uv not found - using standard pip (still works fine).")

    # Step 3: Create venv
    if not create_venv(python_cmd, use_uv):
        sys.exit(1)

    # Step 4: Install
    if not install_cyberclaw(use_uv):
        sys.exit(1)

    # Step 5: Onboard + Doctor
    run_post_install()

    # Step 6: Launchers
    create_launchers()

    # Done!
    chat_script = "start_chat.cmd" if IS_WIN else "./start_chat.sh"
    dash_script = "start_dashboard.cmd" if IS_WIN else "./start_dashboard.sh"
    print(f"""
{GREEN}{'=' * 70}
  CONGRATULATIONS! CYBERCLAW SETUP IS 100% COMPLETE!
{'=' * 70}{RESET}
  1. {BOLD}Chat in terminal:{RESET}  {chat_script}
  2. {BOLD}Web Dashboard:{RESET}     {dash_script}
  3. {BOLD}Switch AI model:{RESET}   cyberclaw select-model
  4. {BOLD}Check updates:{RESET}     cyberclaw update --check
{GREEN}{'=' * 70}{RESET}
""")


if __name__ == "__main__":
    main()
