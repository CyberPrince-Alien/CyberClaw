"""CLI interface for cyberclaw using Typer."""

# Suppress LiteLLM warnings BEFORE it's imported (import-time noise about botocore)
import os as _os
import logging as _logging
import warnings as _warnings
_os.environ["LITELLM_LOG"] = "ERROR"
_logging.getLogger("LiteLLM").setLevel(_logging.ERROR)
_logging.getLogger("litellm").setLevel(_logging.ERROR)

import litellm
litellm.suppress_helper_warnings = True

_warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")

from pathlib import Path
import asyncio
import subprocess
from types import SimpleNamespace
from typing import Annotated

import yaml
import typer
from rich.console import Console
from rich.table import Table

from cyberclaw.cli.chat import chat_command
from cyberclaw.cli.server import server_command
from cyberclaw.cli.model_selector import run_model_selection_wizard
from cyberclaw.core.agent import Agent
from cyberclaw.core.context import SharedContext
from cyberclaw.core.events import CliEventSource
from cyberclaw.utils.config import Config
from cyberclaw.utils.logging import setup_logging

# Fix Windows console encoding for emoji/unicode output
if _os.name == 'nt':
    import sys as _sys
    _os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
    if hasattr(_sys.stdout, 'reconfigure'):
        try:
            _sys.stdout.reconfigure(encoding='utf-8', errors='replace')
            _sys.stderr.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass

app = typer.Typer(
    name="cyberclaw",
    help="CyberClaw: personal AI assistant",
    no_args_is_help=True,
    add_completion=True,
)
gateway_app = typer.Typer(help="Manage the CyberClaw gateway/server")
config_app = typer.Typer(help="Show or update CyberClaw configuration")
sessions_app = typer.Typer(help="Inspect CyberClaw conversation sessions")
pairing_app = typer.Typer(help="Manage DM pairing for channels")
channels_app = typer.Typer(help="Manage messaging channels and login")

console = Console()


def workspace_callback(ctx: typer.Context, workspace: str) -> Path:
    """Store workspace path in context for later use.

    Smart auto-detection order:
    1. Explicit --workspace / -w flag
    2. ./workspace/config.user.yaml  (CWD has workspace subdir)
    3. ./config.user.yaml            (CWD IS the workspace)
    4. Walk up to 5 parent dirs looking for workspace/config.user.yaml
    5. ~/.cyberclaw/workspace/config.user.yaml (global default)
    6. Fallback to 'workspace' (old behaviour)
    """
    ctx.ensure_object(dict)

    # If user explicitly provided a path, use it
    resolved = Path(workspace)
    if workspace != "workspace":
        ctx.obj["workspace"] = resolved
        return resolved

    # Auto-detect: ./workspace/
    if (Path.cwd() / "workspace" / "config.user.yaml").exists():
        ctx.obj["workspace"] = Path.cwd() / "workspace"
        return ctx.obj["workspace"]

    # Auto-detect: CWD is workspace itself
    if (Path.cwd() / "config.user.yaml").exists():
        ctx.obj["workspace"] = Path.cwd()
        return ctx.obj["workspace"]

    # Walk up parents (up to 5 levels)
    current = Path.cwd()
    for _ in range(5):
        parent = current.parent
        if parent == current:
            break
        candidate = parent / "workspace" / "config.user.yaml"
        if candidate.exists():
            ctx.obj["workspace"] = parent / "workspace"
            return ctx.obj["workspace"]
        candidate2 = parent / "config.user.yaml"
        if candidate2.exists():
            ctx.obj["workspace"] = parent
            return ctx.obj["workspace"]
        current = parent

    # Global default: ~/.cyberclaw/workspace/
    global_ws = Path.home() / ".cyberclaw" / "workspace"
    if (global_ws / "config.user.yaml").exists():
        ctx.obj["workspace"] = global_ws
        return ctx.obj["workspace"]

    # Fallback
    ctx.obj["workspace"] = resolved
    return resolved


@app.callback()
def main(
    ctx: typer.Context,
    workspace: str = typer.Option(
        "workspace",
        "--workspace",
        "-w",
        help="Path to workspace directory",
        callback=workspace_callback,
    ),
) -> None:
    """Configuration is loaded from workspace/config.user.yaml by default."""
    workspace_path = ctx.obj["workspace"]
    config_file = workspace_path / "config.user.yaml"

    if ctx.invoked_subcommand == "onboard":
        return

    if not config_file.exists():
        console.print(f"[yellow]No configuration found at {config_file}[/yellow]")
        console.print("\n[dim]Searched locations:[/dim]")
        console.print(f"  [dim]• {Path.cwd() / 'workspace' / 'config.user.yaml'}[/dim]")
        console.print(f"  [dim]• {Path.cwd() / 'config.user.yaml'}[/dim]")
        console.print(f"  [dim]• {Path.home() / '.cyberclaw' / 'workspace' / 'config.user.yaml'}[/dim]")
        console.print("\n[bold cyan]Fix:[/bold cyan] Run [green]cyberclaw onboard[/green] to create a workspace")
        console.print("     or use [green]cyberclaw -w /path/to/workspace chat[/green]")
        raise typer.Exit(1)

    try:
        cfg = Config.load(workspace_path)
        ctx.obj["config"] = cfg
    except Exception as e:
        console.print(f"[red]Error loading config: {e}[/red]")
        raise typer.Exit(1)


@app.command("chat")
def chat(
    ctx: typer.Context,
    agent: Annotated[
        str | None,
        typer.Option(
            "--agent",
            "-a",
            help="Agent ID to use (overrides default_agent from config)",
        ),
    ] = None,
) -> None:
    """Start interactive chat session."""
    chat_command(ctx, agent_id=agent)


@app.command("agent")
def agent_once(
    ctx: typer.Context,
    message: Annotated[
        str,
        typer.Option("--message", "-m", help="Message to send to the agent."),
    ],
    agent: Annotated[
        str | None,
        typer.Option("--agent", "-a", help="Agent ID to use."),
    ] = None,
) -> None:
    """Run one non-interactive agent turn."""
    cfg: Config = ctx.obj["config"]
    setup_logging(cfg, console_output=False)

    async def run_once() -> str:
        context = SharedContext(cfg, [])
        agent_id = agent or cfg.default_agent
        agent_def = context.agent_loader.load(agent_id)
        session = Agent(agent_def, context).new_session(CliEventSource())
        return await session.chat(message)

    console.print(asyncio.run(run_once()))


@app.command("server")
def server(ctx: typer.Context) -> None:
    """Start the 24/7 server for cron and messagebus execution."""
    server_command(ctx)


@app.command("version")
def version_cmd() -> None:
    """Show CyberClaw version."""
    console.print("[bold cyan]CyberClaw[/bold cyan] v0.2.0")


