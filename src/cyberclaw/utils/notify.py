"""Desktop notification utility for CyberClaw."""

import os
import sys
import subprocess
import logging

logger = logging.getLogger(__name__)


def send_os_notification(title: str, message: str) -> None:
    """Sends desktop notifications on Windows/macOS/Linux."""
    # Escape quotes
    title_escaped = title.replace('"', '\\"')
    message_escaped = message.replace('"', '\\"')

    try:
        if sys.platform.startswith("win"):
            # PowerShell Toast Notification using Balloon Tip
            ps_script = f"""
            [void][System.Reflection.Assembly]::LoadWithPartialName("System.Windows.Forms");
            $toast = New-Object System.Windows.Forms.NotifyIcon;
            $toast.Icon = [System.Drawing.SystemIcons]::Information;
            $toast.BalloonTipTitle = "{title_escaped}";
            $toast.BalloonTipText = "{message_escaped}";
            $toast.Visible = $true;
            $toast.ShowBalloonTip(10000);
            """
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_script],
                capture_output=True,
                check=False
            )
        elif sys.platform == "darwin":
            # macOS osascript
            cmd = f'display notification "{message_escaped}" with title "{title_escaped}"'
            subprocess.run(["osascript", "-e", cmd], capture_output=True, check=False)
        else:
            # Linux notify-send
            subprocess.run(["notify-send", title_escaped, message_escaped], capture_output=True, check=False)
    except Exception as e:
        logger.debug(f"Failed to send OS notification: {e}")
