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

    # Rate-limit penalty registry: provider_id -> {"count": int, "penalty": float, "last_hit": float}
    _provider_penalties: dict[str, dict] = {}

    # Sticky sessions registry: session_id -> provider_id
    _session_providers: dict[str, str] = {}

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

    def _get_provider_penalty(self, provider_id: str) -> float:
        """Get the current rate limit penalty for a provider with time-based decay."""
        if not getattr(self.config, "enable_priority_penalties", True):
            return 0.0
        import time
        entry = self._provider_penalties.get(provider_id)
        if not entry:
            return 0.0

        now = time.time()
        elapsed = now - entry["last_hit"]
        decay_interval = getattr(self.config, "penalty_decay_interval", 120.0)
        decay_steps = int(elapsed // decay_interval)
        
        if decay_steps > 0:
            entry["penalty"] = max(0.0, entry["penalty"] - decay_steps)
            entry["last_hit"] = now
            if entry["penalty"] <= 0.0:
                self._provider_penalties.pop(provider_id, None)
                return 0.0
                
        return entry["penalty"]

    def _record_provider_success(self, provider_id: str) -> None:
        """Record a success for a provider, reducing its penalty."""
        entry = self._provider_penalties.get(provider_id)
        if entry:
            entry["penalty"] = max(0.0, entry["penalty"] - 1.0)
            if entry["penalty"] <= 0.0:
                self._provider_penalties.pop(provider_id, None)

    def _record_provider_failure(self, provider_id: str, error: Exception) -> float:
        """Record a failure for a provider, adding rate limit penalties."""
        import time
        error_str = str(error).lower()
        is_rate_limit = "429" in error_str or "rate limit" in error_str
        cooldown_duration = 120.0 if is_rate_limit else 60.0
        
        # Cooldown circuit breaker
        self._failed_providers[provider_id] = time.time() + cooldown_duration
        
        # Add priority penalty
        if getattr(self.config, "enable_priority_penalties", True):
            now = time.time()
            entry = self._provider_penalties.get(provider_id)
            penalty_increment = 3.0 if is_rate_limit else 1.5
            max_penalty = 10.0
            
            if entry:
                entry["count"] += 1
                entry["last_hit"] = now
                entry["penalty"] = min(max_penalty, entry["penalty"] + penalty_increment)
            else:
                self._provider_penalties[provider_id] = {
                    "count": 1,
                    "penalty": penalty_increment,
                    "last_hit": now
                }
            
        return cooldown_duration

    async def chat_with_failover(
        self,
        messages: list[Message],
        tools: Optional[list[dict[str, Any]]] = None,
        session_id: Optional[str] = None,
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

        # 2. Priority + Penalty dynamic sorting
        provider_items = []
        for priority, pid, provider in available_providers:
            penalty = self._get_provider_penalty(pid)
            effective_priority = priority + penalty
            provider_items.append((effective_priority, priority, pid, provider))

        # Sort primarily by effective_priority (lower number = higher priority)
        provider_items.sort(key=lambda x: x[0])

        # Sticky sessions: check if there is an active session provider
        if getattr(self.config, "enable_sticky_sessions", True) and session_id and session_id in self._session_providers:
            preferred_pid = self._session_providers[session_id]
            idx = next((i for i, x in enumerate(provider_items) if x[2] == preferred_pid), -1)
            if idx > 0:
                preferred_item = provider_items.pop(idx)
                provider_items.insert(0, preferred_item)

        for effective_priority, base_priority, provider_id, provider in provider_items:
            try:
                self.logger.info(
                    "Attempting provider: %s/%s (effective priority: %.1f)",
                    provider_id,
                    provider.model,
                    effective_priority,
                )

                result = await provider.chat(messages, tools, **kwargs)
                self.logger.info("Success with provider: %s", provider.model)

                # Reset circuit breaker on success
                self._failed_providers.pop(provider_id, None)
                self._record_provider_success(provider_id)

                # Record sticky session
                if getattr(self.config, "enable_sticky_sessions", True) and session_id:
                    self._session_providers[session_id] = provider_id

                return result

            except Exception as e:
                cooldown_duration = self._record_provider_failure(provider_id, e)
                last_error = e
                self.logger.warning(
                    "Provider %s failed: %s. Applying %.1fs cooldown and rate limit penalty.",
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
        session_id: Optional[str] = None,
        **kwargs: Any,
    ) -> tuple[str, list[LLMToolCall]]:
        """Chat using specific provider or with failover."""
        if provider_id:
            provider = self.get_provider(provider_id)
            if not provider:
                raise ValueError(f"Provider {provider_id} not found or disabled")
            return await provider.chat(messages, tools, **kwargs)

        return await self.chat_with_failover(messages, tools, session_id=session_id, **kwargs)

    async def chat_stream(
        self,
        messages: list[Message],
        tools: Optional[list[dict[str, Any]]] = None,
        provider_id: Optional[str] = None,
        session_id: Optional[str] = None,
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

        # 2. Priority + Penalty dynamic sorting
        provider_items = []
        for priority, pid, provider in available_providers:
            penalty = self._get_provider_penalty(pid)
            effective_priority = priority + penalty
            provider_items.append((effective_priority, priority, pid, provider))

        # Sort primarily by effective_priority (lower number = higher priority)
        provider_items.sort(key=lambda x: x[0])

        # Sticky sessions: check if there is an active session provider
        if getattr(self.config, "enable_sticky_sessions", True) and session_id and session_id in self._session_providers:
            preferred_pid = self._session_providers[session_id]
            idx = next((i for i, x in enumerate(provider_items) if x[2] == preferred_pid), -1)
            if idx > 0:
                preferred_item = provider_items.pop(idx)
                provider_items.insert(0, preferred_item)

        for effective_priority, base_priority, pid, provider in provider_items:
            try:
                self.logger.info("Streaming with provider: %s (effective priority: %.1f)", pid, effective_priority)
                success = False
                async for chunk in provider.chat_stream(messages, tools, **kwargs):
                    if chunk.type == ChunkType.ERROR:
                        raise RuntimeError(chunk.error)
                    yield chunk
                    success = True

                if success:
                    # Reset circuit breaker on success
                    self._failed_providers.pop(pid, None)
                    self._record_provider_success(pid)
                    
                    # Record sticky session
                    if getattr(self.config, "enable_sticky_sessions", True) and session_id:
                        self._session_providers[session_id] = pid
                    return  # Success

            except Exception as e:
                cooldown_duration = self._record_provider_failure(pid, e)
                last_error = e
                self.logger.warning(
                    "Stream provider %s failed: %s. Applying %.1fs cooldown and rate limit penalty.",
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