@app.command("onboard")
def onboard(
    ctx: typer.Context,
    install_daemon: Annotated[
        bool,
        typer.Option(
            "--install-daemon",
            help="Accepted for backward compatibility; CyberClaw starts in the foreground.",
        ),
    ] = False,
) -> None:
    """Create the local workspace files needed for first run."""
    workspace_path: Path = ctx.obj["workspace"]

    console.print("\n[bold magenta]======================================================================[/bold magenta]")
    console.print("[bold cyan]          === CYBERCLAW AUTOMATIC ONBOARDING & SETUP WIZARD ===          [/bold cyan]")
    console.print("[bold magenta]======================================================================[/bold magenta]")
    console.print("  [bold white]Brought to you with love by Cyber Prince (Sourov)[/bold white]")
    console.print("  [dim]Initializing workspace files, database registries, and configurations...[/dim]\n")

    # Step 1: Checking workspace
    console.print("[yellow][?] Step 1: Checking local workspace path...[/yellow]")
    workspace_path.mkdir(parents=True, exist_ok=True)
    console.print(f"      [green]OK[/green] Active path: [cyan]{workspace_path}[/cyan]\n")

    # Step 2: Creating directories and copying templates
    console.print("[yellow][DIR] Step 2: Generating directory structures and copying default templates...[/yellow]")
    import shutil
    template_dir = Path(__file__).resolve().parent.parent / "workspace_template"
    if template_dir.exists():
        def copy_template_dir(src: Path, dest: Path) -> None:
            for item in src.iterdir():
                if item.name in (".event", ".history", ".logs", ".pairing", "config.user.yaml", "__pycache__"):
                    continue
                d_item = dest / item.name
                if item.is_dir():
                    d_item.mkdir(exist_ok=True)
                    copy_template_dir(item, d_item)
                else:
                    if not d_item.exists():
                        shutil.copy2(item, d_item)
        copy_template_dir(template_dir, workspace_path)
        console.print(f"      [green]OK[/green] Workspace initialized with default agents, skills, and templates.\n")
    else:
        # Fallback in case of dev environment or missing template
        dirs_created = []
        for directory in ("agents", "skills", "crons", "memories", "plugins"):
            dpath = workspace_path / directory
            dpath.mkdir(exist_ok=True)
            dirs_created.append(directory)
        console.print(f"      [green]OK[/green] Folders initialized: [cyan]{', '.join(dirs_created)}[/cyan] (Template directory not found)\n")

    # Step 3: Deploy and Configure setting
    console.print("[yellow][FILE] Step 3: Setting up user configuration files...[/yellow]")
    config_path = workspace_path / "config.user.yaml"
    example_path = workspace_path / "config.example.yaml"

    # Load initial template settings
    config_data = {}
    if example_path.exists():
        try:
            with open(example_path) as f:
                config_data = yaml.safe_load(f) or {}
        except Exception:
            pass

    if not config_data:
        # Core fallback template
        config_data = {
            "llm": {
                "default_provider": "openai",
                "temperature": 0.7,
                "max_tokens": 2048,
                "enable_failover": True,
                "providers": [
                    {
                        "id": "openai",
                        "provider": "openai",
                        "model": "gpt-4",
                        "api_key": "sk-your-openai-api-key-here",
                        "priority": 1,
                        "enabled": True,
                    }
                ],
            },
            "default_agent": "cyberclaw",
            "api": {"host": "127.0.0.1", "port": 8000},
        }

    # Prompt user for interactive configuration
    run_interactive = typer.confirm(
        "\nWould you like to run the Premium Model Selection Wizard (V9 Style) now?",
        default=False,
    )

    if run_interactive:
        # Language Selection
        console.print("\nSelect your preferred language / ভাষা নির্বাচন করুন:")
        console.print("  1) English (en)")
        console.print("  2) Bengali (bn)")
        console.print("  3) Spanish (es)")
        console.print("  4) French (fr)")
        console.print("  5) German (de)")
        lang_choice = typer.prompt("Enter choice (1-5)", default="1")
        lang_map = {"1": "en", "2": "bn", "3": "es", "4": "fr", "5": "de"}
        config_data["language"] = lang_map.get(lang_choice, "en")
        console.print(f"  [green]OK[/green] Language set to: {config_data['language'].upper()}\n")

        # Deploy base config first so model selector has a file to merge into
        if not config_path.exists():
            with open(config_path, "w") as f:
                yaml.safe_dump(config_data, f, sort_keys=False, default_flow_style=False)

        # ── STEP A: Launch Premium V9-Style Model Selector ──────────────────
        def _launch_chat_from_onboard(ws_path: Path) -> None:
            """Chat launcher callback for model selector."""
            try:
                cfg = Config.load(ws_path)
                fake_ctx = SimpleNamespace(obj={"config": cfg, "workspace": ws_path})
                chat_command(fake_ctx, agent_id=None)
            except Exception as e:
                console.print(f"[red]Chat launch failed: {e}[/red]")
                console.print("[dim]You can start chatting manually: cyberclaw chat[/dim]")

        run_model_selection_wizard(workspace_path, launch_chat_callback=_launch_chat_from_onboard)

        # Reload config after model selector may have updated it
        try:
            with open(config_path) as f:
                config_data = yaml.safe_load(f) or config_data
        except Exception:
            pass

        # ── STEP B: Gateway ─────────────────────────────────────────────────
        console.print("\n[bold yellow]======================================================[/bold yellow]")
        console.print("[bold yellow]   GATEWAY SERVER SETUP                              [/bold yellow]")
        console.print("[bold yellow]======================================================[/bold yellow]")
        port = 8000
        while True:
            port = typer.prompt("HTTP Gateway Port", default=8000, type=int)
            if 1 <= port <= 65535:
                break
            console.print(f"  [red]❌ Port must be between 1 and 65535 (you entered {port})[/red]")
        if "api" not in config_data:
            config_data["api"] = {}
        config_data["api"]["host"] = "127.0.0.1"
        config_data["api"]["port"] = port
        console.print(f"  [green]OK[/green] Gateway will run on port [cyan]{port}[/cyan]")

        # ── STEP C: Channels ────────────────────────────────────────────────
        console.print("\n[bold yellow]======================================================[/bold yellow]")
        console.print("[bold yellow]   MESSAGING CHANNELS SETUP                          [/bold yellow]")
        console.print("[bold yellow]======================================================[/bold yellow]")
        console.print("  Available channels: Telegram, Discord, WhatsApp, Slack, Signal, Matrix, IRC")
        configure_channels = typer.confirm("Configure messaging channels now?", default=False)

        if configure_channels:
            if "channels" not in config_data:
                config_data["channels"] = {}
            config_data["channels"]["enabled"] = True

            # Telegram
            if typer.confirm("  Enable Telegram?", default=False):
                tg_token = typer.prompt("  Telegram Bot Token", hide_input=True)
                config_data["channels"]["telegram"] = {
                    "enabled": True, "bot_token": tg_token,
                    "dm_policy": "pairing", "allow_from": [],
                }
                console.print("  [green]OK[/green] Telegram configured")

            # Discord
            if typer.confirm("  Enable Discord?", default=False):
                dc_token = typer.prompt("  Discord Bot Token", hide_input=True)
                config_data["channels"]["discord"] = {
                    "enabled": True, "bot_token": dc_token,
                    "dm_policy": "pairing", "allow_from": [],
                }
                console.print("  [green]OK[/green] Discord configured")

            # WhatsApp
            if typer.confirm("  Enable WhatsApp Business API?", default=False):
                wa_phone = typer.prompt("  WhatsApp Phone Number ID")
                wa_token = typer.prompt("  WhatsApp Access Token", hide_input=True)
                wa_verify = typer.prompt("  WhatsApp Verify Token", default="cyberclaw-verify")
                config_data["channels"]["whatsapp"] = {
                    "enabled": True, "phone_number_id": wa_phone,
                    "access_token": wa_token, "verify_token": wa_verify,
                    "dm_policy": "pairing", "allow_from": [],
                }
                console.print("  [green]OK[/green] WhatsApp configured")

            # Slack
            if typer.confirm("  Enable Slack?", default=False):
                sl_bot   = typer.prompt("  Slack Bot Token (xoxb-...)", hide_input=True)
                sl_app   = typer.prompt("  Slack App-Level Token (xapp-...)", hide_input=True)
                config_data["channels"]["slack"] = {
                    "enabled": True, "bot_token": sl_bot, "app_token": sl_app,
                    "dm_policy": "pairing", "allow_from": [],
                }
                console.print("  [green]OK[/green] Slack configured")

            # Signal
            if typer.confirm("  Enable Signal (via signal-cli-rest-api)?", default=False):
                sig_url   = typer.prompt("  Signal API URL", default="http://localhost:8080")
                sig_phone = typer.prompt("  Signal Phone Number (e.g. +8801...)")
                config_data["channels"]["signal"] = {
                    "enabled": True, "api_url": sig_url,
                    "phone_number": sig_phone,
                    "dm_policy": "pairing", "allow_from": [],
                }
                console.print("  [green]OK[/green] Signal configured")

            # Matrix
            if typer.confirm("  Enable Matrix?", default=False):
                mat_hs    = typer.prompt("  Matrix Homeserver (e.g. https://matrix.org)")
                mat_user  = typer.prompt("  Matrix User ID (e.g. @bot:matrix.org)")
                mat_token = typer.prompt("  Matrix Access Token", hide_input=True)
                config_data["channels"]["matrix"] = {
                    "enabled": True, "homeserver": mat_hs,
                    "user_id": mat_user, "access_token": mat_token,
                    "allowed_rooms": [], "allow_from": [],
                }
                console.print("  [green]OK[/green] Matrix configured")

            # IRC
            if typer.confirm("  Enable IRC?", default=False):
                irc_server = typer.prompt("  IRC Server (e.g. irc.libera.chat)")
                irc_nick   = typer.prompt("  IRC Nick", default="CyberClaw")
                irc_chan   = typer.prompt("  IRC Channels (comma-separated, e.g. #ai,#bots)", default="#cyberclaw")
                config_data["channels"]["irc"] = {
                    "enabled": True, "server": irc_server, "port": 6667,
                    "nick": irc_nick, "use_ssl": False,
                    "channels": [c.strip() for c in irc_chan.split(",")],
                    "allow_from": [],
                }
                console.print("  [green]OK[/green] IRC configured")

        # ── STEP D: Web Search + Skills ─────────────────────────────────────
        console.print("\n[bold yellow]======================================================[/bold yellow]")
        console.print("[bold yellow]   WEB SEARCH & SKILLS                               [/bold yellow]")
        console.print("[bold yellow]======================================================[/bold yellow]")

        if typer.confirm("Enable Brave Web Search? (get free key at brave.com/search/api)", default=False):
            brave_key = typer.prompt("  Brave Search API Key", hide_input=True)
            config_data["websearch"] = {"provider": "brave", "api_key": brave_key}
            console.print("  [green]OK[/green] Brave web search configured")

        if typer.confirm("Enable Web Page Reading (crawl4ai)?", default=False):
            config_data["webread"] = {"provider": "crawl4ai"}
            console.print("  [green]OK[/green] Web read configured (install: pip install 'cyberclaw[crawler]')")

        # Write final config
        with open(config_path, "w") as f:
            yaml.safe_dump(config_data, f, sort_keys=False, default_flow_style=False)
        console.print(f"\n  [green]OK[/green] Config saved: [cyan]{config_path}[/cyan]")

    else:
        # Non-interactive: deploy template
        if not config_path.exists() and example_path.exists():
            config_path.write_text(example_path.read_text())
            console.print(f"      [green]OK[/green] Deployed [cyan]config.user.yaml[/cyan] template!")
        elif config_path.exists():
            console.print(f"      [green]OK[/green] Found existing [cyan]config.user.yaml[/cyan]")
        else:
            with open(config_path, "w") as f:
                yaml.safe_dump(config_data, f, sort_keys=False, default_flow_style=False)
            console.print(f"      [green]OK[/green] Generated default config file.")

    console.print(f"      [green]OK[/green] Config location: [cyan]{config_path}[/cyan]\n")

    # Final Summary
    console.print("[bold magenta]----------------------------------------------------------------------[/bold magenta]")
    console.print("[bold green]*** CYBERCLAW WORKSPACE SUCCESSFULLY ONBOARDED! ***[/bold green]")
    console.print("[bold magenta]----------------------------------------------------------------------[/bold magenta]")
    console.print("Next steps:")
    console.print("  [bold white]1.[/bold white] Run diagnostics  -> [cyan]cyberclaw doctor[/cyan]")
    console.print("  [bold white]2.[/bold white] Switch model     -> [cyan]cyberclaw select-model[/cyan]")
    console.print("  [bold white]3.[/bold white] List providers   -> [cyan]cyberclaw providers[/cyan]")
    console.print("  [bold white]4.[/bold white] List channels    -> [cyan]cyberclaw channels[/cyan]")
    console.print("  [bold white]5.[/bold white] Launch Web UI    -> [cyan]cyberclaw gateway start[/cyan]")
    console.print("  [bold white]6.[/bold white] Chat in terminal -> [cyan]cyberclaw chat[/cyan]")
    console.print("[bold magenta]======================================================================[/bold magenta]\n")

    if install_daemon:
        console.print(
            "[yellow]Daemon install is not implemented yet; use `cyberclaw gateway start`.[/yellow]"
        )


