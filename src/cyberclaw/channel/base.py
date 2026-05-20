"""Abstract base class for channel implementations."""

from abc import ABC, abstractmethod
from typing import Callable, Awaitable, Generic, TypeVar, Any

from cyberclaw.core.events import EventSource
from cyberclaw.utils.config import Config


T = TypeVar("T", bound=EventSource)


class Channel(ABC, Generic[T]):
    """Abstract base for messaging platforms with EventSource-based context."""

    @property
    @abstractmethod
    def platform_name(self) -> str:
        """Platform identifier."""
        pass

    @abstractmethod
    async def run(self, on_message: Callable[[str, T], Awaitable[None]]) -> None:
        """Run the channel. Blocks until stop() is called."""
        pass

    @abstractmethod
    def is_allowed(self, source: T) -> bool:
        """Check if sender is whitelisted."""
        pass

    @abstractmethod
    async def reply(self, content: str, source: T) -> None:
        """Reply to incoming message."""
        pass

    @abstractmethod
    async def stop(self) -> None:
        """Stop listening and cleanup resources."""
        pass

    @staticmethod
    def from_config(config: Config) -> list["Channel[Any]"]:
        """Create channel instances from configuration."""
        # Inline imports to avoid circular dependency
        from cyberclaw.channel.telegram_channel import TelegramChannel
        from cyberclaw.channel.discord_channel import DiscordChannel
        from cyberclaw.channel.slack_channel import SlackChannel
        from cyberclaw.channel.whatsapp_channel import WhatsAppChannel
        from cyberclaw.channel.matrix_channel import MatrixChannel
        from cyberclaw.channel.irc_channel import IRCChannel
        from cyberclaw.channel.webchat_channel import WebChatChannel

        channels: list["Channel[Any]"] = []
        channel_config = config.channels
        if channel_config.telegram and channel_config.telegram.enabled:
            channels.append(TelegramChannel(channel_config.telegram))

        if channel_config.discord and channel_config.discord.enabled:
            channels.append(DiscordChannel(channel_config.discord))

        if channel_config.slack and channel_config.slack.enabled:
            channels.append(SlackChannel(channel_config.slack))

        if channel_config.whatsapp and channel_config.whatsapp.enabled:
            channels.append(WhatsAppChannel(channel_config.whatsapp))

        if channel_config.matrix and channel_config.matrix.enabled:
            channels.append(MatrixChannel(channel_config.matrix))

        if channel_config.irc and channel_config.irc.enabled:
            channels.append(IRCChannel(channel_config.irc))

        if channel_config.webchat and channel_config.webchat.enabled:
            channels.append(WebChatChannel())

        if channel_config.signal and channel_config.signal.enabled:
            from cyberclaw.channel.signal_channel import SignalChannel
            channels.append(SignalChannel(channel_config.signal))

        return channels
