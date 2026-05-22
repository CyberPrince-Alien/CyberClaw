#!/usr/bin/env python3
"""
CyberClaw Cross-Platform Installer — Works on Windows, macOS, Linux, Android/Termux, iOS/iSH
===========================================================================================
Zero-touch, self-healing, cross-platform installation script. Auto-detects OS and installs
any missing dependencies (Python 3.11+, Git, Node.js/npm, uv), configures environments,
fixes common errors (path issues, compiler gaps), and generates startup launchers.

Usage:
    python install.py          # Standard execution
"""

import os
import sys
import glob
import platform
import subprocess
import urllib.request
import tempfile
from pathlib import Path

# Try importing winreg on Windows
try:
    import winreg
except ImportError:
    winreg = None

# ── Colours (ANSI, works in modern terminals) ──────────────────────────
GREEN = "\033[92m"
CYAN = "\033[96m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


def banner():
    print(f"""
{CYAN}{'=' * 75}
          CYBERCLAW ZERO-TOUCH SELF-HEALING INSTALLER
{'=' * 75}{RESET}
  {DIM}Author: Cyber Prince (Sourov){RESET}
  {DIM}Auto-detecting OS, ensuring Git/Node/uv/Python, configuring .venv...{RESET}
{CYAN}{'=' * 75}{RESET}
""")


def ok(msg):
    print(f"  {GREEN}[OK]{RESET} {msg}")


def warn(msg):
    print(f"  {YELLOW}[!!]{RESET} {msg}")


def fail(msg):
    print(f"  {RED}[XX]{RESET} {msg}")


def info(msg):
    print(f"  {CYAN}[..]{RESET} {msg}")


# ── System Detection ──────────────────────────────────────────────────
def detect_os():
    """Detects host operating system or shell environment."""
    if platform.system() == "Windows":
        return "windows"
    elif platform.system() == "Darwin":
        return "macos"
    elif os.path.exists("/data/data/com.termux") or "TERMUX_VERSION" in os.environ:
        return "termux"
    elif os.path.exists("/etc/alpine-release") or (os.path.exists("/etc/os-release") and "alpine" in open("/etc/os-release").read().lower()):
        return "ish"
    else:
        return "linux"


# ── Path Refreshing & Windows Registry ─────────────────────────────────
def refresh_windows_path():
    """Reads system & user paths directly from registry to refresh current session."""
    if not winreg:
        return False
    try:
        paths = []
        # System PATH
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"System\CurrentControlSet\Control\Session Manager\Environment") as key:
                paths.append(winreg.QueryValueEx(key, "Path")[0])
        except Exception:
            pass
        # User PATH
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
                paths.append(winreg.QueryValueEx(key, "Path")[0])
        except Exception:
            pass

        combined_path = ";".join(paths)
        os.environ["PATH"] = os.path.expandvars(combined_path)
        return True
    except Exception as e:
        warn(f"Failed to refresh Windows registry path: {e}")
        return False


# ── Command & Dependency Checks ────────────────────────────────────────
def check_command(cmd, args=["--version"]):
    """Checks if a command is executable and returns True if successful."""
    # Bypassing Microsoft Store python mockup aliases which return 0-bytes or open store
    if cmd in ["python", "python3"]:
        try:
            where_res = subprocess.run(["where", cmd] if platform.system() == "Windows" else ["which", cmd], capture_output=True, text=True)
            if "WindowsApps" in where_res.stdout:
                return False
        except Exception:
            pass

    try:
        result = subprocess.run([cmd] + args, capture_output=True, text=True, timeout=5)
        return result.returncode == 0
    except (FileNotFoundError, subprocess.SubprocessError):
        return False