@app.command("select-model")
def select_model_cmd(
    ctx: typer.Context,
) -> None:
    """Interactively swap active models and providers (Premium V9 Style)."""
    workspace_path: Path = ctx.obj["workspace"]

    def _launch_chat(ws_path: Path) -> None:
        """Chat launcher callback for select-model command."""
        try:
            cfg = Config.load(ws_path)
            fake_ctx = SimpleNamespace(obj={"config": cfg, "workspace": ws_path})
            chat_command(fake_ctx, agent_id=None)
        except Exception as e:
            console.print(f"[red]Chat launch failed: {e}[/red]")
            console.print("[dim]You can start chatting manually: cyberclaw chat[/dim]")

    run_model_selection_wizard(workspace_path, launch_chat_callback=_launch_chat)


def _load_user_config(ctx: typer.Context) -> tuple[Path, dict]:
    config_path = ctx.obj["workspace"] / "config.user.yaml"
    data = yaml.safe_load(config_path.read_text()) or {}
    return config_path, data


def _read_config_key(data: dict, key: str | None) -> object:
    value = data
    if key:
        for part in key.split("."):
            if not isinstance(value, dict) or part not in value:
                raise KeyError(key)
            value = value[part]
    return value


@config_app.command("show")
def config_show(ctx: typer.Context) -> None:
    """Show the full user configuration."""
    _, data = _load_user_config(ctx)
    console.print(yaml.safe_dump(data, sort_keys=False).strip())


@config_app.command("get")
def config_get(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help="Dot-path key, for example `llm.default_provider`.")],
) -> None:
    """Read a config value."""
    _, data = _load_user_config(ctx)
    try:
        value = _read_config_key(data, key)
    except KeyError:
        console.print(f"[red]Config key not found:[/red] {key}")
        raise typer.Exit(1)

    console.print(yaml.safe_dump(value, sort_keys=False).strip())


@config_app.command("set")
def config_set(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help="Dot-path key to update.")],
    value: Annotated[str, typer.Argument(help="YAML value to write.")],
) -> None:
    """Update a config value."""
    config_path, data = _load_user_config(ctx)
    parsed_value = yaml.safe_load(value)
    target = data
    parts = key.split(".")
    for part in parts[:-1]:
        if part not in target or not isinstance(target[part], dict):
            target[part] = {}
        target = target[part]
    target[parts[-1]] = parsed_value
    config_path.write_text(yaml.safe_dump(data, sort_keys=False))
    console.print(f"[green]Updated config:[/green] {key}")


