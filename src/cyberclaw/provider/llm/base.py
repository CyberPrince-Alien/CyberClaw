"""Base LLM provider abstraction with streaming support."""

from dataclasses import dataclass
import logging
import os
import warnings
from typing import Any, AsyncIterator, Optional, cast

import litellm
# Suppress LiteLLM helper warnings
litellm.suppress_helper_warnings = True

# Suppress Pydantic serialization UserWarnings
warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")

from litellm import acompletion, Choices, TYPE_CHECKING, token_counter, model_cost
from litellm.types.completion import ChatCompletionMessageParam as Message

from cyberclaw.core.streaming import StreamChunk, ChunkType

if TYPE_CHECKING:
    from cyberclaw.utils.config import LLMConfig

logger = logging.getLogger(__name__)


@dataclass
class LLMToolCall:
    """A tool/function call from the LLM."""

    id: str
    name: str
    arguments: str  # JSON string


@dataclass
class ModelInfo:
    """Information about a model's capabilities."""

    model: str
    max_tokens: int
    supports_tools: bool
    supports_vision: bool
    supports_streaming: bool
    context_window: int

    @property
    def safe_token_threshold(self) -> int:
        """80% of context window as safe threshold for compaction."""
        return int(self.context_window * 0.8)


class LLMProvider:
    """LLM provider using litellm for multi-provider support."""

    def __init__(
        self,
        model: str,
        api_key: str,
        api_base: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs: Any,
    ):
        """Initialize LLM provider."""
        self.model = model
        self.api_key = api_key
        self.api_base = api_base
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._settings = kwargs
        self._model_info: ModelInfo | None = None

    @classmethod
    def from_config(cls, config: "LLMConfig") -> "LLMProvider":
        """Create provider from LLMConfig."""
        if not config.providers:
            raise ValueError("No enabled LLM providers configured")

        provider_config = config.providers[0]
        return cls(
            model=provider_config.model,
            api_key=provider_config.api_key,
            api_base=provider_config.api_base,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
        )

    def get_model_info(self) -> ModelInfo:
        """Get model capabilities. Cached after first lookup."""
        if self._model_info:
            return self._model_info

        # Try to get from litellm's model cost data
        context_window = 128000  # sensible default
        supports_tools = True
        supports_vision = False

        try:
            if model_cost and self.model in model_cost:
                info = model_cost[self.model]
                context_window = info.get("max_input_tokens", 128000)
                supports_vision = info.get("supports_vision", False)
                supports_tools = info.get("supports_function_calling", True)
        except Exception:
            pass  # Fall back to defaults

        self._model_info = ModelInfo(
            model=self.model,
            max_tokens=self.max_tokens,
            supports_tools=supports_tools,
            supports_vision=supports_vision,
            supports_streaming=True,
            context_window=context_window,
        )
        return self._model_info

    def count_tokens(self, messages: list[Message]) -> int:
        """Count tokens for a list of messages."""
        try:
            return token_counter(model=self.model, messages=messages)
        except Exception:
            # Rough fallback: ~4 chars per token
            total = sum(len(str(m.get("content", ""))) for m in messages)
            return total // 4

    async def chat(
        self,
        messages: list[Message],
        tools: Optional[list[dict[str, Any]]] = None,
        **kwargs: Any,
    ) -> tuple[str, list[LLMToolCall]]:
        """Default implementation using litellm. Subclasses can override."""
        self._clear_dead_local_proxy()
        request_kwargs = self._build_request(messages, tools, **kwargs)
        response = await acompletion(**request_kwargs)
        message = cast(Choices, response.choices[0]).message

        return (
            message.content or "",
            [
                LLMToolCall(
                    id=tc["id"],
                    name=tc["function"]["name"],
                    arguments=tc["function"]["arguments"],
                )
                for tc in (message.tool_calls or [])
            ],
        )

    async def chat_stream(
        self,
        messages: list[Message],
        tools: Optional[list[dict[str, Any]]] = None,
        **kwargs: Any,
    ) -> AsyncIterator[StreamChunk]:
        """Stream chat completion tokens."""
        self._clear_dead_local_proxy()
        request_kwargs = self._build_request(messages, tools, stream=True, **kwargs)

        try:
            response = await acompletion(**request_kwargs)

            collected_tool_calls: dict[int, dict[str, str]] = {}

            async for chunk in response:
                delta = chunk.choices[0].delta if chunk.choices else None
                if not delta:
                    continue

                # Handle content tokens
                if delta.content:
                    yield StreamChunk(type=ChunkType.TOKEN, content=delta.content)

                # Handle tool call chunks
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index if hasattr(tc, 'index') else 0
                        if idx not in collected_tool_calls:
                            collected_tool_calls[idx] = {
                                "id": "",
                                "name": "",
                                "arguments": "",
                            }
                        if hasattr(tc, 'id') and tc.id:
                            collected_tool_calls[idx]["id"] = tc.id
                        if hasattr(tc, 'function'):
                            if hasattr(tc.function, 'name') and tc.function.name:
                                collected_tool_calls[idx]["name"] = tc.function.name
                            if hasattr(tc.function, 'arguments') and tc.function.arguments:
                                collected_tool_calls[idx]["arguments"] += tc.function.arguments

                # Check for finish
                finish_reason = chunk.choices[0].finish_reason if chunk.choices else None
                if finish_reason == "tool_calls":
                    for idx, tc_data in sorted(collected_tool_calls.items()):
                        yield StreamChunk(
                            type=ChunkType.TOOL_START,
                            tool_name=tc_data["name"],
                            tool_call_id=tc_data["id"],
                            tool_args=tc_data["arguments"],
                        )
                elif finish_reason == "stop":
                    pass  # Will yield DONE below

            yield StreamChunk(type=ChunkType.DONE)

        except Exception as e:
            yield StreamChunk(type=ChunkType.ERROR, error=str(e))

    def _build_request(
        self,
        messages: list[Message],
        tools: Optional[list[dict[str, Any]]] = None,
        stream: bool = False,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Build request kwargs for litellm."""
        request_kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "api_key": self.api_key,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": stream,
        }
        if self.api_base:
            request_kwargs["api_base"] = self.api_base
        if tools:
            request_kwargs["tools"] = tools
        request_kwargs.update(kwargs)
        return request_kwargs

    @staticmethod
    def _clear_dead_local_proxy() -> None:
        """Ignore a common disabled-proxy sentinel that breaks API calls."""
        for key in (
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "ALL_PROXY",
            "GIT_HTTP_PROXY",
            "GIT_HTTPS_PROXY",
        ):
            if os.environ.get(key) == "http://127.0.0.1:9":
                os.environ.pop(key, None)
