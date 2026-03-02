"""Text-to-Speech synthesis using OpenAI TTS API."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

try:
    from openai import AsyncOpenAI

    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False


class Synthesizer:
    """Synthesizes text to audio using OpenAI TTS API."""

    def __init__(
        self,
        model: str = "tts-1",
        voice: str = "alloy",
    ) -> None:
        if not OPENAI_AVAILABLE:
            raise ImportError(
                "openai is required for voice synthesis. "
                "Install it with: pip install openai>=1.0.0"
            )
        self._client = AsyncOpenAI()
        self._model = model
        self._voice = voice

    async def synthesize(self, text: str) -> bytes:
        """Convert text to audio bytes (opus format)."""
        response = await self._client.audio.speech.create(
            model=self._model,
            voice=self._voice,
            input=text,
            response_format="opus",
        )
        return response.content