@app.command("doctor")
def doctor(ctx: typer.Context, repair: bool = typer.Option(False, "--repair", help="Auto-repair common issues")) -> None:
    """Check and optionally repair common setup issues."""
    cfg: Config = ctx.obj["config"]
    workspace_path: Path = ctx.obj["workspace"]
    config_path = workspace_path / "config.user.yaml"

    console.print("\n[bold cyan]======================================================[/bold cyan]")
    console.print("[bold cyan]   CYBERCLAW SYSTEM DIAGNOSTICS                      [/bold cyan]")
    console.print("[bold cyan]======================================================[/bold cyan]\n")

    issues: list[str] = []
    repairs: list[str] = []

    # 1. Check providers
    enabled_providers = [p for p in cfg.llm.providers if p.enabled]
    if not enabled_providers:
        issues.append("No enabled LLM providers configured.")
        if repair:
            console.print("[yellow]  [REPAIR] No provider enabled. Run `cyberclaw onboard` to configure.[/yellow]")
    else:
        console.print(f"  [green]OK[/green] LLM Providers: {len(enabled_providers)} enabled")
        for provider in enabled_providers:
            placeholder_markers = ("your-", "sk-your", "api-key-here", "sk-ant-your")
            if any(marker in provider.api_key for marker in placeholder_markers):
                issues.append(f"Provider `{provider.id}` has a placeholder API key.")
                if repair:
                    console.print(f"  [yellow][REPAIR] Fixing placeholder key for '{provider.id}'...[/yellow]")
                    new_key = typer.prompt(f"  Enter real API key for {provider.id.upper()}", hide_input=True)
                    try:
                        config_data = yaml.safe_load(config_path.read_text()) or {}
                        for prov in config_data.get("llm", {}).get("providers", []):
                            if prov.get("id") == provider.id:
                                prov["api_key"] = new_key
                        config_path.write_text(yaml.safe_dump(config_data, sort_keys=False))
                        repairs.append(f"Fixed API key for {provider.id}")
                        console.print(f"  [green]REPAIRED[/green] API key updated for '{provider.id}'")
                    except Exception as e:
                        console.print(f"  [red]REPAIR FAILED:[/red] {e}")
            else:
                console.print(f"  [green]OK[/green] Provider '{provider.id}' -> model: {provider.model}")

    # 2. Check workspace dirs
    for d in ("agents", "skills", "crons", "memories", "plugins"):
        dpath = workspace_path / d
        if dpath.exists():
            console.print(f"  [green]OK[/green] Directory '{d}' exists")
        else:
            issues.append(f"Missing workspace directory: {d}")
            if repair:
                dpath.mkdir(parents=True, exist_ok=True)
                repairs.append(f"Created missing directory: {d}")
                console.print(f"  [green]REPAIRED[/green] Created directory '{d}'")

    # 3. Check config file
    if config_path.exists():
        console.print(f"  [green]OK[/green] Config file: {config_path}")
    else:
        issues.append("config.user.yaml is missing.")
        if repair:
            example = workspace_path / "config.example.yaml"
            if example.exists():
                config_path.write_text(example.read_text())
                repairs.append("Restored config.user.yaml from template")
                console.print(f"  [green]REPAIRED[/green] Restored config.user.yaml")

    # 4. Check channels
    if cfg.channels.enabled:
        channel_names = ["telegram", "discord", "slack", "whatsapp", "matrix", "irc", "signal"]
        for name in channel_names:
            channel = getattr(cfg.channels, name, None)
            if channel and getattr(channel, "enabled", False):
                policy = getattr(channel, "dm_policy", None)
                allow  = getattr(channel, "allow_from", [])
                if policy == "open" and "*" in allow:
                    issues.append(f"Channel '{name}': dm_policy=open with allow_from=* is insecure.")
                    console.print(f"  [yellow]WARN[/yellow] Channel '{name}': open to all senders (security risk)")
                else:
                    console.print(f"  [green]OK[/green] Channel '{name}' enabled (dm_policy={policy})")

    # 5. Summary
    console.print()
    if issues and not repairs:
        console.print(f"[yellow]Found {len(issues)} issue(s):[/yellow]")
        for issue in issues:
            console.print(f"  [!] {issue}")
        console.print(f"\n[dim]Run with --repair to auto-fix: [/dim][cyan]cyberclaw doctor --repair[/cyan]")
        raise typer.Exit(1)
    elif repairs:
        console.print(f"[green]Repaired {len(repairs)} issue(s) automatically![/green]")
        for r in repairs:
            console.print(f"  [+] {r}")
        remaining = len(issues) - len(repairs)
        if remaining > 0:
            console.print(f"[yellow]{remaining} issue(s) still need manual attention.[/yellow]")
    else:
        console.print("[bold green]All checks passed - CyberClaw is healthy![/bold green]")
    console.print("[bold cyan]======================================================[/bold cyan]\n")


@channels_app.command("list")
def channels_list(ctx: typer.Context) -> None:
    """List configured messaging channels."""
    cfg: Config = ctx.obj["config"]
    channel_names = [
        "telegram", "discord", "slack", "whatsapp", "matrix", "irc", "webchat",
    ]
    rows = []
    for name in channel_names:
        channel = getattr(cfg.channels, name, None)
        if channel:
            enabled = getattr(channel, "enabled", True)
            dm_policy = getattr(channel, "dm_policy", "n/a")
            allow_count = len(getattr(channel, "allow_from", []))
            rows.append(
                f"  {name}: enabled={enabled}, dm_policy={dm_policy}, allow_from={allow_count}"
            )

    if not rows:
        console.print("No channels configured.")
        return

    console.print("[bold]Configured channels:[/bold]")
    console.print("\n".join(rows))


