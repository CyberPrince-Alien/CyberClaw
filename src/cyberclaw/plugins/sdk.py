"""Plugin SDK for CyberClaw extensions."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from cyberclaw.core.context import SharedContext
    from cyberclaw.utils.config import Config


class PluginCapability(str, Enum):
    """What a plugin provides."""
    CHANNEL = "channel"
    TOOL = "tool"
    PROVIDER = "provider"
    SKILL = "skill"
    TTS = "tts"
    STT = "stt"
    MEDIA = "media"


@dataclass
class PluginManifest:
    """Plugin metadata."""
    name: str
    version: str
    description: str
    author: str = ""
    capabilities: list[PluginCapability] = field(default_factory=list)
    config_schema: dict[str, Any] = field(default_factory=dict)
    dependencies: list[str] = field(default_factory=list)


class Plugin(ABC):
    """Base class for all CyberClaw plugins."""

    manifest: PluginManifest

    def __init__(self, context: "SharedContext", plugin_config: dict[str, Any] | None = None):
        self.context = context
        self.plugin_config = plugin_config or {}

    @abstractmethod
    async def on_load(self) -> None:
        """Called when the plugin is loaded. Register tools/channels/etc here."""
        ...

    async def on_unload(self) -> None:
        """Called when the plugin is unloaded. Cleanup resources here."""
        pass

    async def on_config_change(self, config: "Config") -> None:
        """Called when the main config changes (hot reload)."""
        pass

    def get_tools(self) -> list[dict[str, Any]]:
        """Return tool definitions this plugin provides. Override in subclass."""
        return []

    def get_channels(self) -> list[Any]:
        """Return channel instances this plugin provides. Override in subclass."""
        return []
