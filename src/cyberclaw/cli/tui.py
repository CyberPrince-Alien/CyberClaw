"""Interactive TUI dashboard using Rich console — 3-pane side-by-side layout.

Layout:
  ┌─────────────┬──────────────────┬──────────────┐
  │  WORKSPACE  │   LIVE CHAT      │  TELEMETRY   │
  │  EXPLORER   │   CONSOLE        │  DASHBOARD   │
  │  (tree)     │   (messages)     │  (metrics)   │
  └─────────────┴──────────────────┴──────────────┘
"""

import asyncio
import os
import sys
import time
import threading
from pathlib import Path
from typing import Any, Optional

from rich.console import Console
from rich.panel import Panel
from rich.layout import Layout
from rich.live import Live
from rich.align import Align
from rich.text import Text
from rich.tree import Tree
from rich.table import Table
from rich.columns import Columns
from rich import box

from cyberclaw.utils.config import Config
from cyberclaw.utils.i18n import get_translator

console = Console()

BANNER = """
   ______      __              ______ __
  / ____/_  __/ /_  ___  _____/ ____// /___ __      __
 / /   / / / / __ \\/ _ \\/ ___/ /    / / __ `/ | /| / /
/ /___/ /_/ / /_/ /  __/ /  / /___ / / /_/ /| |/ |/ /
\\____/\\__, /_.___/\\___/_/   \\____//_/\\__,_/ |__/|__/
     /____/
"""

# ── Non-blocking keyboard input (cross-platform) ──────────────────

def _read_key_windows() -> Optional[str]:
    """Non-blocking key read on Windows via msvcrt."""
    try:
        import msvcrt
        if msvcrt.kbhit():
            ch = msvcrt.getwch()
            return ch
    except Exception:
        pass
    return None


def _read_key_unix() -> Optional[str]:
    """Non-blocking key read on Unix/macOS via termios + select."""
    try:
        import select
        import termios
        import tty
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setcbreak(fd)
            rlist, _, _ = select.select([sys.stdin], [], [], 0)
            if rlist:
                return sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    except Exception:
        pass
    return None


def read_key() -> Optional[str]:
    """Cross-platform non-blocking key reader."""
    if sys.platform.startswith("win"):
        return _read_key_windows()
    else:
        return _read_key_unix()


# ── REST helpers (best-effort, non-blocking via threads) ───────────

_cached_metrics: dict[str, Any] = {}
_cached_sessions: list[dict] = []
_cached_messages: list[dict] = []
_fetch_lock = threading.Lock()


def _fetch_data(api_base: str) -> None:
    """Fetch metrics and session data from the gateway API (runs in thread)."""
    global _cached_metrics, _cached_sessions, _cached_messages
    try:
        import httpx
        client = httpx.Client(timeout=2.0)

        # Fetch metrics
        try:
            resp = client.get(f"{api_base}/metrics/json")
            if resp.status_code == 200:
                with _fetch_lock:
                    _cached_metrics = resp.json()
        except Exception:
            pass

        # Fetch sessions
        try:
            resp = client.get(f"{api_base}/sessions")
            if resp.status_code == 200:
                sessions = resp.json()
                with _fetch_lock:
                    _cached_sessions = sessions if isinstance(sessions, list) else []

                # Fetch latest session messages
                if _cached_sessions:
                    latest = _cached_sessions[-1]
                    sid = latest.get("session_id", "")
                    if sid:
                        try:
                            msg_resp = client.get(f"{api_base}/sessions/{sid}/messages")
                            if msg_resp.status_code == 200:
                                msgs = msg_resp.json()
                                with _fetch_lock:
                                    _cached_messages = msgs if isinstance(msgs, list) else []
                        except Exception:
                            pass
        except Exception:
            pass

        client.close()
    except ImportError:
        pass
    except Exception:
        pass


# ── Panel Renderers ────────────────────────────────────────────────

