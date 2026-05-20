"""Slack channel integration using slack-sdk."""

import asyncio
import logging
from typing import Callable, Awaitable, Any

from cyberclaw.channel.base import Channel
from cyberclaw.core.events import EventSource

logger = logging.getLogger(__name__)


class SlackEventSource(EventSource):
    """Source for Slack-originated events."""
    _namespace = "platform-slack"

    def __init__(self, user_id: str, channel_id: str, thread_ts: str | None = None):
        self.user_id = user_id
        self.channel_id = channel_id
        self.thread_ts = thread_ts

    def __str__(self) -> str:
        return f"platform-slack:{self.channel_id}:{self.user_id}"

    @classmethod
    def from_string(cls, s: str) -> "SlackEventSource":
        parts = s.split(":", 2)
        channel_id = parts[1] if len(parts) > 1 else ""
        user_id = parts[2] if len(parts) > 2 else ""
        return cls(user_id=user_id, channel_id=channel_id)


class SlackChannel(Channel["SlackEventSource"]):
    """Slack Bot integration via Socket Mode."""

    def __init__(self, config: Any):
        self.config = config
        self.bot_token: str = config.bot_token
        self.app_token: str = getattr(config, "app_token", "")
        self.allowed_channels: list[str] = getattr(config, "allowed_channels", [])
        self.dm_policy: str = getattr(config, "dm_policy", "pairing")
        self.allow_from: list[str] = getattr(config, "allow_from", [])
        self._handler = None
        self._stop_event = asyncio.Event()

    @property
    def platform_name(self) -> str:
        return "slack"

    def is_allowed(self, source: SlackEventSource) -> bool:
        if "*" in self.allow_from:
            return True
        return source.user_id in self.allow_from

    async def run(self, on_message: Callable[[str, SlackEventSource], Awaitable[None]]) -> None:
        """Run Slack Socket Mode listener."""
        try:
            from slack_sdk.web.async_client import AsyncWebClient
            from slack_sdk.socket_mode.aiohttp import SocketModeClient
            from slack_sdk.socket_mode.request import SocketModeRequest
            from slack_sdk.socket_mode.response import SocketModeResponse
        except ImportError:
            logger.error("slack-sdk not installed. Run: pip install slack-sdk[socket-mode]")
            return

        web_client = AsyncWebClient(token=self.bot_token)
        socket_client = SocketModeClient(app_token=self.app_token, web_client=web_client)

        async def handle_event(client: SocketModeClient, req: SocketModeRequest):
            if req.type == "events_api":
                event = req.payload.get("event", {})
                if event.get("type") == "message" and not event.get("bot_id"):
                    source = SlackEventSource(
                        user_id=event.get("user", ""),
                        channel_id=event.get("channel", ""),
                        thread_ts=event.get("thread_ts"),
                    )
                    text = event.get("text", "")
                    if text and self.is_allowed(source):
                        await on_message(text, source)

                response = SocketModeResponse(envelope_id=req.envelope_id)
                await client.send_socket_mode_response(response)

        socket_client.socket_mode_request_listeners.append(handle_event)
        await socket_client.connect()
        logger.info("Slack Socket Mode connected")
        await self._stop_event.wait()
        await socket_client.disconnect()

    async def reply(self, content: str, source: SlackEventSource) -> None:
        try:
            from slack_sdk.web.async_client import AsyncWebClient
        except ImportError:
            logger.error("slack-sdk not installed")
            return

        client = AsyncWebClient(token=self.bot_token)
        kwargs: dict[str, Any] = {
            "channel": source.channel_id,
            "text": content,
        }
        if source.thread_ts:
            kwargs["thread_ts"] = source.thread_ts
        await client.chat_postMessage(**kwargs)

    async def stop(self) -> None:
        self._stop_event.set()
