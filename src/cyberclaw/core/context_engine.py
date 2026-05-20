"""Context Engine -- dynamic context building with plugin-contributed context."""

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)

@dataclass
class ContextContribution:
    """A piece of context contributed by a plugin or subsystem."""
    source: str
    priority: int = 0  # Higher = injected first
    content: str = ""
    max_tokens: int = 2000

@dataclass
class ContextRequest:
    """Request for context with constraints."""
    agent_id: str
    user_message: str
    max_total_tokens: int = 8000
    include_memory: bool = True
    include_tools: bool = True
    include_history: bool = True

class ContextEngine:
    """Builds dynamic context from registered providers."""

    def __init__(self):
        self._providers: dict[str, Callable[[ContextRequest], ContextContribution | None]] = {}
        self._static: list[ContextContribution] = []

    def register_provider(self, name: str, provider: Callable[[ContextRequest], ContextContribution | None]):
        self._providers[name] = provider
        logger.debug("Context provider registered: %s", name)

    def add_static(self, source: str, content: str, priority: int = 0):
        self._static.append(ContextContribution(source=source, priority=priority, content=content))

    def build(self, request: ContextRequest) -> list[ContextContribution]:
        contributions: list[ContextContribution] = list(self._static)
        for name, provider in self._providers.items():
            try:
                c = provider(request)
                if c and c.content:
                    contributions.append(c)
            except Exception as e:
                logger.warning("Context provider %s failed: %s", name, e)
        contributions.sort(key=lambda c: c.priority, reverse=True)
        # Trim to max tokens
        result = []; total = 0
        for c in contributions:
            est = len(c.content) // 4  # rough token estimate
            if total + est > request.max_total_tokens:
                trimmed = c.content[:request.max_total_tokens * 4 - total * 4]
                result.append(ContextContribution(source=c.source, priority=c.priority,
                                                   content=trimmed, max_tokens=c.max_tokens))
                break
            result.append(c); total += est
        return result

    def build_text(self, request: ContextRequest) -> str:
        parts = []
        for c in self.build(request):
            if c.content.strip():
                parts.append(f"[Context from {c.source}]\n{c.content}")
        return "\n\n".join(parts)

    @property
    def provider_names(self) -> list[str]:
        return list(self._providers.keys())
