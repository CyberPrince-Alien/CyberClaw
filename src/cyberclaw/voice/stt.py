"""Speech-to-Text abstraction layer."""

import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


class STTProvider(ABC):
    """Abstract STT provider."""

    @abstractmethod
    async def transcribe(self, audio_data: bytes, language: str | None = None) -> str:
        """Transcribe audio bytes to text."""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        ...


class WhisperSTTProvider(STTProvider):
    """OpenAI Whisper API STT provider."""

    def __init__(self, api_key: str, model: str = "whisper-1"):
        self.api_key = api_key
        self.model = model

    @property
    def name(self) -> str:
        return "whisper"

    async def transcribe(self, audio_data: bytes, language: str | None = None) -> str:
        import httpx

        url = "https://api.openai.com/v1/audio/transcriptions"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        files = {"file": ("audio.wav", audio_data, "audio/wav")}
        data: dict[str, str] = {"model": self.model}
        if language:
            data["language"] = language

        async with httpx.AsyncClient() as client:
            resp = await client.post(url, headers=headers, files=files, data=data, timeout=30)
            resp.raise_for_status()
            return resp.json().get("text", "")


class DeepgramSTTProvider(STTProvider):
    """Deepgram STT provider."""

    def __init__(self, api_key: str, model: str = "nova-2"):
        self.api_key = api_key
        self.model = model

    @property
    def name(self) -> str:
        return "deepgram"

    async def transcribe(self, audio_data: bytes, language: str | None = None) -> str:
        import httpx

        url = f"https://api.deepgram.com/v1/listen?model={self.model}"
        if language:
            url += f"&language={language}"
        headers = {
            "Authorization": f"Token {self.api_key}",
            "Content-Type": "audio/wav",
        }

        async with httpx.AsyncClient() as client:
            resp = await client.post(url, headers=headers, content=audio_data, timeout=30)
            resp.raise_for_status()
            result = resp.json()
            alternatives = (
                result.get("results", {})
                .get("channels", [{}])[0]
                .get("alternatives", [{}])
            )
            return alternatives[0].get("transcript", "") if alternatives else ""


class STTManager:
    """Manages STT providers."""

    def __init__(self):
        self._providers: dict[str, STTProvider] = {}
        self._default: str | None = None

    def register(self, provider: STTProvider, default: bool = False) -> None:
        self._providers[provider.name] = provider
        if default or not self._default:
            self._default = provider.name

    def get(self, name: str | None = None) -> STTProvider | None:
        if name:
            return self._providers.get(name)
        if self._default:
            return self._providers.get(self._default)
        return None

    async def transcribe(self, audio_data: bytes, provider: str | None = None) -> str:
        p = self.get(provider)
        if not p:
            raise RuntimeError("No STT provider available")
        return await p.transcribe(audio_data)
