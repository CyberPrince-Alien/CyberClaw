"""Auto-Reply Pipeline -- message processing with debounce, heartbeat, thinking mode."""

import asyncio, logging, time
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable
from enum import Enum

logger = logging.getLogger(__name__)

class ThinkingMode(str, Enum):
    HIDDEN = "hidden"; SHOW_INDICATOR = "indicator"; SHOW_CONTENT = "content"

@dataclass
class InboundMessage:
    content: str; source_id: str; channel: str; timestamp: float = field(default_factory=time.time)
    is_group: bool = False; mentions_bot: bool = False; reply_to_bot: bool = False
    media: list[dict] = field(default_factory=list)

@dataclass
class ReplyOptions:
    thinking_mode: ThinkingMode = ThinkingMode.SHOW_INDICATOR
    stream: bool = True; max_tokens: int = 4096
    include_context: bool = True; include_memory: bool = True

@dataclass
class SendPolicy:
    """Controls how and when replies are sent."""
    max_message_length: int = 4096; split_long: bool = True
    typing_indicator: bool = True; debounce_ms: int = 500
    rate_limit_per_minute: int = 30
    group_require_mention: bool = True

class InboundDebouncer:
    """Debounces rapid messages from the same source."""
    def __init__(self, delay_ms: int = 500):
        self.delay = delay_ms / 1000.0
        self._pending: dict[str, asyncio.Task] = {}
        self._buffers: dict[str, list[str]] = {}

    async def debounce(self, source_id: str, content: str,
                       handler: Callable[[str, str], Awaitable[None]]) -> None:
        key = source_id
        if key in self._pending:
            self._pending[key].cancel()
        self._buffers.setdefault(key, []).append(content)

        async def fire():
            await asyncio.sleep(self.delay)
            messages = self._buffers.pop(key, [])
            self._pending.pop(key, None)
            combined = "\n".join(messages) if len(messages) > 1 else messages[0]
            await handler(source_id, combined)

        self._pending[key] = asyncio.create_task(fire())

class HeartbeatChecker:
    """Periodically checks commitments and pending tasks."""
    def __init__(self, interval_seconds: int = 300):
        self.interval = interval_seconds
        self._running = False; self._task: asyncio.Task | None = None
        self._checks: list[Callable[[], Awaitable[list[str]]]] = []

    def register_check(self, check: Callable[[], Awaitable[list[str]]]):
        self._checks.append(check)

    async def start(self, on_notification: Callable[[str], Awaitable[None]]):
        self._running = True
        while self._running:
            await asyncio.sleep(self.interval)
            for check in self._checks:
                try:
                    notifications = await check()
                    for n in notifications:
                        await on_notification(n)
                except Exception as e:
                    logger.warning("Heartbeat check failed: %s", e)

    def stop(self): self._running = False

class AutoReplyPipeline:
    """Full message processing pipeline."""
    def __init__(self, send_policy: SendPolicy | None = None):
        self.policy = send_policy or SendPolicy()
        self.debouncer = InboundDebouncer(self.policy.debounce_ms)
        self.heartbeat = HeartbeatChecker()
        self._rate_tracker: dict[str, list[float]] = {}
        self._filters: list[Callable[[InboundMessage], bool]] = []

    def add_filter(self, fn: Callable[[InboundMessage], bool]):
        self._filters.append(fn)

    def should_reply(self, msg: InboundMessage) -> bool:
        if msg.is_group and self.policy.group_require_mention:
            if not msg.mentions_bot and not msg.reply_to_bot:
                return False
        for f in self._filters:
            if not f(msg): return False
        return self._check_rate(msg.source_id)

    def _check_rate(self, source_id: str) -> bool:
        now = time.time(); cutoff = now - 60
        self._rate_tracker.setdefault(source_id, [])
        self._rate_tracker[source_id] = [t for t in self._rate_tracker[source_id] if t > cutoff]
        if len(self._rate_tracker[source_id]) >= self.policy.rate_limit_per_minute:
            return False
        self._rate_tracker[source_id].append(now)
        return True

    def split_reply(self, text: str) -> list[str]:
        if not self.policy.split_long or len(text) <= self.policy.max_message_length:
            return [text]
        chunks = []; current = ""
        for line in text.split("\n"):
            if len(current) + len(line) + 1 > self.policy.max_message_length:
                if current: chunks.append(current)
                current = line
            else:
                current = current + "\n" + line if current else line
        if current: chunks.append(current)
        return chunks
