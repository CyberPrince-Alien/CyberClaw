"""Channel worker for ingesting platform messages."""

import asyncio
import time
from typing import TYPE_CHECKING

from .worker import Worker
from cyberclaw.channel.access import ChannelAccessManager
from cyberclaw.core.events import EventSource, InboundEvent

if TYPE_CHECKING:
    from cyberclaw.core.context import SharedContext


class ChannelWorker(Worker):
    """Ingests messages from platforms, publishes INBOUND events to Channel."""

    def __init__(self, context: "SharedContext"):
        super().__init__(context)
        self.channels = context.channels
        self.channel_map = {channel.platform_name: channel for channel in self.channels}
        self.access = ChannelAccessManager(context.config)

    async def run(self) -> None:
        """Start all channels and process incoming messages."""
        self.logger.info(f"ChannelWorker started with {len(self.channels)} channel(es)")

        channel_tasks = [
            channel.run(self._create_callback(channel.platform_name))
            for channel in self.channels
        ]

        try:
            await asyncio.gather(*channel_tasks)
        except asyncio.CancelledError:
            await asyncio.gather(*[channel.stop() for channel in self.channels])
            raise

    def _create_callback(self, platform: str):
        """Create callback for a specific platform."""

        async def callback(message: str, source: EventSource) -> None:
            try:
                channel = self.channel_map[platform]

                if not channel.is_allowed(source) or not self.access.is_allowed(
                    platform, source
                ):
                    if self.access.requires_pairing(platform):
                        code = self.access.get_or_create_code(platform, source)
                        await channel.reply(
                            "CyberClaw pairing required. "
                            f"Approve this sender from your trusted CLI with: "
                            f"/pairing approve {platform} {code}",
                            source,
                        )
                    self.logger.debug("Ignored unauthorized message from %s", platform)
                    return

                # Set default delivery source only on first non-CLI platform message
                if source.is_platform and source.platform_name != "cli":
                    if not self.context.config.default_delivery_source:
                        source_str_value = str(source)
                        self.context.config.set_runtime(
                            "default_delivery_source", source_str_value
                        )

                session_id = self.context.routing_table.get_or_create_session_id(source)

                # Publish INBOUND event with typed source
                event = InboundEvent(
                    session_id=session_id,
                    source=source,
                    content=message,
                    timestamp=time.time(),
                )
                await self.context.eventbus.publish(event)
                self.logger.debug(f"Published INBOUND event from {source}")

            except Exception as e:
                self.logger.error(f"Error processing message from {platform}: {e}")

        return callback
