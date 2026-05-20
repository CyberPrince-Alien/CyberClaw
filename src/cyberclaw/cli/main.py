"""CLI interface for cyberclaw using Typer."""

from pathlib import Path
import asyncio
import subprocess
from typing import Annotated

import yaml
import typer
from rich.console import Console
from rich.table import Table

from cyberclaw.cli.chat import chat_command
from cyberclaw.cli.server import server_command
from cyberclaw.core.agent import Agent
from cyberclaw.core.context import SharedContext
from cyberclaw.core.events import CliEventSource
from cyberclaw.utils.config import Config
from cyberclaw.utils.logging import setup_logging

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

console = Console()


def workspace_callback(ctx: typer.Context, workspace: str) -> Path:
    """Store workspace path in context for later use."""
    ctx.ensure_object(dict)
    ctx.obj["workspace"] = Path(workspace)
    return Path(workspace)


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
        console.print("Run `cyberclaw onboard` to create a local workspace config.")
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
    workspace_path.mkdir(parents=True, exist_ok=True)

    for directory in ("agents", "skills", "crons", "memories"):
        (workspace_path / directory).mkdir(exist_ok=True)

    config_path = workspace_path / "config.user.yaml"
    example_path = workspace_path / "config.example.yaml"
    if not config_path.exists() and example_path.exists():
        config_path.write_text(example_path.read_text())

    console.print(f"[green]CyberClaw workspace ready:[/green] {workspace_path}")
    console.print(f"Config: {config_path}")
    if install_daemon:
        console.print(
            "[yellow]Daemon install is not implemented yet; use `cyberclaw gateway start`.[/yellow]"
        )


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
def doctor(ctx: typer.Context) -> None:
    """Check common setup and security issues."""
    cfg: Config = ctx.obj["config"]
    issues: list[str] = []

    enabled_providers = [provider for provider in cfg.llm.providers if provider.enabled]
    if not enabled_providers:
        issues.append("No enabled LLM providers.")

    for provider in enabled_providers:
        placeholder_markers = ("your-", "sk-your", "api-key-here")
        if any(marker in provider.api_key for marker in placeholder_markers):
            issues.append(f"Provider `{provider.id}` appears to use a placeholder API key.")

    if cfg.channels.enabled:
        channel_names = ["telegram", "discord", "slack", "whatsapp", "matrix", "irc"]
        for name in channel_names:
            channel = getattr(cfg.channels, name, None)
            if channel and getattr(channel, "enabled", False):
                policy = getattr(channel, "dm_policy", None)
                allow = getattr(channel, "allow_from", [])
                if policy == "open" and "*" in allow:
                    issues.append(f"{name} accepts all senders; use pairing unless this is intentional.")

    # Check for exposed API keys
    for provider in enabled_providers:
        key = provider.api_key
        if len(key) > 8 and not any(m in key for m in ("your-", "api-key-here")):
            # Real key present, warn about plain text
            pass  # Will be fixed when encrypted secrets are enabled

    if issues:
        console.print("[yellow]CyberClaw doctor found issues:[/yellow]")
        for issue in issues:
            console.print(f"  [!] {issue}")
        raise typer.Exit(1)

    console.print("[green]OK - CyberClaw doctor found no blocking issues.[/green]")


@app.command("channels")
def channels(ctx: typer.Context) -> None:
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


app.add_typer(gateway_app, name="gateway")
app.add_typer(config_app, name="config")
app.add_typer(sessions_app, name="sessions")
app.add_typer(pairing_app, name="pairing")


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


# ── Talk command (voice mode) ──────────────────────────────────
@app.command("talk")
def talk(ctx: typer.Context) -> None:
    """Start voice conversation mode (requires voice dependencies)."""
    cfg: Config = ctx.obj["config"]
    if not cfg.tts.enabled:
        console.print("[yellow]TTS not enabled. Set tts.enabled=true in config.user.yaml[/yellow]")
        console.print("Install voice support: pip install cyberclaw[voice]")
        raise typer.Exit(1)

    console.print("[bold cyan]CyberClaw Talk Mode[/bold cyan]")
    console.print("Speak into your microphone. Press Ctrl+C to stop.")
    console.print("[yellow]Note: Requires edge-tts and a microphone.[/yellow]")

    # Voice conversation loop
    async def voice_loop():
        from cyberclaw.voice import TTSManager, EdgeTTSProvider
        tts = TTSManager()
        tts.register(EdgeTTSProvider(), default=True)

        context = SharedContext(cfg, [])
        agent_def = context.agent_loader.load(cfg.default_agent)
        agent = Agent(agent_def, context)
        session = agent.new_session(CliEventSource())

        console.print("[dim]Voice mode ready. Type messages (voice input requires STT setup).[/dim]")

        while True:
            user_input = await asyncio.to_thread(
                lambda: console.input("[cyan]You:[/cyan] ")
            )
            if user_input.lower() in ("quit", "exit", "q"):
                break

            response = await session.chat(user_input)
            console.print(f"[green]CyberClaw:[/green] {response}")

            # Speak the response
            try:
                audio = await tts.speak(response, voice=cfg.tts.voice)
                # Play audio (platform-dependent)
                import tempfile, subprocess
                with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                    f.write(audio)
                    f.flush()
                    # Windows: use default player
                    subprocess.Popen(
                        ["powershell", "-c", f"(New-Object Media.SoundPlayer '{f.name}').PlaySync()"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    )
            except Exception as e:
                console.print(f"[dim]TTS playback error: {e}[/dim]")

    try:
        asyncio.run(voice_loop())
    except KeyboardInterrupt:
        console.print("\n[bold yellow]Talk mode ended.[/bold yellow]")


# -- Self-update command ------------------------------------------------
@app.command("update")
def update_cmd() -> None:
    """Update CyberClaw to the latest version."""
    console.print("[bold cyan]Checking for updates...[/bold cyan]")
    try:
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
        console.print("[red]uv not found. Install uv first: https://docs.astral.sh/uv/[/red]")
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


if __name__ == "__main__":
    app()