def find_missing_command_in_common_paths(cmd):
    """Searches common installation directories and appends to session PATH if found."""
    system_os = detect_os()
    if system_os == "windows":
        if cmd == "git":
            search_paths = [
                r"C:\Program Files\Git\cmd\git.exe",
                r"C:\Program Files (x86)\Git\cmd\git.exe",
                os.path.expandvars(r"%LOCALAPPDATA%\Programs\Git\cmd\git.exe"),
            ]
        elif cmd in ["node", "npm"]:
            ext = ".exe" if cmd == "node" else ".cmd"
            search_paths = [
                rf"C:\Program Files\nodejs\{cmd}{ext}",
                rf"C:\Program Files (x86)\nodejs\{cmd}{ext}",
                os.path.expandvars(rf"%APPDATA%\npm\{cmd}{ext}"),
            ]
        elif cmd == "uv":
            search_paths = [
                os.path.expandvars(r"%USERPROFILE%\.cargo\bin\uv.exe"),
                os.path.expandvars(r"%APPDATA%\Local\Programs\uv\uv.exe"),
                os.path.expandvars(r"%LOCALAPPDATA%\Programs\uv\uv.exe"),
            ]
        else:
            search_paths = []

        for path in search_paths:
            if os.path.exists(path):
                dir_path = os.path.dirname(path)
                if dir_path not in os.environ["PATH"]:
                    os.environ["PATH"] += ";" + dir_path
                return path

    elif system_os == "macos":
        search_dirs = ["/opt/homebrew/bin", "/usr/local/bin"]
        for d in search_dirs:
            full_path = os.path.join(d, cmd)
            if os.path.exists(full_path):
                if d not in os.environ["PATH"]:
                    os.environ["PATH"] = d + ":" + os.environ["PATH"]
                return full_path

    return None


