"""Voice listener: captures audio from Discord voice channels."""

from __future__ import annotations

import asyncio
import io
import logging
import wave
from typing import Any, Callable

import discord

logger = logging.getLogger(__name__)


class VoiceListener:
    """Listens to audio in a Discord voice channel using a Sink.

    Collects audio per-user and invokes a callback when silence is detected.
    """

    def __init__(
        self,
        voice_client: discord.VoiceClient,
        on_audio_complete: Callable[[int, bytes], Any],
        silence_timeout: float = 1.5,
    ) -> None:
        self._voice_client = voice_client
        self._on_audio_complete = on_audio_complete
        self._silence_timeout = silence_timeout
        self._listening = False
        self._user_buffers: dict[int, bytearray] = {}
        self._user_timers: dict[int, asyncio.Task[None]] = {}

    def start(self) -> None:
        """Start listening for audio in the voice channel."""
        if self._listening:
            return
        self._listening = True
        self._voice_client.start_recording(
            discord.sinks.WaveSink(),
            self._recording_finished,
            None,
        )
        logger.info("Voice listener started")

    def stop(self) -> None:
        """Stop listening for audio."""
        if not self._listening:
            return
        self._listening = False
        if self._voice_client.recording:
            self._voice_client.stop_recording()
        for timer in self._user_timers.values():
            timer.cancel()
        self._user_timers.clear()
        self._user_buffers.clear()
        logger.info("Voice listener stopped")

    async def _recording_finished(
        self,
        sink: discord.sinks.WaveSink,
        *args: Any,
    ) -> None:
        """Called when recording stops. Process captured audio per user."""
        for user_id, audio_data in sink.audio_data.items():
            audio_data.file.seek(0)
            audio_bytes = audio_data.file.read()
            if audio_bytes:
                await self._on_audio_complete(user_id, audio_bytes)
