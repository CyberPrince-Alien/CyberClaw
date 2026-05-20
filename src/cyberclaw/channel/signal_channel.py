"""Signal channel integration via signal-cli-rest-api.

Connects to Signal via the signal-cli-rest-api HTTP bridge:
https://github.com/bbernhard/signal-cli-rest-api

Run signal-cli-rest-api as a Docker container:
  docker run -p 8080:8080 bbernhard/signal-cli-rest-api
"""

import asyncio
import logging
from typing import Callable, Awaitable, Any

from cyberclaw.channel.base import Channel
from cyberclaw.core.events import EventSource

logger = logging.getLogger(__name__)


class SignalEventSource(EventSource):
    _namespace = "platform-signal"

    def __init__(self, phone_number: str):
        self.phone_number = phone_number

    def __str__(self) -> str:
        return f"platform-signal:{self.phone_number}"

    @classmethod
    def from_string(cls, s: str) -> "SignalEventSource":
        parts = s.split(":", 1)
        return cls(phone_number=parts[1] if len(parts) > 1 else "")


class SignalChannel(Channel["SignalEventSource"]):
    """Signal channel via signal-cli-rest-api HTTP bridge."""

    def __init__(self, config: Any):
        self.config = config
        self.api_url: str = getattr(config, "api_url", "http://localhost:8080")
        self.phone_number: str = getattr(config, "phone_number", "")
        self.allow_from: list[str] = getattr(config, "allow_from", [])
        self.dm_policy: str = getattr(config, "dm_policy", "pairing")
        self._stop_event = asyncio.Event()
        self._on_message = None

    @property
    def platform_name(self) -> str:
        return "signal"

    def is_allowed(self, source: SignalEventSource) -> bool:
        if "*" in self.allow_from:
            return True
        return source.phone_number in self.allow_from

    async def run(self, on_message: Callable[[str, SignalEventSource], Awaitable[None]]) -> None:
        """Poll signal-cli-rest-api for incoming messages."""
        self._on_message = on_message

        try:
            import httpx
        except ImportError:
            logger.error("httpx not installed")
            return

        logger.info("Signal channel polling %s", self.api_url)

        async with httpx.AsyncClient() as client:
            while not self._stop_event.is_set():
                try:
                    # Receive messages
                    resp = await client.get(
                        f"{self.api_url}/v1/receive/{self.phone_number}",
                        timeout=30,
                    )
                    if resp.status_code == 200:
                        messages = resp.json()
                        for msg in messages:
                            envelope = msg.get("envelope", {})
                            data_message = envelope.get("dataMessage", {})
                            body = data_message.get("message", "")
                            source_number = envelope.get("source", "")

                            if body and source_number:
                                source = SignalEventSource(phone_number=source_number)
                                if self.is_allowed(source):
                                    await on_message(body, source)

                except httpx.TimeoutException:
                    pass  # Normal — long poll timeout
                except Exception as e:
                    logger.warning("Signal poll error: %s", e)
                    await asyncio.sleep(5)

                await asyncio.sleep(1)

    async def reply(self, content: str, source: SignalEventSource) -> None:
        """Send a reply via signal-cli-rest-api."""
        try:
            import httpx
        except ImportError:
            logger.error("httpx not installed")
            return

        url = f"{self.api_url}/v2/send"
        body = {
            "message": content,
            "number": self.phone_number,
            "recipients": [source.phone_number],
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=body, timeout=15)
            if resp.status_code not in (200, 201):
                logger.error("Signal send failed: %s", resp.text)

    async def stop(self) -> None:
        self._stop_event.set()
