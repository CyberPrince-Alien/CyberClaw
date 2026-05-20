"""Windows service wrapper using NSSM or win32serviceutil.

Provides install/uninstall/status commands for running CyberClaw as a
Windows background service that starts on boot.
"""

import logging
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


class WindowsServiceManager:
    """Manages CyberClaw as a Windows service."""

    SERVICE_NAME = "CyberClawGateway"
    DISPLAY_NAME = "CyberClaw AI Assistant Gateway"

    def __init__(self, workspace: Path):
        self.workspace = workspace

    def install(self) -> str:
        """Install CyberClaw as a Windows service."""
        # Try NSSM first (most reliable)
        nssm = self._find_nssm()
        if nssm:
            return self._install_nssm(nssm)

        # Fall back to schtasks (built-in)
        return self._install_schtasks()

    def uninstall(self) -> str:
        """Remove the CyberClaw service."""
        nssm = self._find_nssm()
        if nssm:
            return self._uninstall_nssm(nssm)
        return self._uninstall_schtasks()

    def status(self) -> str:
        """Check service status."""
        nssm = self._find_nssm()
        if nssm:
            try:
                result = subprocess.run(
                    [nssm, "status", self.SERVICE_NAME],
                    capture_output=True, text=True,
                )
                return result.stdout.strip() or "Not installed"
            except FileNotFoundError:
                pass

        # Check schtasks
        try:
            result = subprocess.run(
                ["schtasks", "/Query", "/TN", self.SERVICE_NAME],
                capture_output=True, text=True,
            )
            if result.returncode == 0:
                return "Installed (scheduled task)"
            return "Not installed"
        except FileNotFoundError:
            return "Cannot check status"

    def _find_nssm(self) -> str | None:
        """Find NSSM executable."""
        for path in ["nssm", "nssm.exe", r"C:\nssm\nssm.exe"]:
            try:
                subprocess.run([path, "version"], capture_output=True)
                return path
            except FileNotFoundError:
                continue
        return None

    def _install_nssm(self, nssm: str) -> str:
        """Install using NSSM."""
        uv_path = self._find_uv()
        if not uv_path:
            return "Error: uv not found in PATH"

        # Install service
        subprocess.run(
            [nssm, "install", self.SERVICE_NAME, uv_path, "run", "cyberclaw", "server"],
            check=True,
        )

        # Set working directory
        subprocess.run(
            [nssm, "set", self.SERVICE_NAME, "AppDirectory", str(self.workspace.parent)],
            check=True,
        )

        # Set display name
        subprocess.run(
            [nssm, "set", self.SERVICE_NAME, "DisplayName", self.DISPLAY_NAME],
            check=True,
        )

        # Set description
        subprocess.run(
            [nssm, "set", self.SERVICE_NAME, "Description",
             "CyberClaw personal AI assistant gateway service"],
            check=True,
        )

        # Auto-start
        subprocess.run(
            [nssm, "set", self.SERVICE_NAME, "Start", "SERVICE_AUTO_START"],
            check=True,
        )

        # Start the service
        subprocess.run([nssm, "start", self.SERVICE_NAME])

        return f"Service '{self.SERVICE_NAME}' installed and started via NSSM"

    def _uninstall_nssm(self, nssm: str) -> str:
        subprocess.run([nssm, "stop", self.SERVICE_NAME], capture_output=True)
        subprocess.run([nssm, "remove", self.SERVICE_NAME, "confirm"], check=True)
        return f"Service '{self.SERVICE_NAME}' removed"

    def _install_schtasks(self) -> str:
        """Install using Windows Task Scheduler (no admin required)."""
        uv_path = self._find_uv()
        if not uv_path:
            return "Error: uv not found in PATH"

        cmd = f'"{uv_path}" run cyberclaw server'
        work_dir = str(self.workspace.parent)

        subprocess.run([
            "schtasks", "/Create",
            "/TN", self.SERVICE_NAME,
            "/TR", cmd,
            "/SC", "ONLOGON",
            "/RL", "HIGHEST",
            "/F",
        ], check=True)

        return f"Scheduled task '{self.SERVICE_NAME}' created (runs on logon)"

    def _uninstall_schtasks(self) -> str:
        subprocess.run([
            "schtasks", "/Delete", "/TN", self.SERVICE_NAME, "/F",
        ], check=True)
        return f"Scheduled task '{self.SERVICE_NAME}' removed"

    @staticmethod
    def _find_uv() -> str | None:
        """Find uv executable."""
        import shutil
        return shutil.which("uv")
