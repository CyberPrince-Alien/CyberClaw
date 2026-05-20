"""IRC channel integration."""

import asyncio
import logging
from typing import Callable, Awaitable, Any

from cyberclaw.channel.base import Channel
from cyberclaw.core.events import EventSource

logger = logging.getLogger(__name__)


class IRCEventSource(EventSource):
    _namespace = "platform-irc"

    def __init__(self, nick: str, channel_name: str):
        self.nick = nick
        self.channel_name = channel_name

    def __str__(self) -> str:
        return f"platform-irc:{self.channel_name}:{self.nick}"

    @classmethod
    def from_string(cls, s: str) -> "IRCEventSource":
        parts = s.split(":", 2)
        channel_name = parts[1] if len(parts) > 1 else ""
        nick = parts[2] if len(parts) > 2 else ""
        return cls(nick=nick, channel_name=channel_name)


class IRCChannel(Channel["IRCEventSource"]):
    """IRC channel using asyncio raw sockets."""

    def __init__(self, config: Any):
        self.config = config
        self.server: str = getattr(config, "server", "")
        self.port: int = getattr(config, "port", 6667)
        self.nick: str = getattr(config, "nick", "CyberClaw")
        self.channels_list: list[str] = getattr(config, "channels", [])
        self.use_ssl: bool = getattr(config, "use_ssl", False)
        self.allow_from: list[str] = getattr(config, "allow_from", [])
        self._writer: asyncio.StreamWriter | None = None
        self._stop_event = asyncio.Event()

    @property
    def platform_name(self) -> str:
        return "irc"

    def is_allowed(self, source: IRCEventSource) -> bool:
        if "*" in self.allow_from:
            return True
        return source.nick in self.allow_from

    async def run(self, on_message: Callable[[str, IRCEventSource], Awaitable[None]]) -> None:
        if self.use_ssl:
            import ssl as ssl_mod
            ssl_ctx = ssl_mod.create_default_context()
            reader, writer = await asyncio.open_connection(self.server, self.port, ssl=ssl_ctx)
        else:
            reader, writer = await asyncio.open_connection(self.server, self.port)

        self._writer = writer

        # Register
        writer.write(f"NICK {self.nick}\r\n".encode())
        writer.write(f"USER {self.nick} 0 * :CyberClaw Bot\r\n".encode())
        await writer.drain()

        # Join channels
        for ch in self.channels_list:
            writer.write(f"JOIN {ch}\r\n".encode())
        await writer.drain()

        logger.info("IRC connected to %s:%d as %s", self.server, self.port, self.nick)

        try:
            while not self._stop_event.is_set():
                try:
                    line_bytes = await asyncio.wait_for(reader.readline(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue

                if not line_bytes:
                    break

                line = line_bytes.decode("utf-8", errors="replace").strip()

                # Handle PING
                if line.startswith("PING"):
                    pong = line.replace("PING", "PONG", 1)
                    writer.write(f"{pong}\r\n".encode())
                    await writer.drain()
                    continue

                # Parse PRIVMSG
                if "PRIVMSG" in line:
                    try:
                        prefix = line.split("!")[0].lstrip(":")
                        parts = line.split("PRIVMSG", 1)[1].strip().split(" :", 1)
                        channel_name = parts[0].strip()
                        text = parts[1] if len(parts) > 1 else ""
                        source = IRCEventSource(nick=prefix, channel_name=channel_name)
                        if text and self.is_allowed(source):
                            await on_message(text, source)
                    except (IndexError, ValueError):
                        pass
        finally:
            writer.close()

    async def reply(self, content: str, source: IRCEventSource) -> None:
        if self._writer:
            for line in content.split("\n"):
                msg = f"PRIVMSG {source.channel_name} :{line}\r\n"
                self._writer.write(msg.encode())
            await self._writer.drain()

    async def stop(self) -> None:
        self._stop_event.set()
        if self._writer:
            self._writer.close()