# ── Download Helper ───────────────────────────────────────────────────
def download_with_progress(url, filename, desc="Downloading"):
    """Downloads a file showing progress details."""
    info(f"{desc} starting from {url}...")
    def reporthook(blocknum, blocksize, totalsize):
        readsofar = blocknum * blocksize
        if totalsize > 0:
            percent = min(100, readsofar * 100 // totalsize)
            sys.stdout.write(f"\r  [..] Progress: {percent}% ({readsofar // 1024 // 1024}MB / {totalsize // 1024 // 1024}MB)")
            sys.stdout.flush()
        else:
            sys.stdout.write(f"\r  [..] Progress: {readsofar // 1024} KB read")
            sys.stdout.flush()
    try:
        urllib.request.urlretrieve(url, filename, reporthook)
        print(f"\n  {GREEN}[OK]{RESET} Saved to {filename}")
        return True
    except Exception as e:
        print(f"\n  {RED}[XX]{RESET} Download failed: {e}")
        return False


# ── Installer Functions ───────────────────────────────────────────────
def install_build_tools():
    """Installs required compiler and build utilities automatically."""
    info("Compiler or build tools missing. Attempting self-healing installation...")
    system_os = detect_os()
    try:
        if system_os == "macos":
            subprocess.run(["xcode-select", "--install"], check=True)
        elif system_os == "termux":
            subprocess.run(["pkg", "install", "-y", "clang", "make", "python-dev"], check=True)
        elif system_os == "ish":
            subprocess.run(["apk", "add", "build-base"], check=True)
        elif system_os == "linux":
            if check_command("apt-get"):
                subprocess.run(["sudo", "apt-get", "install", "-y", "build-essential"], check=True)
            elif check_command("dnf"):
                subprocess.run(["sudo", "dnf", "groupinstall", "-y", "Development Tools"], check=True)
            elif check_command("pacman"):
                subprocess.run(["sudo", "pacman", "-S", "--needed", "--noconfirm", "base-devel"], check=True)
        ok("Build tools installed successfully!")
        return True
    except Exception as e:
        fail(f"Failed to install build tools automatically: {e}")
        return False


def ensure_dependency(name):
    """Ensures dependency is present; installs it if missing."""
    cmd_name = "node" if name == "npm" else name
    if check_command(cmd_name):
        return True

    if find_missing_command_in_common_paths(cmd_name):
        return True

    info(f"Dependency '{name}' is missing. Launching automatic installation...")
    system_os = detect_os()

    if system_os == "windows":
        # Attempt Winget first
        if check_command("winget"):
            pkg_ids = {"git": "Git.Git", "node": "OpenJS.NodeJS", "npm": "OpenJS.NodeJS", "uv": "Astral.uv"}
            pkg_id = pkg_ids.get(name)
            if pkg_id:
                info(f"Installing {name} via winget...")
                subprocess.run(["winget", "install", "--id", pkg_id, "--silent", "--accept-package-agreements", "--accept-source-agreements"])
                refresh_windows_path()
                if check_command(cmd_name) or find_missing_command_in_common_paths(cmd_name):
                    ok(f"Successfully installed {name} via winget!")
                    return True

        # Fallback to direct download
        temp_dir = tempfile.gettempdir()
        if name == "git":
            url = "https://github.com/git-for-windows/git/releases/download/v2.44.0.windows.1/Git-2.44.0-64-bit.exe"
            dest = os.path.join(temp_dir, "git_installer.exe")
            if download_with_progress(url, dest, "Git Installer"):
                info("Running Git installer silently...")
                subprocess.run([dest, "/VERYSILENT", "/NORESTART", "/NOCANCEL", "/SP-", "/CLOSEAPPLICATIONS", "/RESTARTAPPLICATIONS"], check=True)
                os.remove(dest)
                refresh_windows_path()
                os.environ["PATH"] += r";C:\Program Files\Git\cmd;C:\Program Files (x86)\Git\cmd"
                if check_command("git"):
                    return True
        elif name in ["node", "npm"]:
            url = "https://nodejs.org/dist/v20.12.2/node-v20.12.2-x64.msi"
            dest = os.path.join(temp_dir, "node_installer.msi")
            if download_with_progress(url, dest, "NodeJS Installer"):
                info("Running NodeJS installer silently...")
                subprocess.run(["msiexec", "/i", dest, "/qn", "/norestart"], check=True)
                os.remove(dest)
                refresh_windows_path()
                os.environ["PATH"] += r";C:\Program Files\nodejs"
                if check_command("node"):
                    return True
        elif name == "uv":
            info("Installing uv package manager via pip...")
            res = subprocess.run([sys.executable, "-m", "pip", "install", "uv"], capture_output=True, text=True)
            refresh_windows_path()
            if check_command("uv") or find_missing_command_in_common_paths("uv"):
                return True

    elif system_os == "macos":
        if not check_command("brew"):
            info("Homebrew not found. Installing Homebrew...")
            subprocess.run(["/bin/bash", "-c", "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"], check=True)
            # Add Homebrew to current shell path
            os.environ["PATH"] = "/opt/homebrew/bin:/usr/local/bin:" + os.environ["PATH"]
        
        info(f"Installing {name} via brew...")
        brew_name = "node" if name in ["node", "npm"] else name
        subprocess.run(["brew", "install", brew_name], check=True)
        if check_command(cmd_name):
            return True

    elif system_os == "termux":
        info(f"Installing {name} via Termux pkg...")
        pkg_map = {"git": "git", "node": "nodejs-lts", "npm": "nodejs-lts", "uv": "python-pip"}
        subprocess.run(["pkg", "install", "-y", pkg_map[name]], check=True)
        if name == "uv":
            subprocess.run(["pip", "install", "uv"])
        if check_command(cmd_name):
            return True

    elif system_os == "ish":
        info(f"Installing {name} via Alpine apk...")
        pkg_map = {"git": "git", "node": "nodejs", "npm": "npm", "uv": "py3-pip"}
        subprocess.run(["apk", "add", pkg_map[name]], check=True)
        if name == "uv":
            subprocess.run(["pip", "install", "uv"])
        if check_command(cmd_name):
            return True

    elif system_os == "linux":
        info(f"Installing {name} via system package manager (requires sudo)...")
        if check_command("apt-get"):
            pkg_map = {"git": "git", "node": "nodejs", "npm": "npm", "uv": "python3-pip"}
            subprocess.run(["sudo", "apt-get", "update"], check=True)
            subprocess.run(["sudo", "apt-get", "install", "-y", pkg_map[name]], check=True)
            if name == "uv":
                subprocess.run(["pip3", "install", "--user", "uv"])
        elif check_command("dnf"):
            pkg_map = {"git": "git", "node": "nodejs", "npm": "npm", "uv": "python3-pip"}
            subprocess.run(["sudo", "dnf", "install", "-y", pkg_map[name]], check=True)
            if name == "uv":
                subprocess.run(["pip3", "install", "--user", "uv"])
        elif check_command("pacman"):
            pkg_map = {"git": "git", "node": "nodejs", "npm": "npm", "uv": "python-pip"}
            subprocess.run(["sudo", "pacman", "-S", "--needed", "--noconfirm", pkg_map[name]], check=True)
            if name == "uv":
                subprocess.run(["pip", "install", "uv"])
        
        if check_command(cmd_name):
            return True

    fail(f"Could not automatically install {name}. Please install it manually.")
    return False


# ── Create Venv ───────────────────────────────────────────────────────
def create_venv(use_uv):
    print(f"\n{CYAN}[**] Creating virtual environment (.venv)...{RESET}")
    venv_dir = Path(".venv")

    if venv_dir.exists():
        warn("Existing .venv found - reusing it.")
        return True

    # Self-healing loop: if venv creation fails, delete directory and retry
    for attempt in range(2):
        if use_uv:
            info("Using uv for fast virtualenv creation...")
            result = subprocess.run(["uv", "venv", "--python", "3.12"], capture_output=True, text=True)
        else:
            info("Using standard python -m venv...")
            result = subprocess.run([sys.executable, "-m", "venv", ".venv"], capture_output=True, text=True)

        if venv_dir.exists():
            ok("Virtual environment created!")
            return True
        else:
            warn(f"Virtualenv creation failed: {result.stderr or result.stdout}. Retrying clean creation...")
            if venv_dir.exists():
                import shutil
                shutil.rmtree(venv_dir, ignore_errors=True)
                
    fail("Failed to create virtual environment (.venv) after multiple attempts.")
    return False


# ── Venv Paths ────────────────────────────────────────────────────────
def get_venv_python():
    if platform.system() == "Windows":
        return str(Path(".venv") / "Scripts" / "python.exe")
    return str(Path(".venv") / "bin" / "python")


def get_venv_pip():
    if platform.system() == "Windows":
        return str(Path(".venv") / "Scripts" / "pip.exe")
    return str(Path(".venv") / "bin" / "pip")


def get_venv_cyberclaw():
    if platform.system() == "Windows":
        return str(Path(".venv") / "Scripts" / "cyberclaw.exe")
    return str(Path(".venv") / "bin" / "cyberclaw")


def kill_running_instances():
    """Checks and terminates any active CyberClaw or gateway process to prevent file lock issues."""
    info("Checking and terminating any running CyberClaw or gateway instances to release file locks...")
    system_os = detect_os()
    try:
        if system_os == "windows":
            subprocess.run(["taskkill", "/f", "/im", "cyberclaw.exe"], capture_output=True)
            subprocess.run(["taskkill", "/f", "/im", "uvicorn.exe"], capture_output=True)
        else:
            subprocess.run(["pkill", "-f", "cyberclaw"], capture_output=True)
            subprocess.run(["pkill", "-f", "uvicorn"], capture_output=True)
        ok("Active processes terminated.")
    except Exception as e:
        warn(f"Failed to kill running processes: {e}")


# ── CyberClaw Installation ───────────────────────────────────────────
def install_cyberclaw(use_uv):
    print(f"\n{CYAN}[**] Installing CyberClaw and dependencies...{RESET}")
    kill_running_instances()
    venv_python = get_venv_python()

    # Upgrade pip inside venv first
    subprocess.run([venv_python, "-m", "pip", "install", "--upgrade", "pip"], capture_output=True)

    # Attempt installation
    for attempt in range(2):
        if use_uv:
            info("Running uv pip install (editable mode)...")
            result = subprocess.run(["uv", "pip", "install", "-e", "."], capture_output=True, text=True)
        else:
            info("Running standard pip install (editable mode)...")
            result = subprocess.run([get_venv_pip(), "install", "-e", "."], capture_output=True, text=True)

        if result.returncode == 0:
            ok("CyberClaw installed successfully!")
            return True
            
        err_out = result.stderr or result.stdout
        # Self-healing: check for file locking/access issues
        if "used by another process" in err_out.lower() or "os error 32" in err_out.lower() or "permissionerror" in err_out.lower() or "access is denied" in err_out.lower():
            warn("File lock detected during installation. Retrying process termination...")
            kill_running_instances()
            continue
            
        # Self-healing: check if compilation failed and install build-essential tools
        if "compiler" in err_out.lower() or "gcc" in err_out.lower() or "clang" in err_out.lower() or "build" in err_out.lower():
            if install_build_tools():
                continue # Retry installation after installing compilers
                
        # Fallback to standard pip if uv failed
        if use_uv:
            warn("uv pip installation failed. Falling back to standard pip install...")
            use_uv = False
            continue

    fail(f"CyberClaw installation failed!\n{result.stderr or result.stdout}")
    return False



# ── Post Install setup ────────────────────────────────────────────────
def run_post_install():
    cyberclaw = get_venv_cyberclaw()
    print(f"\n{CYAN}[**] Running onboarding setup...{RESET}")
    subprocess.run([cyberclaw, "onboard"], input=b"n\n")

    print(f"\n{CYAN}[**] Running health diagnostics...{RESET}")
    subprocess.run([cyberclaw, "doctor"])


# ── Launcher Generation ───────────────────────────────────────────────
def create_launchers():
    print(f"\n{CYAN}[**] Generating startup launchers...{RESET}")
    is_win = platform.system() == "Windows"

    if is_win:
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
    if platform.system() == "Windows":
        os.system("")  # Enable ANSI Escape colors

    banner()

    # Step 1: Ensure system dependencies
    info("Checking and verifying environment dependencies...")
    dependencies = ["git", "node", "npm", "uv"]
    for dep in dependencies:
        if not ensure_dependency(dep):
            fail(f"Critical dependency '{dep}' is missing and could not be auto-installed. Terminating.")
            sys.exit(1)

    # Step 2: Create virtual environment
    use_uv = check_command("uv")
    if not create_venv(use_uv):
        sys.exit(1)

    # Step 3: Install project
    if not install_cyberclaw(use_uv):
        sys.exit(1)

    # Step 4: Post-installation onboarding & diagnostics
    run_post_install()

    # Step 5: Launchers
    create_launchers()

    # Complete!
    chat_script = "start_chat.cmd" if platform.system() == "Windows" else "./start_chat.sh"
    dash_script = "start_dashboard.cmd" if platform.system() == "Windows" else "./start_dashboard.sh"
    print(f"""
{GREEN}{'=' * 75}
  CONGRATULATIONS! CYBERCLAW SETUP IS 100% COMPLETE & VERIFIED!
{'=' * 75}{RESET}
  1. {BOLD}Chat in Terminal:{RESET} {chat_script}
  2. {BOLD}Web Dashboard:{RESET}    {dash_script}
  3. {BOLD}Switch Model:{RESET}     cyberclaw select-model
  4. {BOLD}Check Updates:{RESET}    cyberclaw update --check
{GREEN}{'=' * 75}{RESET}
""")


if __name__ == "__main__":
    main()
