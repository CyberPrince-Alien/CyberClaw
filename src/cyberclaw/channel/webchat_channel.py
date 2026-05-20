"""Built-in WebChat channel served by the gateway."""

import asyncio
import json
import logging
from typing import Callable, Awaitable, Any

from cyberclaw.channel.base import Channel
from cyberclaw.core.events import EventSource

logger = logging.getLogger(__name__)


class WebChatEventSource(EventSource):
    """Source for web chat widget events."""
    _namespace = "platform-webchat"

    def __init__(self, session_token: str):
        self.session_token = session_token

    def __str__(self) -> str:
        return f"platform-webchat:{self.session_token}"

    @classmethod
    def from_string(cls, s: str) -> "WebChatEventSource":
        parts = s.split(":", 1)
        return cls(session_token=parts[1] if len(parts) > 1 else "")


class WebChatChannel(Channel["WebChatEventSource"]):
    """WebChat channel — messages arrive via the gateway WebSocket or API."""

    def __init__(self):
        self._stop_event = asyncio.Event()
        self._on_message = None

    @property
    def platform_name(self) -> str:
        return "webchat"

    def is_allowed(self, source: WebChatEventSource) -> bool:
        return True  # WebChat is local, always allowed

    async def run(self, on_message: Callable[[str, WebChatEventSource], Awaitable[None]]) -> None:
        self._on_message = on_message
        logger.info("WebChat channel ready (messages via /chat API or WebSocket)")
        await self._stop_event.wait()

    async def handle_message(self, text: str, session_token: str) -> None:
        """Called by the gateway when a webchat message arrives."""
        if self._on_message:
            source = WebChatEventSource(session_token=session_token)
            await self._on_message(text, source)

    async def reply(self, content: str, source: WebChatEventSource) -> None:
        # Replies are delivered via WebSocket push or SSE — handled at gateway level
        pass

    async def stop(self) -> None:
        self._stop_event.set()
