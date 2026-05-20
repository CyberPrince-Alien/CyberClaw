"""Plugin registry — discovery, loading, and lifecycle management."""

import importlib
import logging
from pathlib import Path
from typing import Any, TYPE_CHECKING

from cyberclaw.plugins.sdk import Plugin, PluginManifest

if TYPE_CHECKING:
    from cyberclaw.core.context import SharedContext

logger = logging.getLogger(__name__)


class PluginRegistry:
    """Discovers, loads, and manages plugin lifecycle."""

    def __init__(self, context: "SharedContext"):
        self.context = context
        self._plugins: dict[str, Plugin] = {}

    @property
    def loaded(self) -> list[str]:
        return list(self._plugins.keys())

    def get(self, name: str) -> Plugin | None:
        return self._plugins.get(name)

    async def load_plugin(self, plugin_cls: type[Plugin], config: dict[str, Any] | None = None) -> None:
        """Instantiate and load a plugin class."""
        plugin = plugin_cls(self.context, config)
        name = plugin.manifest.name
        if name in self._plugins:
            logger.warning("Plugin %s already loaded, skipping", name)
            return

        try:
            await plugin.on_load()
            self._plugins[name] = plugin
            logger.info("Loaded plugin: %s v%s", name, plugin.manifest.version)
        except Exception as e:
            logger.error("Failed to load plugin %s: %s", name, e)

    async def unload_plugin(self, name: str) -> None:
        """Unload a plugin by name."""
        plugin = self._plugins.pop(name, None)
        if plugin:
            try:
                await plugin.on_unload()
                logger.info("Unloaded plugin: %s", name)
            except Exception as e:
                logger.error("Error unloading plugin %s: %s", name, e)

    async def unload_all(self) -> None:
        """Unload all plugins."""
        for name in list(self._plugins.keys()):
            await self.unload_plugin(name)

    async def discover_and_load(self, plugins_dir: Path) -> int:
        """Discover plugins from a directory and load them.
        
        Each plugin should be a Python package with a plugin.py containing
        a class that extends Plugin.
        """
        count = 0
        if not plugins_dir.exists():
            return 0

        for plugin_path in plugins_dir.iterdir():
            if not plugin_path.is_dir():
                continue
            plugin_file = plugin_path / "plugin.py"
            if not plugin_file.exists():
                continue

            try:
                # Import the module
                spec = importlib.util.spec_from_file_location(
                    f"cyberclaw_plugin_{plugin_path.name}",
                    str(plugin_file),
                )
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)

                    # Find Plugin subclass
                    for attr_name in dir(module):
                        attr = getattr(module, attr_name)
                        if (
                            isinstance(attr, type)
                            and issubclass(attr, Plugin)
                            and attr is not Plugin
                        ):
                            await self.load_plugin(attr)
                            count += 1
                            break
            except Exception as e:
                logger.error("Failed to discover plugin from %s: %s", plugin_path, e)

        return count

    async def notify_config_change(self) -> None:
        """Notify all plugins of a config change."""
        for name, plugin in self._plugins.items():
            try:
                await plugin.on_config_change(self.context.config)
            except Exception as e:
                logger.error("Plugin %s config change error: %s", name, e)

    def get_all_tools(self) -> list[dict[str, Any]]:
        """Collect tools from all loaded plugins."""
        tools = []
        for plugin in self._plugins.values():
            tools.extend(plugin.get_tools())
        return tools

    def get_all_channels(self) -> list[Any]:
        """Collect channels from all loaded plugins."""
        channels = []
        for plugin in self._plugins.values():
            channels.extend(plugin.get_channels())
        return channels
