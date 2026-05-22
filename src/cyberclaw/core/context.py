from typing import Any, TYPE_CHECKING

from cyberclaw.core.agent_loader import AgentLoader
from cyberclaw.core.commands.registry import CommandRegistry
from cyberclaw.core.cron_loader import CronLoader
from cyberclaw.core.history import HistoryStore
from cyberclaw.core.prompt_builder import PromptBuilder
from cyberclaw.core.routing import RoutingTable
from cyberclaw.core.eventbus import EventBus
from cyberclaw.channel.base import Channel
from cyberclaw.plugins.registry import PluginRegistry
from cyberclaw.security import PairingStore
from cyberclaw.utils.config import Config

if TYPE_CHECKING:
    from cyberclaw.server.websocket_worker import WebSocketWorker
    from cyberclaw.core.skill_loader import SkillLoader


class SharedContext:
    """Global shared state for the application."""

    config: Config
    history_store: HistoryStore
    agent_loader: AgentLoader
    skill_loader: "SkillLoader"
    cron_loader: CronLoader
    command_registry: CommandRegistry
    routing_table: RoutingTable
    prompt_builder: PromptBuilder
    channels: list[Channel[Any]]
    eventbus: EventBus
    websocket_worker: "WebSocketWorker | None"
    plugin_registry: PluginRegistry
    pairing_store: PairingStore

    def __init__(
        self, config: Config, channels: list[Channel[Any]] | None = None
    ) -> None:
        from cyberclaw.core.skill_loader import SkillLoader

        self.config = config
        self.history_store = HistoryStore.from_config(config)
        self.agent_loader = AgentLoader.from_config(config)
        self.skill_loader = SkillLoader.from_config(config)
        self.cron_loader = CronLoader.from_config(config)
        self.command_registry = CommandRegistry.with_builtins()
        self.routing_table = RoutingTable(self)
        self.prompt_builder = PromptBuilder(self)

        if channels is not None:
            self.channels = channels
        else:
            self.channels = Channel.from_config(config)

        self.eventbus = EventBus(self)
        self.websocket_worker = None
        self.plugin_registry = PluginRegistry(self)
        self.pairing_store = PairingStore(config.workspace / ".pairing")
        
        # MCP server connection caching
        self._mcp_clients = {}
        self._mcp_initialized_servers = set()
        self._mcp_failed_servers = set()
