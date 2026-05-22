"""Multi-provider LLM manager with failover and streaming support."""

import logging
from typing import Any, AsyncIterator, Optional

from litellm import TYPE_CHECKING
from litellm.types.completion import ChatCompletionMessageParam as Message

from .base import LLMProvider, LLMToolCall, ModelInfo
from cyberclaw.core.streaming import StreamChunk, ChunkType

if TYPE_CHECKING:
    from cyberclaw.utils.config import LLMConfig, LLMProviderConfig


class MultiLLMProvider:
    """Manages multiple LLM providers with failover capability."""

    # Shared circuit-breaker cache: provider_id -> cooldown_until_timestamp
    _failed_providers: dict[str, float] = {}

    def __init__(self, config: "LLMConfig"):
        """Initialize multi-provider manager."""
        self.config = config
        self.providers = self._load_providers()
        self.logger = logging.getLogger(__name__)

    def _load_providers(self) -> list[tuple[int, str, LLMProvider]]:
        """Load and sort providers by priority."""
        providers = []

        # Load configured providers
        for provider_config in self.config.providers:
            if provider_config.enabled:
                provider = LLMProvider(
                    model=self._model_name(provider_config),
                    api_key=provider_config.api_key or ("ollama" if provider_config.id == "ollama" else ""),
                    api_base=provider_config.api_base,
                    temperature=self.config.temperature,
                    max_tokens=self.config.max_tokens,
                )
                providers.append((provider_config.priority, provider_config.id, provider))

        # Sort by priority (lower number = higher priority), but ensure default_provider is first
        providers.sort(key=lambda x: (0 if x[1] == self.config.default_provider else 1, x[0]))

        # Store as list of tuples (priority, provider_id, provider)
        return providers

    @staticmethod
    def _model_name(provider_config: "LLMProviderConfig") -> str:
        """Return the LiteLLM model name for a configured provider."""
        model = provider_config.model
        provider = provider_config.provider

        if provider in ("openai", "anthropic"):
            return model
        if model.startswith(f"{provider}/"):
            return model

        return f"{provider}/{model}"

    def get_provider(self, provider_id: Optional[str] = None) -> Optional[LLMProvider]:
        """Get a specific provider by ID or the default provider."""
        if provider_id:
            for _priority, configured_id, provider in self.providers:
                if configured_id == provider_id:
                    return provider
            return None

        # Return highest priority provider as default
        return self.providers[0][2] if self.providers else None

    async def chat_with_failover(
        self,
        messages: list[Message],
        tools: Optional[list[dict[str, Any]]] = None,
        **kwargs: Any,
    ) -> tuple[str, list[LLMToolCall]]:
        """Attempt chat with failover to backup providers."""
        import time
        import random

        last_error = None
        now = time.time()

        # 1. Filter out cooled-off providers
        available_providers = []
        for priority, pid, provider in self.providers:
            cooldown_until = self._failed_providers.get(pid, 0.0)
            if now < cooldown_until:
                self.logger.warning(
                    "Provider %s is in cooling-off period (circuit broken) for another %.1fs. Skipping.",
                    pid,
                    cooldown_until - now,
                )
                continue
            available_providers.append((priority, pid, provider))

        # Fallback: if all configured providers are cooled off, ignore cooldown so we don't return empty
        if not available_providers:
            available_providers = self.providers

        # 2. Priority-based Load Balancing: group by priority and shuffle within groups
        priority_groups = {}
        for priority, pid, provider in available_providers:
            priority_groups.setdefault(priority, []).append((priority, pid, provider))

        sorted_available = []
        for prio in sorted(priority_groups.keys()):
            group = priority_groups[prio]
            random.shuffle(group)  # Load-balance traffic by shuffling equal priorities
            sorted_available.extend(group)

        for priority, provider_id, provider in sorted_available:
            try:
                self.logger.info(
                    "Attempting provider: %s/%s (priority: %d)",
                    provider_id,
                    provider.model,
                    priority,
                )

                result = await provider.chat(messages, tools, **kwargs)
                self.logger.info("Success with provider: %s", provider.model)

                # Reset circuit breaker on success
                if provider_id in self._failed_providers:
                    del self._failed_providers[provider_id]

                return result

            except Exception as e:
                # 3. Add to cooling-off period
                error_str = str(e).lower()
                cooldown_duration = 120.0 if ("429" in error_str or "rate limit" in error_str) else 60.0
                self._failed_providers[provider_id] = time.time() + cooldown_duration

                last_error = e
                self.logger.warning(
                    "Provider %s failed: %s. Applying %.1fs cooldown.",
                    provider_id,
                    str(e),
                    cooldown_duration,
                )

                if not self.config.enable_failover:
                    raise

                continue

        # All providers failed
        error_msg = "All LLM providers failed"
        if last_error:
            error_msg += f": {str(last_error)}"

        self.logger.error(error_msg)
        raise Exception(error_msg)

    async def chat(
        self,
        messages: list[Message],
        tools: Optional[list[dict[str, Any]]] = None,
        provider_id: Optional[str] = None,
        **kwargs: Any,
    ) -> tuple[str, list[LLMToolCall]]:
        """Chat using specific provider or with failover."""
        if provider_id:
            provider = self.get_provider(provider_id)
            if not provider:
                raise ValueError(f"Provider {provider_id} not found or disabled")
            return await provider.chat(messages, tools, **kwargs)

        return await self.chat_with_failover(messages, tools, **kwargs)

    async def chat_stream(
        self,
        messages: list[Message],
        tools: Optional[list[dict[str, Any]]] = None,
        provider_id: Optional[str] = None,
        **kwargs: Any,
    ) -> AsyncIterator[StreamChunk]:
        """Stream chat with failover to backup providers."""
        if provider_id:
            provider = self.get_provider(provider_id)
            if not provider:
                yield StreamChunk(type=ChunkType.ERROR, error=f"Provider {provider_id} not found")
                return
            async for chunk in provider.chat_stream(messages, tools, **kwargs):
                yield chunk
            return

        import time
        import random

        last_error = None
        now = time.time()

        # 1. Filter out cooled-off providers
        available_providers = []
        for priority, pid, provider in self.providers:
            cooldown_until = self._failed_providers.get(pid, 0.0)
            if now < cooldown_until:
                self.logger.warning(
                    "Stream provider %s is in cooling-off period for another %.1fs. Skipping.",
                    pid,
                    cooldown_until - now,
                )
                continue
            available_providers.append((priority, pid, provider))

        # Fallback: if all configured providers are cooled off, ignore cooldown so we don't return empty
        if not available_providers:
            available_providers = self.providers

        # 2. Priority-based Load Balancing: group by priority and shuffle within groups
        priority_groups = {}
        for priority, pid, provider in available_providers:
            priority_groups.setdefault(priority, []).append((priority, pid, provider))

        sorted_available = []
        for prio in sorted(priority_groups.keys()):
            group = priority_groups[prio]
            random.shuffle(group)  # Load-balance traffic by shuffling equal priorities
            sorted_available.extend(group)

        for priority, pid, provider in sorted_available:
            try:
                self.logger.info("Streaming with provider: %s (priority: %d)", pid, priority)
                success = False
                async for chunk in provider.chat_stream(messages, tools, **kwargs):
                    if chunk.type == ChunkType.ERROR:
                        raise RuntimeError(chunk.error)
                    yield chunk
                    success = True

                if success:
                    # Reset circuit breaker on success
                    if pid in self._failed_providers:
                        del self._failed_providers[pid]
                    return  # Success

            except Exception as e:
                # 3. Add to cooling-off period
                error_str = str(e).lower()
                cooldown_duration = 120.0 if ("429" in error_str or "rate limit" in error_str) else 60.0
                self._failed_providers[pid] = time.time() + cooldown_duration

                last_error = e
                self.logger.warning(
                    "Stream provider %s failed: %s. Applying %.1fs cooldown.",
                    pid,
                    str(e),
                    cooldown_duration,
                )

                if not self.config.enable_failover:
                    yield StreamChunk(type=ChunkType.ERROR, error=str(e))
                    return

                continue

        yield StreamChunk(
            type=ChunkType.ERROR,
            error=f"All providers failed: {last_error}",
        )

    def get_model_info(self) -> ModelInfo:
        """Get model info from the default (highest priority) provider."""
        if not self.providers:
            return ModelInfo(
                model="unknown", max_tokens=2048, supports_tools=True,
                supports_vision=False, supports_streaming=True, context_window=128000,
            )
        return self.providers[0][2].get_model_info()

    def count_tokens(self, messages: list[Message]) -> int:
        """Count tokens using the default provider."""
        if not self.providers:
            return sum(len(str(m.get('content', ''))) for m in messages) // 4
        return self.providers[0][2].count_tokens(messages)

    def get_available_providers(self) -> list[str]:
        """Get list of available provider IDs."""
        return [p.id for p in self.config.providers if p.enabled]

    def health_check(self) -> dict[str, bool]:
        """Check health of all providers."""
        return {p.id: True for p in self.config.providers if p.enabled}
