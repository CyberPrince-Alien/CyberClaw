"""Matrix channel integration via matrix-nio."""

import asyncio
import logging
from typing import Callable, Awaitable, Any

from cyberclaw.channel.base import Channel
from cyberclaw.core.events import EventSource

logger = logging.getLogger(__name__)


class MatrixEventSource(EventSource):
    _namespace = "platform-matrix"

    def __init__(self, user_id: str, room_id: str):
        self.user_id = user_id
        self.room_id = room_id

    def __str__(self) -> str:
        return f"platform-matrix:{self.room_id}:{self.user_id}"

    @classmethod
    def from_string(cls, s: str) -> "MatrixEventSource":
        parts = s.split(":", 2)
        room_id = parts[1] if len(parts) > 1 else ""
        user_id = parts[2] if len(parts) > 2 else ""
        return cls(user_id=user_id, room_id=room_id)


class MatrixChannel(Channel["MatrixEventSource"]):
    """Matrix channel via matrix-nio library."""

    def __init__(self, config: Any):
        self.config = config
        self.homeserver: str = getattr(config, "homeserver", "")
        self.user_id_str: str = getattr(config, "user_id", "")
        self.access_token: str = getattr(config, "access_token", "")
        self.allowed_rooms: list[str] = getattr(config, "allowed_rooms", [])
        self.allow_from: list[str] = getattr(config, "allow_from", [])
        self._stop_event = asyncio.Event()
        self._client = None

    @property
    def platform_name(self) -> str:
        return "matrix"

    def is_allowed(self, source: MatrixEventSource) -> bool:
        if "*" in self.allow_from:
            return True
        return source.user_id in self.allow_from

    async def run(self, on_message: Callable[[str, MatrixEventSource], Awaitable[None]]) -> None:
        try:
            from nio import AsyncClient, RoomMessageText
        except ImportError:
            logger.error("matrix-nio not installed. Run: pip install matrix-nio")
            return

        client = AsyncClient(self.homeserver, self.user_id_str)
        client.access_token = self.access_token
        self._client = client

        async def message_callback(room, event):
            if event.sender == self.user_id_str:
                return
            source = MatrixEventSource(user_id=event.sender, room_id=room.room_id)
            if self.is_allowed(source):
                await on_message(event.body, source)

        client.add_event_callback(message_callback, RoomMessageText)

        logger.info("Matrix client syncing with %s", self.homeserver)
        await client.sync_forever(timeout=30000, full_state=True)

    async def reply(self, content: str, source: MatrixEventSource) -> None:
        if self._client:
            try:
                from nio import RoomSendResponse
            except ImportError:
                return
            await self._client.room_send(
                room_id=source.room_id,
                message_type="m.room.message",
                content={"msgtype": "m.text", "body": content},
            )

    async def stop(self) -> None:
        if self._client:
            await self._client.close()
        self._stop_event.set()
