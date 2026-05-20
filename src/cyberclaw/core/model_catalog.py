"""Model Catalog — unified registry of LLM models with costs, capabilities, and live discovery.

Tracks:
- Per-model pricing (input/output tokens)
- Capability flags (reasoning, vision, tools, streaming)
- Context window and max output tokens
- Status (available, preview, deprecated)
- Live discovery from provider APIs
"""

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ModelStatus(str, Enum):
    AVAILABLE = "available"
    PREVIEW = "preview"
    DEPRECATED = "deprecated"
    DISABLED = "disabled"


@dataclass
class ModelCost:
    """Per-million-token pricing in USD."""
    input: float = 0.0
    output: float = 0.0
    cache_read: float = 0.0
    cache_write: float = 0.0


@dataclass
class ModelCapabilities:
    reasoning: bool = False
    vision: bool = False
    tools: bool = True
    streaming: bool = True
    json_mode: bool = False
    image_generation: bool = False
    code_execution: bool = False


@dataclass
class CatalogEntry:
    provider: str
    model: str
    label: str = ""
    context_window: int = 4096
    max_output_tokens: int = 4096
    cost: ModelCost = field(default_factory=ModelCost)
    capabilities: ModelCapabilities = field(default_factory=ModelCapabilities)
    status: ModelStatus = ModelStatus.AVAILABLE
    status_reason: str = ""
    replaced_by: str = ""
    tags: list[str] = field(default_factory=list)
    source: str = "static"  # static, live, config
    fetched_at: float = 0.0

    @property
    def ref(self) -> str:
        return f"{self.provider}/{self.model}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "label": self.label or self.model,
            "ref": self.ref,
            "context_window": self.context_window,
            "max_output_tokens": self.max_output_tokens,
            "cost": {
                "input_per_mtok": self.cost.input,
                "output_per_mtok": self.cost.output,
            },
            "capabilities": {
                "reasoning": self.capabilities.reasoning,
                "vision": self.capabilities.vision,
                "tools": self.capabilities.tools,
                "streaming": self.capabilities.streaming,
            },
            "status": self.status.value,
            "tags": self.tags,
        }


# ── Static catalog with known models ──────────────────────────────────

