"""Music Generation -- provider registry for AI music creation."""

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

@dataclass
class MusicResult:
    audio_url: str = ""; audio_bytes: bytes = b""; duration_seconds: float = 0
    provider: str = ""; model: str = ""; prompt: str = ""

class MusicProvider:
    id: str; name: str
    async def generate(self, prompt: str, duration: int = 30, **kwargs) -> MusicResult:
        raise NotImplementedError

class SunoProvider(MusicProvider):
    """Suno AI music generation."""
    id = "suno"; name = "Suno"
    def __init__(self, api_key: str = "", api_base: str = ""):
        self.api_key = api_key
        self.api_base = api_base or "https://api.suno.ai/v1"
    async def generate(self, prompt: str, duration: int = 30, **kwargs) -> MusicResult:
        import httpx
        async with httpx.AsyncClient() as c:
            r = await c.post(f"{self.api_base}/generate", json={"prompt": prompt, "duration": duration},
                            headers={"Authorization": f"Bearer {self.api_key}"}, timeout=120)
            data = r.json()
            return MusicResult(audio_url=data.get("audio_url", ""), duration_seconds=duration,
                              provider="suno", prompt=prompt)

class ReplicateMusicProvider(MusicProvider):
    """Replicate MusicGen."""
    id = "replicate"; name = "MusicGen (Replicate)"
    def __init__(self, api_key: str = ""):
        self.api_key = api_key
    async def generate(self, prompt: str, duration: int = 30, **kwargs) -> MusicResult:
        import httpx
        async with httpx.AsyncClient() as c:
            r = await c.post("https://api.replicate.com/v1/predictions",
                json={"version": "b05b1dff1d8c386be1d0f076dba4b380849bef659cb4e12f0da25c69d7eab7e4",
                      "input": {"prompt": prompt, "duration": min(duration, 30)}},
                headers={"Authorization": f"Token {self.api_key}"}, timeout=120)
            data = r.json()
            return MusicResult(audio_url=data.get("urls", {}).get("get", ""),
                              duration_seconds=duration, provider="replicate", prompt=prompt)

class MusicGenerationRegistry:
    def __init__(self):
        self._providers: dict[str, MusicProvider] = {}
    def register(self, provider: MusicProvider):
        self._providers[provider.id] = provider
    def get(self, provider_id: str) -> MusicProvider | None:
        return self._providers.get(provider_id)
    def list_providers(self) -> list[str]:
        return list(self._providers.keys())

MUSIC_TOOL_SCHEMA = {"type": "function", "function": {
    "name": "generate_music", "description": "Generate music from a text description.",
    "parameters": {"type": "object", "properties": {
        "prompt": {"type": "string", "description": "Music description"},
        "duration_seconds": {"type": "integer", "default": 30},
        "provider": {"type": "string", "enum": ["suno", "replicate"]}},
    "required": ["prompt"]}}}
