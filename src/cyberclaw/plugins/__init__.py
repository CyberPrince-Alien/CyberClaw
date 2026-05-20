"""CyberClaw plugin system."""

from .sdk import Plugin, PluginManifest, PluginCapability
from .registry import PluginRegistry

__all__ = ["Plugin", "PluginManifest", "PluginCapability", "PluginRegistry"]
