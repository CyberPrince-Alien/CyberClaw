"""Interactive TUI dashboard using Rich console."""

import asyncio
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.layout import Layout
from rich.live import Live
from rich.align import Align
from rich.text import Text

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

class CyberClawTUI:
    """Interactive TUI Dashboard helper."""

    def __init__(self, config: Config):
        self.config = config
        self.t = get_translator(config.language)

    def draw_dashboard(self) -> Layout:
        """Render the layout grid."""
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=8),
            Layout(name="body"),
            Layout(name="footer", size=3),
        )

        # Header panel
        header_text = Text(BANNER, style="bold cyan")
        layout["header"].update(Panel(Align.center(header_text), border_style="cyan"))

        # Body panel (status + menu)
        status_lines = [
            f"[bold]Workspace:[/bold] {self.config.workspace}",
            f"[bold]Language:[/bold] {self.config.language.upper()}",
            f"[bold]Default Agent:[/bold] {self.config.default_agent}",
            f"[bold]Active LLM Provider:[/bold] {self.config.llm.default_provider}",
            f"[bold]API Server:[/bold] http://{self.config.api.host}:{self.config.api.port}",
            "",
            "[bold cyan]" + self.t.translate("tui_nav") + "[/bold cyan]",
            "  " + self.t.translate("option_chat"),
            "  " + self.t.translate("option_doctor"),
            "  " + self.t.translate("option_plugins"),
            "  " + self.t.translate("option_migrate"),
            "  " + self.t.translate("option_exit"),
        ]
        
        body_panel = Panel(
            "\n".join(status_lines),
            title="[bold yellow]" + self.t.translate("tui_title") + "[/bold yellow]",
            border_style="yellow",
        )
        layout["body"].update(body_panel)

        # Footer panel
        footer_text = Text("CyberClaw CLI v0.2.0 • Press key [1-5] to select action", style="dim white")
        layout["footer"].update(Panel(Align.center(footer_text), border_style="dim"))

        return layout

    def start(self) -> None:
        """Start the TUI input processing loop."""
        console.clear()
        
        while True:
            # Render layout
            layout = self.draw_dashboard()
            console.print(layout)

            try:
                choice = console.input("\n[bold green]Choose option [1-5]:[/bold green] ").strip()
            except (KeyboardInterrupt, EOFError):
                break

            if choice == "5":
                console.print("[yellow]Exiting TUI dashboard...[/yellow]")
                break
            elif choice == "1":
                console.clear()
                console.print("[bold cyan]Starting Live Chat. Type 'exit' to return to dashboard.[/bold cyan]")
                # We will invoke the CLI chat flow synchronously
                from cyberclaw.cli.main import chat
                import sys
                try:
                    # Mock Typer Context
                    class MockContext:
                        obj = {"config": self.config}
                    chat(ctx=MockContext()) # type: ignore
                except Exception as e:
                    console.print(f"[red]Error starting chat: {e}[/red]")
                console.input("\nPress Enter to return to Dashboard...")
                console.clear()
            elif choice == "2":
                console.clear()
                console.print("[bold cyan]Running System Doctor check...[/bold cyan]")
                from cyberclaw.cli.main import doctor
                class MockContext:
                    obj = {"config": self.config}
                try:
                    doctor(ctx=MockContext(), repair=False) # type: ignore
                except Exception as e:
                    console.print(f"[dim]Doctor completed: {e}[/dim]")
                console.input("\nPress Enter to return to Dashboard...")
                console.clear()
            elif choice == "3":
                console.clear()
                console.print("[bold cyan]Discovered Plugins Manager:[/bold cyan]")
                from cyberclaw.cli.main import plugins_list
                class MockContext:
                    obj = {"config": self.config}
                try:
                    plugins_list(ctx=MockContext()) # type: ignore
                except Exception as e:
                    console.print(f"[red]Error listing plugins: {e}[/red]")
                console.input("\nPress Enter to return to Dashboard...")
                console.clear()
            elif choice == "4":
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
            else:
                console.print("[red]Invalid choice. Please enter 1, 2, 3, 4, or 5.[/red]")
                asyncio.run(asyncio.sleep(1.5))
                console.clear()
