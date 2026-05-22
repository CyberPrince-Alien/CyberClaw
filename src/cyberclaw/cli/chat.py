"""Chat CLI command for interactive sessions with event-driven architecture."""

import asyncio
import warnings

import litellm
# Suppress LiteLLM helper warnings and feedback banner
litellm.suppress_helper_warnings = True
litellm.suppress_debug_info = True

# Suppress Pydantic serialization UserWarnings
warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.text import Text

from cyberclaw.core.agent import Agent
from cyberclaw.core.context import SharedContext
from cyberclaw.core.events import (
    OutboundEvent,
    InboundEvent,
    CliEventSource,
)
from cyberclaw.server import (
    AgentWorker,
    Worker,
)
from cyberclaw.utils.config import Config, ConfigReloader
from cyberclaw.utils.logging import setup_logging


class ChatLoop:
    """Interactive chat session using event-driven architecture."""

    def __init__(self, config: Config, agent_id: str | None = None):
        self.config = config
        self.console = Console()
        self.context = SharedContext(config=config, channels=[])
        self.config_reloader = ConfigReloader(config)

        self.workers: list[Worker] = [
            self.context.eventbus,
            AgentWorker(self.context),
        ]

        self.response_queue: asyncio.Queue[OutboundEvent] = asyncio.Queue()
        self.context.eventbus.subscribe(OutboundEvent, self.handle_outbound_event)

        agent_id = agent_id or config.default_agent
        self.agent_def = self.context.agent_loader.load(agent_id)

    async def handle_outbound_event(self, event: OutboundEvent) -> None:
        """Handle outbound events by adding to response queue."""
        await self.response_queue.put(event)
        self.context.eventbus.ack(event)

    def get_user_input(self) -> str:
        """Get user input with styled prompt."""
        prompt_text = Text("You", style="cyan")
        user_input = Prompt.ask(prompt_text, console=self.console)
        return user_input.strip()

    def display_agent_response(self, content: str) -> None:
        """Display agent response with styled prefix."""
        prefix = Text(f"{self.agent_def.id}: ", style="green")

        self.console.print(prefix, end="")
        self.console.print(content)

    async def run(self) -> None:
        """Run the interactive chat loop."""
        model_name = "Unknown Model"
        if self.agent_def.llm.model:
            model_name = self.agent_def.llm.model
        elif self.agent_def.llm.providers:
            enabled_providers = [p for p in self.agent_def.llm.providers if p.enabled]
            if enabled_providers:
                model_name = enabled_providers[0].model

        logo = """[bold cyan]  ═══════════════════════════════════════════════════════════════════════════════[/bold cyan]

[bold magenta]   ██████╗██╗   ██╗██████╗ ███████╗██████╗  ██████╗██╗      █████╗ ██╗    ██╗[/bold magenta]
[bold magenta]  ██╔════╝╚██╗ ██╔╝██╔══██╗██╔════╝██╔══██╗██╔════╝██║     ██╔══██╗██║    ██║[/bold magenta]
[bold magenta]  ██║      ╚████╔╝ ██████╔╝█████╗  ██████╔╝██║     ██║     ███████║██║ █╗ ██║[/bold magenta]
[bold magenta]  ██║       ╚██╔╝  ██╔══██╗██╔══╝  ██╔══██╗██║     ██║     ██╔══██║██║███╗██║[/bold magenta]
[bold magenta]  ╚██████╗   ██║   ██████╔╝███████╗██║  ██║╚██████╗███████╗██║  ██║╚███╔███╔╝[/bold magenta]
[bold magenta]   ╚═════╝   ╚═╝   ╚═════╝ ╚══════╝╚═╝  ╚═╝ ╚═════╝╚══════╝╚═╝  ╚═╝ ╚══╝╚══╝[/bold magenta]

[bold cyan]  ═══════════════════════════════════════════════════════════════════════════════[/bold cyan]

                           [bold green]█ READY — CyberClaw AI Online With {model_name}[/bold green]
"""
        self.console.print(logo.format(model_name=model_name))
        self.console.print("Type '/help' for commands, 'quit' or 'exit' to end.\n")

        self.config_reloader.start()

        for worker in self.workers:
            worker.start()

        # Discover and load plugins
        plugins_dir = self.context.config.workspace / "plugins"
        try:
            await self.context.plugin_registry.discover_and_load(plugins_dir)
        except Exception as e:
            self.console.print(f"[red]Failed to discover and load plugins: {e}[/red]")

        session_id = (
            Agent(self.agent_def, self.context).new_session(CliEventSource()).session_id
        )

        try:
            while True:
                user_input = await asyncio.to_thread(self.get_user_input)
                if user_input.lower() in ("quit", "exit", "q"):
                    self.console.print("\n[bold yellow]Goodbye![/bold yellow]")
                    break

                if not user_input:
                    continue

                event = InboundEvent(
                    session_id=session_id,
                    source=CliEventSource(),
                    content=user_input,
                )
                await self.context.eventbus.publish(event)

                try:
                    response = await asyncio.wait_for(
                        self.response_queue.get(), timeout=60.0
                    )

                    self.display_agent_response(response.content)
                except asyncio.TimeoutError:
                    self.console.print("[red]Agent response timed out[/red]")
                    self.console.print()

        except (KeyboardInterrupt, EOFError):
            self.console.print("\n[bold yellow]Goodbye![/bold yellow]")
        finally:
            for worker in self.workers:
                await worker.stop()
            self.config_reloader.stop()


def chat_command(ctx: typer.Context, agent_id: str | None = None) -> None:
    """Start interactive chat session."""
    config = ctx.obj.get("config")
    setup_logging(config, console_output=False)

    chat_loop = ChatLoop(config, agent_id=agent_id)
    asyncio.run(chat_loop.run())
