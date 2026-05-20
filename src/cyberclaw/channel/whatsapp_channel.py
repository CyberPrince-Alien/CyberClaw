"""WhatsApp Business API channel integration."""

import asyncio
import logging
from typing import Callable, Awaitable, Any

from cyberclaw.channel.base import Channel
from cyberclaw.core.events import EventSource

logger = logging.getLogger(__name__)


class WhatsAppEventSource(EventSource):
    _namespace = "platform-whatsapp"

    def __init__(self, phone_number: str, display_name: str = ""):
        self.phone_number = phone_number
        self.display_name = display_name

    def __str__(self) -> str:
        return f"platform-whatsapp:{self.phone_number}"

    @classmethod
    def from_string(cls, s: str) -> "WhatsAppEventSource":
        parts = s.split(":", 1)
        return cls(phone_number=parts[1] if len(parts) > 1 else "")


class WhatsAppChannel(Channel["WhatsAppEventSource"]):
    """WhatsApp Business API via Cloud API webhooks."""

    def __init__(self, config: Any):
        self.config = config
        self.phone_number_id: str = getattr(config, "phone_number_id", "")
        self.access_token: str = getattr(config, "access_token", "")
        self.verify_token: str = getattr(config, "verify_token", "cyberclaw-verify")
        self.allow_from: list[str] = getattr(config, "allow_from", [])
        self.dm_policy: str = getattr(config, "dm_policy", "pairing")
        self._stop_event = asyncio.Event()
        self._on_message = None

    @property
    def platform_name(self) -> str:
        return "whatsapp"

    def is_allowed(self, source: WhatsAppEventSource) -> bool:
        if "*" in self.allow_from:
            return True
        return source.phone_number in self.allow_from

    async def run(self, on_message: Callable[[str, WhatsAppEventSource], Awaitable[None]]) -> None:
        """Run webhook server for WhatsApp Cloud API.
        
        Note: WhatsApp requires a publicly accessible webhook URL.
        The gateway's FastAPI server handles webhook registration;
        this channel processes the incoming webhook payloads.
        """
        self._on_message = on_message
        logger.info("WhatsApp channel ready (webhook mode — register webhook at /webhook/whatsapp)")
        await self._stop_event.wait()

    async def handle_webhook(self, payload: dict[str, Any]) -> None:
        """Process an incoming WhatsApp webhook payload."""
        if not self._on_message:
            return

        entry = payload.get("entry", [])
        for e in entry:
            changes = e.get("changes", [])
            for change in changes:
                value = change.get("value", {})
                messages = value.get("messages", [])
                for msg in messages:
                    if msg.get("type") == "text":
                        text = msg.get("text", {}).get("body", "")
                        from_number = msg.get("from", "")
                        contact = value.get("contacts", [{}])[0]
                        display_name = contact.get("profile", {}).get("name", "")

                        source = WhatsAppEventSource(
                            phone_number=from_number,
                            display_name=display_name,
                        )
                        if text and self.is_allowed(source):
                            await self._on_message(text, source)

    async def reply(self, content: str, source: WhatsAppEventSource) -> None:
        """Send a reply via WhatsApp Cloud API."""
        try:
            import httpx
        except ImportError:
            logger.error("httpx not installed")
            return

        url = f"https://graph.facebook.com/v18.0/{self.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        body = {
            "messaging_product": "whatsapp",
            "to": source.phone_number,
            "type": "text",
            "text": {"body": content},
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=body, headers=headers)
            if resp.status_code != 200:
                logger.error("WhatsApp send failed: %s", resp.text)

    async def stop(self) -> None:
        self._stop_event.set()