@channels_app.command("login")
def channels_login(
    ctx: typer.Context,
    channel: str = typer.Option("whatsapp", "--channel", "-c", help="Channel to log in (e.g. whatsapp)"),
) -> None:
    """Pair and link a messaging channel (interactive QR scan for WhatsApp)."""
    if channel.lower() != "whatsapp":
        console.print(f"[red]Interactive login is only supported for channel: whatsapp[/red]")
        raise typer.Exit(1)

    # Load config to ensure WhatsApp is configured
    cfg: Config = ctx.obj["config"]
    whatsapp_cfg = cfg.channels.whatsapp
    if not whatsapp_cfg or not whatsapp_cfg.enabled:
        console.print("[yellow]WhatsApp channel is not enabled in config.user.yaml. Enabling temporarily for login...[/yellow]")
    
    import sys
    import json
    import subprocess
    from pathlib import Path

    # Determine paths
    bridge_dir = Path(__file__).parent.parent / "channel" / "whatsapp_bridge"
    node_modules = bridge_dir / "node_modules"
    
    if not node_modules.exists():
        console.print("[cyan]WhatsApp bridge dependencies not found. Installing dependencies via npm...[/cyan]")
        try:
            subprocess.run(
                ["npm", "install", "--no-audit", "--no-fund"],
                cwd=str(bridge_dir),
                shell=True,
                check=True
            )
            console.print("[green]Bridge dependencies installed successfully![/green]\n")
        except Exception as e:
            console.print(f"[red]Failed to install bridge dependencies: {e}[/red]")
            console.print("Make sure Node.js is installed on your system.")
            raise typer.Exit(1)

    auth_dir = Path.home() / ".cyberclaw" / "whatsapp_auth"
    auth_dir.mkdir(parents=True, exist_ok=True)
    
    bridge_script = bridge_dir / "bridge.js"
    
    console.print("[bold cyan]Starting WhatsApp Link Device pairing flow...[/bold cyan]")
    console.print("[dim]A terminal QR code will be generated. Scan it using your WhatsApp Linked Devices menu.[/dim]\n")
    
    try:
        # Run the Node bridge subprocess and pipe stdout/stderr
        process = subprocess.Popen(
            ["node", str(bridge_script), str(auth_dir)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        
        # Loop reading output lines in real time
        while True:
            line = process.stdout.readline()
            if not line:
                break
            
            line_stripped = line.strip()
            if not line_stripped:
                continue
                
            try:
                data = json.loads(line_stripped)
                msg_type = data.get("type")
                
                if msg_type == "connection":
                    status = data.get("status")
                    if status == "open":
                        console.print(f"\n[bold green]✔ WhatsApp successfully linked to {data.get('phone')} ({data.get('name')})![/bold green]")
                        console.print("[green]You can now start your CyberClaw server using:[/green] [bold]cyberclaw server[/bold]")
                        process.terminate()
                        process.wait()
                        break
                    elif status == "close":
                        if not data.get("reconnect"):
                            console.print("[yellow]Session disconnected or logged out.[/yellow]")
                            break
                elif msg_type == "logout_success":
                    console.print("[yellow]Logged out successfully.[/yellow]")
                    break
            except json.JSONDecodeError:
                # Not a JSON line, print it directly to the user's terminal (like the QR code)
                sys.stdout.write(line)
                sys.stdout.flush()
                
        process.wait()
    except KeyboardInterrupt:
        console.print("\n[yellow]Pairing flow cancelled by user.[/yellow]")
        if 'process' in locals():
            process.terminate()
    except Exception as e:
        console.print(f"[red]Error during pairing flow: {e}[/red]")
        raise typer.Exit(1)


@app.command("providers")
def providers(ctx: typer.Context) -> None:
    """List configured LLM providers without showing secrets."""
    cfg: Config = ctx.obj["config"]
    table = Table("ID", "Provider", "Model", "Priority", "Enabled")
    for provider in sorted(cfg.llm.providers, key=lambda item: item.priority):
        table.add_row(
            provider.id,
            provider.provider,
            provider.model,
            str(provider.priority),
            "yes" if provider.enabled else "no",
        )
    console.print(table)


@sessions_app.command("list")
def sessions_list(ctx: typer.Context) -> None:
    """List saved sessions."""
    cfg: Config = ctx.obj["config"]
    from cyberclaw.core.history import HistoryStore

    store = HistoryStore.from_config(cfg)
    table = Table("Session ID", "Agent", "Messages", "Updated", "Title")
    for session in store.list_sessions():
        table.add_row(
            session.id,
            session.agent_id,
            str(session.message_count),
            session.updated_at,
            session.title or "",
        )
    console.print(table)


@sessions_app.command("show")
def sessions_show(
    ctx: typer.Context,
    session_id: Annotated[str, typer.Argument(help="Session ID to inspect.")],
) -> None:
    """Show messages for a saved session."""
    cfg: Config = ctx.obj["config"]
    from cyberclaw.core.history import HistoryStore

    store = HistoryStore.from_config(cfg)
    session = store.get_session_info(session_id)
    if not session:
        console.print(f"[red]Session not found:[/red] {session_id}")
        raise typer.Exit(1)

    console.print(f"[bold]Session:[/bold] {session.id}")
    console.print(f"Agent: {session.agent_id}")
    console.print(f"Source: {session.source}")
    console.print("")
    for message in store.get_messages(session_id):
        console.print(f"[bold]{message.role}[/bold] {message.timestamp}")
        console.print(message.content)
        console.print("")


@gateway_app.command("start")
def gateway_start(ctx: typer.Context) -> None:
    """Start the CyberClaw gateway/server in the foreground."""
    server_command(ctx)


@gateway_app.command("restart")
def gateway_restart(ctx: typer.Context) -> None:
    """Restart-compatible entrypoint for the foreground gateway."""
    console.print(
        "[yellow]CyberClaw has no daemon yet; starting the gateway in the foreground.[/yellow]"
    )
    server_command(ctx)


@gateway_app.command("status")
def gateway_status(ctx: typer.Context) -> None:
    """Show configured gateway endpoint and channel status."""
    cfg: Config = ctx.obj["config"]
    console.print(f"Gateway API: {cfg.api.host}:{cfg.api.port}")
    console.print(f"Channels enabled: {cfg.channels.enabled}")


@gateway_app.command("install-startup")
def gateway_install_startup() -> None:
    """Install a Windows logon startup task for the CyberClaw gateway."""
    script = (
        Path(__file__).resolve().parents[3]
        / "scripts"
        / "install-startup-task.ps1"
    )
    subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
        ],
        check=True,
    )


@gateway_app.command("uninstall-startup")
def gateway_uninstall_startup() -> None:
    """Remove the Windows logon startup task for the CyberClaw gateway."""
    script = (
        Path(__file__).resolve().parents[3]
        / "scripts"
        / "uninstall-startup-task.ps1"
    )
    subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
        ],
        check=True,
    )


@gateway_app.command("tunnel")
def gateway_tunnel(
    ctx: typer.Context,
    provider: Annotated[
        str, typer.Option(help="Tunnel provider: cloudflared or localtunnel")
    ] = "localtunnel",
) -> None:
    """Expose the local running gateway API to the public web."""
    cfg: Config = ctx.obj["config"]
    port = cfg.api.port

    console.print(f"[bold cyan]Exposing gateway API (port {port}) to the web...[/bold cyan]")

    if provider == "cloudflared":
        console.print("Running Cloudflare Tunnel...")
        console.print("[dim]Note: Requires cloudflared installed on system.[/dim]")
        try:
            subprocess.run(["cloudflared", "tunnel", "--url", f"http://127.0.0.1:{port}"])
        except FileNotFoundError:
            console.print("[red]cloudflared is not installed or not in PATH.[/red]")
            console.print("Download from: https://github.com/cloudflare/cloudflared/releases")
    else:
        console.print("Running localtunnel via npx...")
        try:
            subprocess.run(["npx", "-y", "localtunnel", "--port", str(port)])
        except FileNotFoundError:
            console.print("[red]npx is not installed or not in PATH.[/red]")
            console.print("Ensure Node.js is installed.")


app.add_typer(gateway_app, name="gateway")
app.add_typer(config_app, name="config")
app.add_typer(sessions_app, name="sessions")
app.add_typer(pairing_app, name="pairing")
app.add_typer(channels_app, name="channels")


# ── Pairing commands ───────────────────────────────────────────
@pairing_app.command("list")
def pairing_list(ctx: typer.Context) -> None:
    """List pending and approved pairings."""
    cfg: Config = ctx.obj["config"]
    from cyberclaw.security import PairingStore
    store = PairingStore(cfg.workspace / ".pairing")

    pending = store.list_pending()
    approved = store.list_approved()

    if pending:
        console.print("[bold yellow]Pending pairings:[/bold yellow]")
        for p in pending:
            console.print(f"  {p['channel']}:{p['sender_id']} - code: {p['code']}")
    else:
        console.print("No pending pairings.")

    if approved:
        console.print("\n[bold green]Approved pairings:[/bold green]")
        for a in approved:
            console.print(f"  {a['channel']}:{a['sender_id']}")