def _build_workspace_tree(workspace: Path, max_depth: int = 3) -> Tree:
    """Build a Rich Tree representing the workspace file structure."""
    tree = Tree(
        f"[bold cyan]📁 {workspace.name}[/bold cyan]",
        guide_style="dim cyan",
    )

    def _add_entries(parent_tree: Tree, parent_path: Path, depth: int) -> None:
        if depth > max_depth:
            parent_tree.add("[dim]...[/dim]")
            return
        try:
            entries = sorted(parent_path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except PermissionError:
            parent_tree.add("[red]⛔ access denied[/red]")
            return

        shown = 0
        for entry in entries:
            # Skip hidden and pycache dirs
            if entry.name.startswith(".") or entry.name == "__pycache__":
                continue
            if shown >= 20:
                parent_tree.add(f"[dim]... and {len(entries) - shown} more[/dim]")
                break
            shown += 1

            if entry.is_dir():
                branch = parent_tree.add(f"[bold yellow]📂 {entry.name}/[/bold yellow]")
                _add_entries(branch, entry, depth + 1)
            else:
                # Color code by extension
                ext = entry.suffix.lower()
                icon = "📄"
                style = "white"
                if ext in (".py",):
                    icon = "🐍"
                    style = "green"
                elif ext in (".yaml", ".yml", ".toml", ".json"):
                    icon = "⚙️"
                    style = "bright_yellow"
                elif ext in (".md", ".txt", ".rst"):
                    icon = "📝"
                    style = "bright_white"
                elif ext in (".js", ".ts", ".html", ".css"):
                    icon = "🌐"
                    style = "bright_cyan"
                size = ""
                try:
                    sz = entry.stat().st_size
                    if sz < 1024:
                        size = f" ({sz}B)"
                    elif sz < 1048576:
                        size = f" ({sz // 1024}KB)"
                    else:
                        size = f" ({sz // 1048576}MB)"
                except Exception:
                    pass
                parent_tree.add(f"[{style}]{icon} {entry.name}[/{style}][dim]{size}[/dim]")

    _add_entries(tree, workspace, 0)
    return tree


def _build_chat_panel() -> Panel:
    """Build the center chat console panel from cached session messages."""
    with _fetch_lock:
        messages = list(_cached_messages)
        sessions = list(_cached_sessions)

    lines = []
    if not sessions:
        lines.append("[dim italic]No active sessions. Start a chat to see messages here.[/dim italic]")
    else:
        latest_session = sessions[-1]
        sid = latest_session.get("session_id", "unknown")[:12]
        agent_id = latest_session.get("agent_id", "default")
        lines.append(f"[bold bright_cyan]Session:[/bold bright_cyan] [dim]{sid}...[/dim]  [bold]Agent:[/bold] {agent_id}")
        lines.append("─" * 40)

        if not messages:
            lines.append("[dim italic]No messages in this session yet.[/dim italic]")
        else:
            # Show last 15 messages
            recent = messages[-15:]
            for msg in recent:
                role = msg.get("role", "unknown")
                content = msg.get("content", "")
                # Truncate long content
                if len(content) > 200:
                    content = content[:200] + "..."

                if role == "user":
                    lines.append(f"[bold green]👤 User:[/bold green]")
                    lines.append(f"  {content}")
                elif role == "assistant":
                    lines.append(f"[bold magenta]🤖 Assistant:[/bold magenta]")
                    lines.append(f"  {content}")
                elif role == "system":
                    lines.append(f"[bold yellow]⚡ System:[/bold yellow]")
                    lines.append(f"  [dim]{content}[/dim]")
                else:
                    lines.append(f"[bold]{role}:[/bold] {content}")
                lines.append("")

    content = "\n".join(lines) if lines else "[dim]Waiting for data...[/dim]"
    return Panel(
        content,
        title="[bold bright_cyan]💬 Live Chat Console[/bold bright_cyan]",
        border_style="bright_cyan",
        box=box.ROUNDED,
        padding=(1, 1),
    )


def _build_telemetry_panel(config: Config) -> Panel:
    """Build the right telemetry metrics dashboard panel."""
    with _fetch_lock:
        metrics = dict(_cached_metrics)
        sessions = list(_cached_sessions)

    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column("Key", style="bold bright_yellow", no_wrap=True)
    table.add_column("Value", style="white")

    # Runtime info
    uptime = metrics.get("uptime_seconds", 0)
    if uptime > 3600:
        uptime_str = f"{uptime / 3600:.1f}h"
    elif uptime > 60:
        uptime_str = f"{uptime / 60:.1f}m"
    else:
        uptime_str = f"{uptime:.0f}s"

    table.add_row("⏱ Uptime", uptime_str)
    table.add_row("📡 Gateway", f"http://{config.api.host}:{config.api.port}")
    table.add_row("🤖 Agent", config.default_agent)
    table.add_row("🔧 Provider", config.llm.default_provider)
    table.add_row("🛡 Sandbox", config.sandbox)
    table.add_row("📊 Sessions", str(len(sessions)))
    table.add_row("", "")

    # Counters from metrics
    counters = metrics.get("counters", {})
    gauges = metrics.get("gauges", {})
    histograms = metrics.get("histograms", {})

    # LLM token counts
    total_tokens_in = 0
    total_tokens_out = 0
    total_llm_calls = 0
    for key, val in counters.items():
        if "tokens_in" in key:
            total_tokens_in += val
        elif "tokens_out" in key:
            total_tokens_out += val
        elif "llm_calls" in key:
            total_llm_calls += val

    table.add_row("[bold cyan]── Token Stats ──[/bold cyan]", "")
    table.add_row("📥 Tokens In", f"{int(total_tokens_in):,}")
    table.add_row("📤 Tokens Out", f"{int(total_tokens_out):,}")
    table.add_row("🔄 LLM Calls", str(int(total_llm_calls)))

    # Cost estimation (rough: $0.002 per 1K tokens average)
    total_tokens = total_tokens_in + total_tokens_out
    est_cost = (total_tokens / 1000.0) * 0.002
    table.add_row("💰 Est. Cost", f"${est_cost:.4f}")
    table.add_row("", "")

    # Latency from histograms
    table.add_row("[bold cyan]── Latency ──[/bold cyan]", "")
    latency_found = False
    for key, val in histograms.items():
        if "latency" in key:
            avg = val.get("avg", 0)
            count = val.get("count", 0)
            label = key.split("|")[0].replace("cyberclaw_", "").replace("_", " ").title()
            table.add_row(f"⚡ {label}", f"{avg:.3f}s (n={count})")
            latency_found = True
    if not latency_found:
        table.add_row("⚡ Avg Latency", "[dim]n/a[/dim]")

    # Active session gauge
    table.add_row("", "")
    table.add_row("[bold cyan]── System ──[/bold cyan]", "")
    active = int(gauges.get("cyberclaw_active_sessions", 0))
    table.add_row("🟢 Active", str(active))

    # Channel messages
    total_ch_msgs = sum(v for k, v in counters.items() if "channel_messages" in k)
    table.add_row("📨 Ch. Msgs", str(int(total_ch_msgs)))

    # API requests
    total_api = sum(v for k, v in counters.items() if "api_requests" in k)
    table.add_row("🌐 API Reqs", str(int(total_api)))

    return Panel(
        table,
        title="[bold bright_yellow]📊 Telemetry[/bold bright_yellow]",
        border_style="bright_yellow",
        box=box.ROUNDED,
        padding=(1, 0),
    )


# ── Main TUI Class ────────────────────────────────────────────────

class CyberClawTUI:
    """Interactive TUI Dashboard — 3-pane side-by-side layout with live refresh."""

    def __init__(self, config: Config):
        self.config = config
        self.t = get_translator(config.language)
        self._api_base = f"http://{config.api.host}:{config.api.port}"
        self._running = False

    def draw_dashboard(self) -> Layout:
        """Render the full 3-pane dashboard layout."""
        layout = Layout()

        # Top-level split: header + body + footer
        layout.split_column(
            Layout(name="header", size=4),
            Layout(name="body"),
            Layout(name="footer", size=3),
        )

        # Header
        header_text = Text(BANNER.strip(), style="bold cyan")
        layout["header"].update(
            Panel(
                Align.center(header_text),
                border_style="bright_cyan",
                box=box.DOUBLE,
            )
        )

        # Body: 3 horizontal panes
        layout["body"].split_row(
            Layout(name="left", ratio=1, minimum_size=25),
            Layout(name="center", ratio=2, minimum_size=40),
            Layout(name="right", ratio=1, minimum_size=30),
        )

        # Left: Workspace Explorer
        workspace_tree = _build_workspace_tree(self.config.workspace, max_depth=2)
        layout["left"].update(
            Panel(
                workspace_tree,
                title="[bold green]📁 Workspace[/bold green]",
                border_style="green",
                box=box.ROUNDED,
                padding=(0, 0),
            )
        )

        # Center: Chat Console
        layout["center"].update(_build_chat_panel())

        # Right: Telemetry
        layout["right"].update(_build_telemetry_panel(self.config))

        # Footer: Controls
        controls = [
            "[bold green][1][/bold green] Chat",
            "[bold cyan][2][/bold cyan] Doctor",
            "[bold yellow][3][/bold yellow] Plugins",
            "[bold magenta][4][/bold magenta] Migrate",
            "[bold red][5/q][/bold red] Exit",
            "[dim]  Auto-refresh 2Hz[/dim]",
        ]
        footer_text = Text.from_markup("  │  ".join(controls))
        layout["footer"].update(
            Panel(
                Align.center(footer_text),
                border_style="dim",
                box=box.ROUNDED,
            )
        )

        return layout

    def _background_fetch(self) -> None:
        """Periodically fetch API data in a background thread."""
        while self._running:
            _fetch_data(self._api_base)
            time.sleep(2.0)

    def start(self) -> None:
        """Start the TUI with Rich Live rendering and non-blocking keyboard input."""
        self._running = True

        # Start background data fetcher thread
        fetch_thread = threading.Thread(target=self._background_fetch, daemon=True)
        fetch_thread.start()

        # Initial data fetch
        _fetch_data(self._api_base)

        console.clear()

        with Live(self.draw_dashboard(), console=console, refresh_per_second=2, screen=True) as live:
            while self._running:
                # Non-blocking key check
                key = read_key()

                if key in ("5", "q", "Q"):
                    self._running = False
                    break
                elif key == "1":
                    # Launch chat
                    live.stop()
                    console.clear()
                    console.print("[bold cyan]Starting Live Chat. Type 'exit' to return to dashboard.[/bold cyan]")
                    from cyberclaw.cli.main import chat
                    try:
                        class MockContext:
                            obj = {"config": self.config}
                        chat(ctx=MockContext())  # type: ignore
                    except Exception as e:
                        console.print(f"[red]Error starting chat: {e}[/red]")
                    console.input("\nPress Enter to return to Dashboard...")
                    console.clear()
                    live.start()
                elif key == "2":
                    live.stop()
                    console.clear()
                    console.print("[bold cyan]Running System Doctor check...[/bold cyan]")
                    from cyberclaw.cli.main import doctor
                    class MockContext2:
                        obj = {"config": self.config}
                    try:
                        doctor(ctx=MockContext2(), repair=False)  # type: ignore
                    except Exception as e:
                        console.print(f"[dim]Doctor completed: {e}[/dim]")
                    console.input("\nPress Enter to return to Dashboard...")
                    console.clear()
                    live.start()
                elif key == "3":
                    live.stop()
                    console.clear()
                    console.print("[bold cyan]Discovered Plugins Manager:[/bold cyan]")
                    from cyberclaw.cli.main import plugins_list
                    class MockContext3:
                        obj = {"config": self.config}
                    try:
                        plugins_list(ctx=MockContext3())  # type: ignore
                    except Exception as e:
                        console.print(f"[red]Error listing plugins: {e}[/red]")
                    console.input("\nPress Enter to return to Dashboard...")
                    console.clear()
                    live.start()
                elif key == "4":
                    live.stop()
                    console.clear()
                    console.print("[bold cyan]Database & Configuration Migration Utility[/bold cyan]")
                    console.print("This tool migrates database configuration files from OpenClaw to CyberClaw.")
                    db_path = console.input("Enter path to OpenClaw DB/YAML file: ").strip()
                    if db_path:
                        from cyberclaw.utils.migrator import OpenClawMigrator
                        migrator = OpenClawMigrator(self.config)
                        migrator.migrate(Path(db_path))
                    console.input("\nPress Enter to return to Dashboard...")
                    console.clear()
                    live.start()

                # Refresh display
                live.update(self.draw_dashboard())

                # 2Hz refresh — sleep 0.5s between polls
                time.sleep(0.5)

        self._running = False
        console.clear()
        console.print("[yellow]CyberClaw TUI Dashboard exited.[/yellow]")
