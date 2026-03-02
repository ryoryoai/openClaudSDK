"""Speech-to-Text transcription using OpenAI Whisper API."""

from __future__ import annotations

import io
import logging

logger = logging.getLogger(__name__)

try:
    from openai import AsyncOpenAI

    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False


class Transcriber:
    """Transcribes audio bytes to text using OpenAI Whisper API."""

    def __init__(self, model: str = "whisper-1") -> None:
        if not OPENAI_AVAILABLE:
            raise ImportError(
                "openai is required for voice transcription. "
                "Install it with: pip install openai>=1.0.0"
            )
        self._client = AsyncOpenAI()
        self._model = model

    async def transcribe(self, audio_bytes: bytes) -> str:
        """Transcribe audio bytes (WAV format) to text."""
        audio_file = io.BytesIO(audio_bytes)
        audio_file.name = "audio.wav"

        transcript = await self._client.audio.transcriptions.create(
            model=self._model,
            file=audio_file,
        )
        return transcript.text