STATIC_CATALOG: list[CatalogEntry] = [
    # OpenAI
    CatalogEntry("openai", "gpt-4o", "GPT-4o", 128000, 16384,
                 ModelCost(2.50, 10.00), ModelCapabilities(reasoning=True, vision=True)),
    CatalogEntry("openai", "gpt-4o-mini", "GPT-4o Mini", 128000, 16384,
                 ModelCost(0.15, 0.60), ModelCapabilities(vision=True)),
    CatalogEntry("openai", "gpt-4-turbo", "GPT-4 Turbo", 128000, 4096,
                 ModelCost(10.00, 30.00), ModelCapabilities(vision=True)),
    CatalogEntry("openai", "gpt-4", "GPT-4", 8192, 8192,
                 ModelCost(30.00, 60.00), ModelCapabilities()),
    CatalogEntry("openai", "gpt-3.5-turbo", "GPT-3.5 Turbo", 16385, 4096,
                 ModelCost(0.50, 1.50), ModelCapabilities(),
                 status=ModelStatus.DEPRECATED, replaced_by="gpt-4o-mini"),
    CatalogEntry("openai", "o1", "o1", 200000, 100000,
                 ModelCost(15.00, 60.00), ModelCapabilities(reasoning=True)),
    CatalogEntry("openai", "o1-mini", "o1 Mini", 128000, 65536,
                 ModelCost(3.00, 12.00), ModelCapabilities(reasoning=True)),
    CatalogEntry("openai", "o3-mini", "o3 Mini", 200000, 100000,
                 ModelCost(1.10, 4.40), ModelCapabilities(reasoning=True)),

    # Google
    CatalogEntry("gemini", "gemini-2.5-flash", "Gemini 2.5 Flash", 1048576, 65536,
                 ModelCost(0.15, 0.60), ModelCapabilities(reasoning=True, vision=True)),
    CatalogEntry("gemini", "gemini-2.5-pro", "Gemini 2.5 Pro", 1048576, 65536,
                 ModelCost(1.25, 10.00), ModelCapabilities(reasoning=True, vision=True)),
    CatalogEntry("gemini", "gemini-2.0-flash", "Gemini 2.0 Flash", 1048576, 8192,
                 ModelCost(0.10, 0.40), ModelCapabilities(vision=True)),
    CatalogEntry("gemini", "gemini-1.5-pro", "Gemini 1.5 Pro", 2097152, 8192,
                 ModelCost(1.25, 5.00), ModelCapabilities(vision=True),
                 status=ModelStatus.DEPRECATED, replaced_by="gemini-2.5-pro"),

    # Anthropic
    CatalogEntry("anthropic", "claude-sonnet-4-20250514", "Claude Sonnet 4", 200000, 64000,
                 ModelCost(3.00, 15.00), ModelCapabilities(reasoning=True, vision=True)),
    CatalogEntry("anthropic", "claude-3-5-sonnet-20241022", "Claude 3.5 Sonnet", 200000, 8192,
                 ModelCost(3.00, 15.00), ModelCapabilities(vision=True)),
    CatalogEntry("anthropic", "claude-3-5-haiku-20241022", "Claude 3.5 Haiku", 200000, 8192,
                 ModelCost(0.80, 4.00), ModelCapabilities()),
    CatalogEntry("anthropic", "claude-3-opus-20240229", "Claude 3 Opus", 200000, 4096,
                 ModelCost(15.00, 75.00), ModelCapabilities(vision=True)),

    # Groq
    CatalogEntry("groq", "llama-3.3-70b-versatile", "Llama 3.3 70B", 128000, 32768,
                 ModelCost(0.59, 0.79), ModelCapabilities()),
    CatalogEntry("groq", "llama-3.1-8b-instant", "Llama 3.1 8B", 128000, 8192,
                 ModelCost(0.05, 0.08), ModelCapabilities()),
    CatalogEntry("groq", "mixtral-8x7b-32768", "Mixtral 8x7B", 32768, 32768,
                 ModelCost(0.24, 0.24), ModelCapabilities()),
    CatalogEntry("groq", "gemma2-9b-it", "Gemma 2 9B", 8192, 8192,
                 ModelCost(0.20, 0.20), ModelCapabilities()),

    # Meta via various providers
    CatalogEntry("nvidia_nim", "meta/llama-3.1-8b-instruct", "Llama 3.1 8B (NIM)", 128000, 4096,
                 ModelCost(0.10, 0.10), ModelCapabilities()),
    CatalogEntry("nvidia_nim", "meta/llama-3.1-70b-instruct", "Llama 3.1 70B (NIM)", 128000, 4096,
                 ModelCost(0.35, 0.40), ModelCapabilities()),

    # OpenRouter
    CatalogEntry("openrouter", "openai/gpt-4o-mini", "GPT-4o Mini (OR)", 128000, 16384,
                 ModelCost(0.15, 0.60), ModelCapabilities(vision=True)),
    CatalogEntry("openrouter", "anthropic/claude-sonnet-4", "Claude Sonnet 4 (OR)", 200000, 64000,
                 ModelCost(3.00, 15.00), ModelCapabilities(reasoning=True, vision=True)),
    CatalogEntry("openrouter", "google/gemini-2.5-flash", "Gemini 2.5 Flash (OR)", 1048576, 65536,
                 ModelCost(0.15, 0.60), ModelCapabilities(reasoning=True, vision=True)),
]


