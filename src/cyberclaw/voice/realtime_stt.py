"""Realtime Transcription -- WebSocket-based live speech-to-text."""

import asyncio, json, logging
from dataclasses import dataclass
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)

@dataclass
class TranscriptSegment:
    text: str; is_final: bool = False; confidence: float = 0.0; timestamp: float = 0.0

class RealtimeTranscriptionSession:
    """WebSocket-based realtime STT session."""
    def __init__(self, provider: str = "deepgram", api_key: str = "",
                 language: str = "en", model: str = "nova-2"):
        self.provider = provider; self.api_key = api_key
        self.language = language; self.model = model
        self._ws = None; self._running = False

    async def start(self, on_transcript: Callable[[TranscriptSegment], Awaitable[None]]) -> None:
        if self.provider == "deepgram":
            await self._start_deepgram(on_transcript)
        else:
            raise ValueError(f"Unknown provider: {self.provider}")

    async def _start_deepgram(self, on_transcript):
        try:
            import websockets
        except ImportError:
            logger.error("websockets not installed"); return

        url = (f"wss://api.deepgram.com/v1/listen?"
               f"model={self.model}&language={self.language}&punctuate=true&interim_results=true")
        headers = {"Authorization": f"Token {self.api_key}"}
        self._running = True
        async with websockets.connect(url, extra_headers=headers) as ws:
            self._ws = ws
            async for message in ws:
                if not self._running: break
                try:
                    data = json.loads(message)
                    channel = data.get("channel", {})
                    alternatives = channel.get("alternatives", [{}])
                    if alternatives:
                        alt = alternatives[0]
                        text = alt.get("transcript", "")
                        if text:
                            segment = TranscriptSegment(
                                text=text, is_final=data.get("is_final", False),
                                confidence=alt.get("confidence", 0))
                            await on_transcript(segment)
                except Exception as e:
                    logger.warning("Transcription parse error: %s", e)

    async def send_audio(self, audio_bytes: bytes) -> None:
        if self._ws: await self._ws.send(audio_bytes)

    async def stop(self) -> None:
        self._running = False
        if self._ws:
            try: await self._ws.send(json.dumps({"type": "CloseStream"}))
            except Exception: pass

class RealtimeTranscriptionManager:
    """Manages transcription sessions."""
    def __init__(self):
        self._sessions: dict[str, RealtimeTranscriptionSession] = {}

    def create_session(self, session_id: str, provider: str = "deepgram",
                       api_key: str = "") -> RealtimeTranscriptionSession:
        session = RealtimeTranscriptionSession(provider=provider, api_key=api_key)
        self._sessions[session_id] = session; return session

    def get_session(self, session_id: str) -> RealtimeTranscriptionSession | None:
        return self._sessions.get(session_id)

    async def close_session(self, session_id: str):
        session = self._sessions.pop(session_id, None)
        if session: await session.stop()