@pairing_app.command("approve")
def pairing_approve(
    ctx: typer.Context,
    channel: Annotated[str, typer.Argument(help="Channel name (telegram, discord, etc.)")],
    code: Annotated[str, typer.Argument(help="Pairing code to approve")],
) -> None:
    """Approve a pairing code."""
    cfg: Config = ctx.obj["config"]
    from cyberclaw.security import PairingStore
    store = PairingStore(cfg.workspace / ".pairing")
    result = store.approve(channel, code)
    if result:
        console.print(f"[green]Approved sender:[/green] {result}")
    else:
        console.print(f"[red]Pairing code not found:[/red] {code}")
        raise typer.Exit(1)


@pairing_app.command("revoke")
def pairing_revoke(
    ctx: typer.Context,
    channel: Annotated[str, typer.Argument(help="Channel name")],
    sender_id: Annotated[str, typer.Argument(help="Sender ID to revoke")],
) -> None:
    """Revoke an approved pairing."""
    cfg: Config = ctx.obj["config"]
    from cyberclaw.security import PairingStore
    store = PairingStore(cfg.workspace / ".pairing")
    if store.revoke(channel, sender_id):
        console.print(f"[green]Revoked:[/green] {channel}:{sender_id}")
    else:
        console.print(f"[red]Not found:[/red] {channel}:{sender_id}")
        raise typer.Exit(1)


@app.command("tui")
def tui_cmd(ctx: typer.Context) -> None:
    """Start interactive TUI console dashboard."""
    cfg: Config = ctx.obj["config"]
    from cyberclaw.cli.tui import CyberClawTUI
    dashboard = CyberClawTUI(cfg)
    dashboard.start()


@app.command("migrate-openclaw")
def migrate_openclaw_cmd(
    ctx: typer.Context,
    source: Annotated[str, typer.Argument(help="Path to OpenClaw YAML config or SQLite database file")],
) -> None:
    """Migrate settings or chat history from OpenClaw."""
    cfg: Config = ctx.obj["config"]
    from cyberclaw.utils.migrator import OpenClawMigrator
    migrator = OpenClawMigrator(cfg)
    migrator.migrate(Path(source))


# ── Talk command (voice mode) ──────────────────────────────────
@app.command("talk")
def talk(ctx: typer.Context) -> None:
    """Start voice conversation mode (requires voice dependencies)."""
    cfg: Config = ctx.obj["config"]
    if not cfg.tts.enabled:
        console.print("[yellow]TTS not enabled. Set tts.enabled=true in config.user.yaml[/yellow]")
        console.print("Install voice support: pip install cyberclaw[voice]")
        raise typer.Exit(1)

    console.print("[bold cyan]CyberClaw Premium Voice Talk Mode[/bold cyan]")
    console.print(f"Active Provider: [bold green]{cfg.tts.provider or 'edge-tts'}[/bold green] | Voice Style: [bold green]{cfg.tts.voice or 'default'}[/bold green]")
    console.print("Speak/Type to converse. Press Ctrl+C to exit.")

    # Voice conversation loop
    async def voice_loop():
        import re
        import os
        import tempfile
        import subprocess
        from cyberclaw.voice import TTSManager, EdgeTTSProvider, ElevenLabsTTSProvider, SupertonicTTSProvider

        tts = TTSManager()
        
        # 1. Register EdgeTTS
        edge_provider = EdgeTTSProvider()
        tts.register(edge_provider, default=(cfg.tts.provider == "edge-tts"))

        # 2. Register ElevenLabs if configured
        if cfg.tts.api_key:
            el_provider = ElevenLabsTTSProvider(
                api_key=cfg.tts.api_key,
                voice_id=cfg.tts.voice_id or "21m00Tcm4TlvDq8ikWAM"
            )
            tts.register(el_provider, default=(cfg.tts.provider == "elevenlabs"))

        # 3. Register Supertonic
        supertonic_provider = SupertonicTTSProvider(voice=cfg.tts.voice or "M4")
        tts.register(supertonic_provider, default=(cfg.tts.provider == "supertonic"))

        context = SharedContext(cfg, [])
        agent_def = context.agent_loader.load(cfg.default_agent)
        agent = Agent(agent_def, context)
        session = agent.new_session(CliEventSource())

        console.print("[dim]Voice mode ready. Type messages below...[/dim]")

        while True:
            user_input = await asyncio.to_thread(
                lambda: console.input("[cyan]You:[/cyan] ")
            )
            if user_input.lower() in ("quit", "exit", "q"):
                break

            response = await session.chat(user_input)
            console.print(f"[green]CyberClaw:[/green] {response}")

            # Strip expression tags (e.g., [happy], *giggles*) for clean speech synthesis
            clean_speech = re.sub(r"\[.*?\]", "", response)
            clean_speech = re.sub(r"\*.*?\*", "", clean_speech)
            clean_speech = clean_speech.strip()

            if not clean_speech:
                continue

            # Speak the response
            try:
                audio = await tts.speak(clean_speech, provider=cfg.tts.provider, voice=cfg.tts.voice)
                
                # Check if it is a WAV file (starts with b"RIFF") or MP3
                is_wav = audio.startswith(b"RIFF")
                suffix = ".wav" if is_wav else ".mp3"
                
                with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
                    f.write(audio)
                    f.flush()
                    f.close()
                    
                    try:
                        if os.name == "nt":
                            if is_wav:
                                # Standard Windows library play for WAV (synchronous, native)
                                import winsound
                                winsound.PlaySound(f.name, winsound.SND_FILENAME)
                            else:
                                # Play MP3 cleanly via PowerShell MediaPlayer
                                sleep_sec = max(3.0, len(clean_speech) / 12.0)
                                ps_cmd = (
                                    f"Add-Type -AssemblyName PresentationCore; "
                                    f"$p = New-Object System.Windows.Media.MediaPlayer; "
                                    f"$p.Open('{f.name}'); "
                                    f"$p.Play(); "
                                    f"Start-Sleep -Seconds {sleep_sec}"
                                )
                                subprocess.run(
                                    ["powershell", "-c", ps_cmd],
                                    stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL
                                )
                        else:
                            # Unix fallback: play using standard utilities
                            play_cmd = ["aplay"] if is_wav else ["ffplay", "-nodisp", "-autoexit"]
                            subprocess.run(
                                play_cmd + [f.name],
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL
                            )
                    finally:
                        try:
                            os.unlink(f.name)
                        except Exception:
                            pass
            except Exception as e:
                console.print(f"[dim]TTS playback error: {e}[/dim]")

    try:
        asyncio.run(voice_loop())
    except KeyboardInterrupt:
        console.print("\n[bold yellow]Talk mode ended.[/bold yellow]")


