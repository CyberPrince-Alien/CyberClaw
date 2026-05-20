"""Wake word detection for voice mode."""

import asyncio
import logging
from typing import Callable, Awaitable

logger = logging.getLogger(__name__)


class WakeWordDetector:
    """Detects wake words via openwakeword or keyboard fallback."""

    def __init__(self, wake_words: list[str] | None = None, sensitivity: float = 0.5):
        self.wake_words = wake_words or ["hey cyberclaw", "hey cyber claw"]
        self.sensitivity = sensitivity
        self._running = False

    async def start_listening(self, on_wake: Callable[[], Awaitable[None]]) -> None:
        """Start listening. Tries openwakeword, falls back to keyboard."""
        try:
            await self._listen_oww(on_wake)
        except ImportError:
            logger.info("openwakeword not available, using keyboard fallback")
            await self._listen_keyboard(on_wake)

    async def _listen_oww(self, on_wake: Callable[[], Awaitable[None]]) -> None:
        import openwakeword
        from openwakeword.model import Model
        import pyaudio
        import numpy as np

        openwakeword.utils.download_models()
        oww = Model(inference_framework="onnx")
        pa = pyaudio.PyAudio()
        stream = pa.open(format=pyaudio.paInt16, channels=1, rate=16000, input=True, frames_per_buffer=1280)
        self._running = True
        logger.info("Wake word active (openwakeword)")
        try:
            while self._running:
                data = await asyncio.to_thread(stream.read, 1280)
                arr = np.frombuffer(data, dtype=np.int16)
                oww.predict(arr)
                for name in oww.prediction_buffer:
                    scores = list(oww.prediction_buffer[name])
                    if scores and max(scores[-3:]) > self.sensitivity:
                        oww.reset()
                        await on_wake()
        finally:
            stream.stop_stream()
            stream.close()
            pa.terminate()

    async def _listen_keyboard(self, on_wake: Callable[[], Awaitable[None]]) -> None:
        logger.info("Wake word: press Enter to activate")
        self._running = True
        while self._running:
            await asyncio.to_thread(input, "")
            await on_wake()

    def stop(self):
        self._running = False
