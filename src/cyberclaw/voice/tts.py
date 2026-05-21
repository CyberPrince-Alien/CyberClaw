"""Text-to-Speech abstraction layer."""

import logging
from abc import ABC, abstractmethod
from typing import Any, AsyncIterator

logger = logging.getLogger(__name__)


class TTSProvider(ABC):
    """Abstract TTS provider."""

    @abstractmethod
    async def synthesize(self, text: str, voice: str | None = None) -> bytes:
        """Synthesize speech, return audio bytes (WAV/MP3)."""
        ...

    @abstractmethod
    async def stream_synthesize(self, text: str, voice: str | None = None) -> AsyncIterator[bytes]:
        """Stream audio chunks."""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        ...


class EdgeTTSProvider(TTSProvider):
    """Free TTS using Microsoft Edge's online TTS (edge-tts package)."""

    @property
    def name(self) -> str:
        return "edge-tts"

    async def synthesize(self, text: str, voice: str | None = None) -> bytes:
        try:
            import edge_tts
        except ImportError:
            raise RuntimeError("edge-tts not installed. Run: pip install edge-tts")

        voice = voice or "en-US-AriaNeural"
        communicate = edge_tts.Communicate(text, voice)
        audio_data = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_data += chunk["data"]
        return audio_data

    async def stream_synthesize(self, text: str, voice: str | None = None) -> AsyncIterator[bytes]:
        try:
            import edge_tts
        except ImportError:
            raise RuntimeError("edge-tts not installed")

        voice = voice or "en-US-AriaNeural"
        communicate = edge_tts.Communicate(text, voice)
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                yield chunk["data"]


class ElevenLabsTTSProvider(TTSProvider):
    """ElevenLabs TTS provider."""

    def __init__(self, api_key: str, voice_id: str = "21m00Tcm4TlvDq8ikWAM"):
        self.api_key = api_key
        self.voice_id = voice_id

    @property
    def name(self) -> str:
        return "elevenlabs"

    async def synthesize(self, text: str, voice: str | None = None) -> bytes:
        import httpx

        voice_id = voice or self.voice_id
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        headers = {"xi-api-key": self.api_key, "Content-Type": "application/json"}
        body = {"text": text, "model_id": "eleven_monolingual_v1"}

        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=body, headers=headers, timeout=30)
            resp.raise_for_status()
            return resp.content

    async def stream_synthesize(self, text: str, voice: str | None = None) -> AsyncIterator[bytes]:
        import httpx

        voice_id = voice or self.voice_id
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream"
        headers = {"xi-api-key": self.api_key, "Content-Type": "application/json"}
        body = {"text": text, "model_id": "eleven_monolingual_v1"}

        async with httpx.AsyncClient() as client:
            async with client.stream("POST", url, json=body, headers=headers, timeout=30) as resp:
                async for chunk in resp.aiter_bytes(1024):
                    yield chunk


class SupertonicTTSProvider(TTSProvider):
    """Local, offline, edge-native ONNX TTS using the Supertonic library."""

    def __init__(self, voice: str = "M4"):
        self.default_voice = voice
        self._tts_engine = None

    @property
    def name(self) -> str:
        return "supertonic"

    async def synthesize(self, text: str, voice: str | None = None) -> bytes:
        import io
        import soundfile as sf

        # Lazy load supertonic engine
        if self._tts_engine is None:
            from supertonic import TTS
            self._tts_engine = TTS(auto_download=True)

        voice_name = voice or self.default_voice

        # Load voice style preset or custom JSON path
        if voice_name.endswith(".json"):
            style = self._tts_engine.get_voice_style_from_path(voice_name)
        else:
            style = self._tts_engine.get_voice_style(voice_name=voice_name)

        # Synthesize speech
        wav, duration = self._tts_engine.synthesize(text, voice_style=style)

        # Flatten NumPy array and write to WAV bytes in memory
        data = wav.flatten()
        out = io.BytesIO()
        sf.write(out, data, 24000, format='WAV', subtype='PCM_16')
        return out.getvalue()

    async def stream_synthesize(self, text: str, voice: str | None = None) -> AsyncIterator[bytes]:
        import re
        import io
        import soundfile as sf

        # Lazy load supertonic engine
        if self._tts_engine is None:
            from supertonic import TTS
            self._tts_engine = TTS(auto_download=True)

        voice_name = voice or self.default_voice

        if voice_name.endswith(".json"):
            style = self._tts_engine.get_voice_style_from_path(voice_name)
        else:
            style = self._tts_engine.get_voice_style(voice_name=voice_name)

        # Robust regex-based sentence level split (ignoring common abbreviations)
        pattern = r"(?<!Mr\.)(?<!Mrs\.)(?<!Ms\.)(?<!Dr\.)(?<!Prof\.)(?<!Sr\.)(?<!Jr\.)(?<!Ph\.D\.)(?<!etc\.)(?<!e\.g\.)(?<!i\.e\.)(?<!vs\.)(?<!Inc\.)(?<!Ltd\.)(?<!Co\.)(?<!Corp\.)(?<!St\.)(?<!Ave\.)(?<!Blvd\.)(?<=[.!?])\s+"
        sentences = [s.strip() for s in re.split(pattern, text) if s.strip()]

        if not sentences:
            sentences = [text]

        for sentence in sentences:
            wav, duration = self._tts_engine.synthesize(sentence, voice_style=style)
            data = wav.flatten()
            out = io.BytesIO()
            sf.write(out, data, 24000, format='WAV', subtype='PCM_16')
            yield out.getvalue()


class TTSManager:
    """Manages TTS providers and provides a unified interface."""

    def __init__(self):
        self._providers: dict[str, TTSProvider] = {}
        self._default: str | None = None

    def register(self, provider: TTSProvider, default: bool = False) -> None:
        self._providers[provider.name] = provider
        if default or not self._default:
            self._default = provider.name

    def get(self, name: str | None = None) -> TTSProvider | None:
        if name:
            return self._providers.get(name)
        if self._default:
            return self._providers.get(self._default)
        return None

    async def speak(self, text: str, provider: str | None = None, voice: str | None = None) -> bytes:
        """Synthesize speech using the specified or default provider."""
        p = self.get(provider)
        if not p:
            raise RuntimeError("No TTS provider available")
        return await p.synthesize(text, voice)