# -- Self-update command ------------------------------------------------
@app.command("update")
def update_cmd(
    check: Annotated[
        bool,
        typer.Option("--check", "-c", help="Only check for updates without installing."),
    ] = False,
) -> None:
    """Update CyberClaw to the latest version (or check with --check)."""
    import re

    current_version = "0.2.0"  # synced with pyproject.toml
    repo_url = "https://github.com/CyberPrince-Alien/CyberClaw.git"

    # ── Fetch latest version from git tags ──────────────────────────
    console.print("[bold cyan]Checking for updates...[/bold cyan]")
    latest_version = None
    try:
        result = subprocess.run(
            ["git", "ls-remote", "--tags", repo_url],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0 and result.stdout.strip():
            tags = re.findall(r"refs/tags/v?([\d.]+)", result.stdout)
            if tags:
                # Sort by version tuple
                tags.sort(key=lambda v: tuple(int(x) for x in v.split(".")))
                latest_version = tags[-1]
    except (FileNotFoundError, subprocess.TimeoutExpired):
        console.print("[dim]Could not check remote tags (git not found or network error).[/dim]")

    # ── Display version comparison ──────────────────────────────────
    table = Table(title="CyberClaw Version Check", show_header=True)
    table.add_column("", style="bold")
    table.add_column("Version", style="cyan")
    table.add_row("Installed", f"v{current_version}")
    table.add_row("Latest", f"v{latest_version}" if latest_version else "[dim]unknown[/dim]")

    if latest_version and latest_version != current_version:
        try:
            current_tuple = tuple(int(x) for x in current_version.split("."))
            latest_tuple = tuple(int(x) for x in latest_version.split("."))
            if latest_tuple > current_tuple:
                table.add_row("Status", "[yellow]Update available![/yellow]")
            else:
                table.add_row("Status", "[green]Up to date[/green]")
        except ValueError:
            table.add_row("Status", "[dim]Could not compare[/dim]")
    elif latest_version:
        table.add_row("Status", "[green]Up to date[/green]")
    else:
        table.add_row("Status", "[dim]Could not determine[/dim]")

    console.print(table)

    if check:
        return

    # ── Install update ──────────────────────────────────────────────
    console.print("\n[bold cyan]Installing update...[/bold cyan]")
    try:
        # Try uv first
        result = subprocess.run(
            ["uv", "self", "update"],
            capture_output=True, text=True,
        )
        console.print(result.stdout or "uv is up to date.")

        result2 = subprocess.run(
            ["uv", "sync"],
            capture_output=True, text=True,
            cwd=str(Path(__file__).resolve().parents[3]),
        )
        if result2.returncode == 0:
            console.print("[green]CyberClaw dependencies synced.[/green]")
        else:
            console.print(f"[yellow]Sync warning: {result2.stderr}[/yellow]")

        console.print("[green]Update complete.[/green]")
    except FileNotFoundError:
        # Fallback: pip install from git
        console.print("[dim]uv not found, trying pip...[/dim]")
        try:
            result = subprocess.run(
                ["pip", "install", "--upgrade", f"git+{repo_url}"],
                capture_output=True, text=True,
            )
            if result.returncode == 0:
                console.print("[green]Update complete via pip.[/green]")
            else:
                console.print(f"[red]pip install failed: {result.stderr}[/red]")
                console.print(f"[dim]Try manually: pip install --upgrade git+{repo_url}[/dim]")
        except FileNotFoundError:
            console.print("[red]Neither uv nor pip found. Please install manually.[/red]")
            raise typer.Exit(1)


# -- Service commands ---------------------------------------------------
service_app = typer.Typer(help="Manage CyberClaw as a Windows service")
app.add_typer(service_app, name="service")


@service_app.command("install")
def service_install(ctx: typer.Context) -> None:
    """Install CyberClaw as a Windows background service."""
    cfg: Config = ctx.obj["config"]
    from cyberclaw.utils.service import WindowsServiceManager
    mgr = WindowsServiceManager(cfg.workspace)
    result = mgr.install()
    console.print(f"[green]{result}[/green]")


@service_app.command("uninstall")
def service_uninstall(ctx: typer.Context) -> None:
    """Remove the CyberClaw Windows service."""
    cfg: Config = ctx.obj["config"]
    from cyberclaw.utils.service import WindowsServiceManager
    mgr = WindowsServiceManager(cfg.workspace)
    result = mgr.uninstall()
    console.print(f"[green]{result}[/green]")


@service_app.command("status")
def service_status(ctx: typer.Context) -> None:
    """Check CyberClaw service status."""
    cfg: Config = ctx.obj["config"]
    from cyberclaw.utils.service import WindowsServiceManager
    mgr = WindowsServiceManager(cfg.workspace)
    status = mgr.status()
    console.print(f"Service status: {status}")


# -- Secrets commands ---------------------------------------------------
secrets_app = typer.Typer(help="Manage encrypted API key storage")
app.add_typer(secrets_app, name="secrets")


@secrets_app.command("import")
def secrets_import(ctx: typer.Context) -> None:
    """Import API keys from config.user.yaml into encrypted store."""
    cfg: Config = ctx.obj["config"]
    from cyberclaw.security.secrets_store import SecretsStore
    store = SecretsStore(cfg.workspace / ".secrets" / "vault.json")
    config_path = cfg.workspace / "config.user.yaml"
    import yaml
    data = yaml.safe_load(config_path.read_text()) or {}
    count = store._import_recursive(data)
    console.print(f"[green]Imported {count} secrets into encrypted store.[/green]")


@secrets_app.command("list")
def secrets_list(ctx: typer.Context) -> None:
    """List stored secret keys (values redacted)."""
    cfg: Config = ctx.obj["config"]
    from cyberclaw.security.secrets_store import SecretsStore
    store = SecretsStore(cfg.workspace / ".secrets" / "vault.json")
    keys = store.list_keys()
    if not keys:
        console.print("No secrets stored. Run `cyberclaw secrets import` first.")
        return
    console.print(f"[bold]Stored secrets ({len(keys)}):[/bold]")
    for key in keys:
        console.print(f"  {key}")


@secrets_app.command("set")
def secrets_set(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help="Secret key name")],
    value: Annotated[str, typer.Argument(help="Secret value")],
) -> None:
    """Store a secret."""
    cfg: Config = ctx.obj["config"]
    from cyberclaw.security.secrets_store import SecretsStore
    store = SecretsStore(cfg.workspace / ".secrets" / "vault.json")
    store.set(key, value)
    console.print(f"[green]Secret stored: {key}[/green]")


@secrets_app.command("get")
def secrets_get(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help="Secret key name")],
) -> None:
    """Retrieve a secret."""
    cfg: Config = ctx.obj["config"]
    from cyberclaw.security.secrets_store import SecretsStore
    store = SecretsStore(cfg.workspace / ".secrets" / "vault.json")
    value = store.get(key)
    if value is None:
        console.print(f"[red]Secret not found: {key}[/red]")
        raise typer.Exit(1)
    console.print(value)



# -- Plugins commands ----------------------------------------------------
plugins_app = typer.Typer(help="Manage CyberClaw plugins")
app.add_typer(plugins_app, name="plugins")


@plugins_app.command("list")
def plugins_list(ctx: typer.Context) -> None:
    """List discovered and loaded plugins."""
    cfg: Config = ctx.obj["config"]
    plugins_dir = cfg.workspace / "plugins"
    plugins_dir.mkdir(parents=True, exist_ok=True)

    # Walk directories and load manifests
    import importlib.util
    from cyberclaw.plugins.sdk import Plugin

    table = Table("Name", "Version", "Author", "Capabilities", "Description")
    found_any = False

    for plugin_path in plugins_dir.iterdir():
        if not plugin_path.is_dir():
            continue
        plugin_file = plugin_path / "plugin.py"
        if not plugin_file.exists():
            continue

        try:
            spec = importlib.util.spec_from_file_location(
                f"cyberclaw_plugin_list_{plugin_path.name}",
                str(plugin_file),
            )
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (
                        isinstance(attr, type)
                        and issubclass(attr, Plugin)
                        and attr is not Plugin
                    ):
                        manifest = attr.manifest
                        caps = ", ".join([c.value for c in manifest.capabilities])
                        table.add_row(
                            manifest.name,
                            manifest.version,
                            manifest.author or "Unknown",
                            caps or "None",
                            manifest.description,
                        )
                        found_any = True
                        break
        except Exception as e:
            table.add_row(
                plugin_path.name,
                "[red]Error[/red]",
                "N/A",
                "N/A",
                f"Failed to load: {e}",
            )
            found_any = True

    if not found_any:
        console.print("No plugins found in workspace/plugins/")
        console.print("Run `cyberclaw plugins create <name>` to start building one!")
        return

    console.print("\n[bold cyan]Discovered Plugins:[/bold cyan]")
    console.print(table)