class ModelCatalog:
    """Unified model catalog with static + live discovery."""

    def __init__(self):
        self._entries: dict[str, CatalogEntry] = {}
        self._load_static()

    def _load_static(self) -> None:
        for entry in STATIC_CATALOG:
            entry.source = "static"
            self._entries[entry.ref] = entry

    def get(self, provider: str, model: str) -> CatalogEntry | None:
        return self._entries.get(f"{provider}/{model}")

    def get_by_ref(self, ref: str) -> CatalogEntry | None:
        return self._entries.get(ref)

    def list_models(self, provider: str | None = None, only_available: bool = False) -> list[CatalogEntry]:
        entries = list(self._entries.values())
        if provider:
            entries = [e for e in entries if e.provider == provider]
        if only_available:
            entries = [e for e in entries if e.status == ModelStatus.AVAILABLE]
        return sorted(entries, key=lambda e: (e.provider, e.model))

    def list_providers(self) -> list[str]:
        return sorted(set(e.provider for e in self._entries.values()))

    def register(self, entry: CatalogEntry) -> None:
        self._entries[entry.ref] = entry

    def estimate_cost(self, provider: str, model: str, input_tokens: int, output_tokens: int) -> float:
        """Estimate cost in USD for a given call."""
        entry = self.get(provider, model)
        if not entry:
            return 0.0
        input_cost = (input_tokens / 1_000_000) * entry.cost.input
        output_cost = (output_tokens / 1_000_000) * entry.cost.output
        return round(input_cost + output_cost, 6)

    def find_cheapest(self, min_context: int = 0, needs_vision: bool = False,
                      needs_reasoning: bool = False) -> CatalogEntry | None:
        """Find the cheapest model matching requirements."""
        candidates = [
            e for e in self._entries.values()
            if e.status == ModelStatus.AVAILABLE
            and e.context_window >= min_context
            and (not needs_vision or e.capabilities.vision)
            and (not needs_reasoning or e.capabilities.reasoning)
        ]
        if not candidates:
            return None
        return min(candidates, key=lambda e: e.cost.input + e.cost.output)

    def find_best(self, needs_vision: bool = False, needs_reasoning: bool = False) -> CatalogEntry | None:
        """Find the most capable model (highest cost as proxy)."""
        candidates = [
            e for e in self._entries.values()
            if e.status == ModelStatus.AVAILABLE
            and (not needs_vision or e.capabilities.vision)
            and (not needs_reasoning or e.capabilities.reasoning)
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda e: e.context_window * (e.cost.input + e.cost.output + 0.01))

    async def discover_live(self, provider: str, api_key: str, api_base: str = "") -> int:
        """Discover models from a provider's API (OpenAI-compatible /v1/models)."""
        import httpx

        base = api_base.rstrip("/") if api_base else self._default_base(provider)
        if not base:
            return 0

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{base}/models",
                    headers={"Authorization": f"Bearer {api_key}"},
                    timeout=15,
                )
                if resp.status_code != 200:
                    logger.warning("Model discovery failed for %s: %s", provider, resp.status_code)
                    return 0

                data = resp.json()
                models = data.get("data", [])
                count = 0
                for m in models:
                    model_id = m.get("id", "")
                    if not model_id:
                        continue
                    ref = f"{provider}/{model_id}"
                    if ref not in self._entries:
                        self._entries[ref] = CatalogEntry(
                            provider=provider,
                            model=model_id,
                            label=model_id,
                            source="live",
                            fetched_at=time.time(),
                        )
                        count += 1
                return count
        except Exception as e:
            logger.warning("Model discovery error for %s: %s", provider, e)
            return 0

    @staticmethod
    def _default_base(provider: str) -> str:
        bases = {
            "openai": "https://api.openai.com/v1",
            "groq": "https://api.groq.com/openai/v1",
            "openrouter": "https://openrouter.ai/api/v1",
        }
        return bases.get(provider, "")

    def to_dict(self) -> list[dict[str, Any]]:
        return [e.to_dict() for e in self.list_models()]


# Global singleton
_catalog = ModelCatalog()

def get_catalog() -> ModelCatalog:
    return _catalog
