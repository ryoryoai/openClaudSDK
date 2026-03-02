"""Voice handler: STT -> Agent -> TTS -> playback pipeline."""

from __future__ import annotations

import asyncio
import io
import logging
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

import discord

from openclaw.voice.listener import VoiceListener
from openclaw.voice.synthesizer import Synthesizer
from openclaw.voice.transcriber import Transcriber

if TYPE_CHECKING:
    from openclaw.agent.session import SessionManager

logger = logging.getLogger(__name__)


class VoiceHandler:
    """Manages the voice pipeline: listen -> transcribe -> agent -> speak."""

    def __init__(
        self,
        session_manager: SessionManager,
        stt_model: str = "whisper-1",
        tts_model: str = "tts-1",
        tts_voice: str = "alloy",
        silence_timeout: float = 1.5,
    ) -> None:
        self._session_manager = session_manager
        self._transcriber = Transcriber(model=stt_model)
        self._synthesizer = Synthesizer(model=tts_model, voice=tts_voice)
        self._silence_timeout = silence_timeout
        self._active_connections: dict[int, VoiceListener] = {}  # guild_id -> listener

    async def join(
        self,
        channel: discord.VoiceChannel,
    ) -> discord.VoiceClient:
        """Join a voice channel and start listening."""
        guild_id = channel.guild.id

        if guild_id in self._active_connections:
            self._active_connections[guild_id].stop()

        voice_client = await channel.connect()
        listener = VoiceListener(
            voice_client=voice_client,
            on_audio_complete=self._handle_audio,
            silence_timeout=self._silence_timeout,
        )
        listener.start()
        self._active_connections[guild_id] = listener
        logger.info("Joined voice channel: %s", channel.name)
        return voice_client

    async def leave(self, guild_id: int) -> bool:
        """Leave the voice channel for a guild. Returns True if was connected."""
        listener = self._active_connections.pop(guild_id, None)
        if listener is None:
            return False

        listener.stop()
        voice_client = listener._voice_client
        if voice_client.is_connected():
            await voice_client.disconnect()
        logger.info("Left voice channel in guild %d", guild_id)
        return True

    async def _handle_audio(self, user_id: int, audio_bytes: bytes) -> None:
        """Process captured audio: STT -> Agent -> TTS -> playback."""
        try:
            text = await self._transcriber.transcribe(audio_bytes)
            if not text.strip():
                return
            logger.info("Transcribed from user %d: %s", user_id, text[:80])

            # Find the voice client for this user's guild
            voice_client = self._find_voice_client(user_id)
            if voice_client is None:
                return

            # Send to agent (use guild channel id for session)
            response = await self._session_manager.query(
                user_id=user_id,
                channel_id=voice_client.channel.id,
                prompt=text,
            )

            # Synthesize response
            audio_out = await self._synthesizer.synthesize(response.text)

            # Play audio response
            await self._play_audio(voice_client, audio_out)

        except Exception:
            logger.exception("Error in voice pipeline for user %d", user_id)

    def _find_voice_client(self, user_id: int) -> discord.VoiceClient | None:
        """Find the voice client where this user is connected."""
        for listener in self._active_connections.values():
            vc = listener._voice_client
            if vc.is_connected():
                return vc
        return None

    async def _play_audio(
        self,
        voice_client: discord.VoiceClient,
        audio_bytes: bytes,
    ) -> None:
        """Play audio bytes through the voice client."""
        with tempfile.NamedTemporaryFile(suffix=".opus", delete=False) as f:
            f.write(audio_bytes)
            tmp_path = f.name

        try:
            source = discord.FFmpegOpusAudio(tmp_path)
            if voice_client.is_playing():
                voice_client.stop()
            voice_client.play(source)
            while voice_client.is_playing():
                await asyncio.sleep(0.1)
        finally:
            Path(tmp_path).unlink(missing_ok=True)