@plugins_app.command("create")
def plugins_create(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="Name of the plugin (snake_case)")],
) -> None:
    """Create a template plugin in workspace/plugins/."""
    cfg: Config = ctx.obj["config"]
    plugin_dir = cfg.workspace / "plugins" / name
    if plugin_dir.exists():
        console.print(f"[red]Plugin directory already exists:[/red] {plugin_dir}")
        raise typer.Exit(1)

    plugin_dir.mkdir(parents=True, exist_ok=True)
    plugin_file = plugin_dir / "plugin.py"

    # Template plugin code
    template_code = f'''"""Template plugin generated by CyberClaw."""

from typing import Any
from cyberclaw.plugins.sdk import Plugin, PluginManifest, PluginCapability


class MyCustomPlugin(Plugin):
    """Custom extension plugin for CyberClaw."""

    manifest = PluginManifest(
        name="{name}",
        version="0.1.0",
        description="Auto-generated template plugin",
        author="Cyber Prince Developer",
        capabilities=[PluginCapability.TOOL, PluginCapability.CHANNEL],
    )

    async def on_load(self) -> None:
        """Executed when the plugin is registered."""
        print(f"[Plugin {name}] load completed successfully!")

    async def on_unload(self) -> None:
        """Executed during cleanup."""
        print(f"[Plugin {name}] unload completed.")

    def get_tools(self) -> list[dict[str, Any]]:
        """Add custom tools here."""
        return [
            {{
                "name": "{name}_ping",
                "description": "Example plugin tool that returns pong",
                "parameters": {{"type": "object", "properties": {{}}}},
            }}
        ]
'''
    plugin_file.write_text(template_code)
    console.print(f"[green]Successfully created plugin template:[/green] {plugin_dir}")
    console.print(f"Edit [cyan]{plugin_file}[/cyan] to build your custom tools and channels.")


@plugins_app.command("install")
def plugins_install(
    ctx: typer.Context,
    source: Annotated[str, typer.Argument(help="Git URL or local directory path to copy")],
) -> None:
    """Install a plugin from a Git repository or local folder."""
    cfg: Config = ctx.obj["config"]
    plugins_dir = cfg.workspace / "plugins"
    plugins_dir.mkdir(parents=True, exist_ok=True)

    is_git = source.startswith("http://") or source.startswith("https://") or source.startswith("git@")

    if is_git:
        # Clone using git CLI
        plugin_name = source.split("/")[-1].replace(".git", "")
        target_dir = plugins_dir / plugin_name
        if target_dir.exists():
            console.print(f"[red]Target plugin directory already exists:[/red] {target_dir}")
            raise typer.Exit(1)

        console.print(f"Cloning plugin from [cyan]{source}[/cyan]...")
        try:
            result = subprocess.run(
                ["git", "clone", source, str(target_dir)],
                capture_output=True, text=True, check=True
            )
            console.print(f"[green]Plugin installed successfully via Git to {target_dir}[/green]")
        except Exception as e:
            console.print(f"[red]Git clone failed:[/red] {e}")
            raise typer.Exit(1)
    else:
        # Local copy
        src_path = Path(source).resolve()
        if not src_path.exists() or not src_path.is_dir():
            console.print(f"[red]Local source path is not a directory or does not exist:[/red] {source}")
            raise typer.Exit(1)

        target_dir = plugins_dir / src_path.name
        if target_dir.exists():
            console.print(f"[red]Target plugin directory already exists:[/red] {target_dir}")
            raise typer.Exit(1)

        console.print(f"Copying plugin from [cyan]{src_path}[/cyan]...")
        import shutil
        try:
            shutil.copytree(src_path, target_dir)
            console.print(f"[green]Plugin installed successfully to {target_dir}[/green]")
        except Exception as e:
            console.print(f"[red]Copy failed:[/red] {e}")
            raise typer.Exit(1)


# -- Migrate history command --------------------------------------------
@app.command("migrate-history")
def migrate_history(ctx: typer.Context) -> None:
    """Migrate conversation history from JSONL to SQLite."""
    cfg: Config = ctx.obj["config"]
    from cyberclaw.core.history import HistoryStore
    from cyberclaw.core.history_sqlite import SQLiteHistoryStore

    jsonl_store = HistoryStore.from_config(cfg)
    sqlite_store = SQLiteHistoryStore.from_config(cfg)

    sessions = jsonl_store.list_sessions()
    console.print(f"Found {len(sessions)} sessions in JSONL store.")

    count = sqlite_store.migrate_from_jsonl(jsonl_store)
    console.print(f"[green]Migrated {count} sessions to SQLite.[/green]")
    sqlite_store.close()


# -- Coding Workspace Command ------------------------------------------
@app.command("code")
def code_command(
    ctx: typer.Context,
    dev: Annotated[
        bool,
        typer.Option(
            "--dev",
            help="Run launcher in dev mode using TS files",
        ),
    ] = True,
    path: Annotated[
        str,
        typer.Option(
            "--path",
            help="Path to free-code-main workspace",
        ),
    ] = r"C:\Users\Sourov\Desktop\free-code-main",
) -> None:
    """Launch the Cyber Prince V9 Agentic Coding Workspace (Claude Code Engine)."""
    import os
    import subprocess
    from pathlib import Path
    from cyberclaw.security.secrets_store import SecretsStore

    free_code_dir = Path(path)
    if not free_code_dir.exists():
        console.print(f"[red]Error: free-code-main directory not found at {free_code_dir}[/red]")
        raise typer.Exit(1)

    cfg = ctx.obj.get("config")
    env = os.environ.copy()
    
    if cfg:
        vault_path = cfg.workspace / ".secrets" / "vault.json"
        if vault_path.exists():
            try:
                store = SecretsStore(vault_path)
                key_mapping = {
                    "anthropic.api_key": "ANTHROPIC_API_KEY",
                    "openai.api_key": "OPENAI_API_KEY",
                    "gemini.api_key": "GEMINI_API_KEY",
                    "tavily.api_key": "TAVILY_API_KEY",
                    "brave.api_key": "BRAVE_API_KEY",
                    "groq.api_key": "GROQ_API_KEY",
                    "openrouter.api_key": "OPENROUTER_API_KEY",
                    "deepseek.api_key": "DEEPSEEK_API_KEY",
                }
                for vault_key, env_var in key_mapping.items():
                    val = store.get(vault_key)
                    if val:
                        env[env_var] = val
            except Exception as e:
                console.print(f"[yellow]Warning: Could not load keys from vault: {e}[/yellow]")

    console.print(f"[bold green]Starting Cyber Prince CLI V9 (Claude Code Workspace)...[/bold green]")
    console.print(f"Directory: [cyan]{free_code_dir}[/cyan]")
    
    # Run bun run launch-v9-simple.ts
    cmd = ["bun", "run", "launch-v9-simple.ts"]
    try:
        subprocess.run(cmd, cwd=free_code_dir, env=env, check=True)
    except subprocess.CalledProcessError as e:
        console.print(f"[red]CLI process exited with error code {e.returncode}[/red]")
        raise typer.Exit(e.returncode)
    except KeyboardInterrupt:
        console.print("\n[yellow]CLI workspace closed by user.[/yellow]")


if __name__ == "__main__":
    app()
