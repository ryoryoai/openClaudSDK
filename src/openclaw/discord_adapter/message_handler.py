"""Message handler: routes DMs and @mentions to the agent."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import discord

from openclaw.discord_adapter.formatter import split_message

if TYPE_CHECKING:
    from openclaw.agent.access_control import AccessController
    from openclaw.agent.session import SessionManager
    from openclaw.config import AppConfig

logger = logging.getLogger(__name__)


class MessageHandler:
    """Routes incoming Discord messages to the agent and sends responses."""

    def __init__(
        self,
        config: AppConfig,
        session_manager: SessionManager,
        bot_user_id: int,
        access_controller: AccessController | None = None,
    ) -> None:
        self._config = config
        self._sessions = session_manager
        self._bot_user_id = bot_user_id
        self._access_controller = access_controller
        self._processing: set[str] = set()  # prevent concurrent per-user+channel

    def should_handle(self, message: discord.Message) -> bool:
        """Decide whether this message should be handled."""
        if message.author.bot:
            return False

        # DM — always respond
        if isinstance(message.channel, discord.DMChannel):
            return True

        # Server channel — respond only to @mentions
        if self._bot_user_id in [u.id for u in message.mentions]:
            # Check allowed channels
            allowed = self._config.discord.allowed_channel_ids
            if allowed and message.channel.id not in allowed:
                return False
            return True

        return False

    async def handle(self, message: discord.Message) -> None:
        """Process the message and reply."""
        key = f"{message.author.id}:{message.channel.id}"

        # Prevent concurrent processing for the same user+channel
        if key in self._processing:
            await message.reply("Previous request is still processing...")
            return
        self._processing.add(key)

        try:
            await self._process(message)
        finally:
            self._processing.discard(key)

    async def _process(self, message: discord.Message) -> None:
        # Access control check
        if self._access_controller is not None:
            from openclaw.agent.access_control import PermissionLevel

            perm = self._access_controller.get_permission(message.author.id)
            if perm == PermissionLevel.BLOCKED:
                await message.reply("You do not have access to this bot.")
                return
            if perm < PermissionLevel.APPROVED:
                code = self._access_controller.generate_code(message.author.id)
                await message.reply(
                    f"Access pending approval. Use `/approve {code}` to verify."
                )
                return

        # Strip the bot mention from the prompt
        prompt = message.content
        for mention in message.mentions:
            if mention.id == self._bot_user_id:
                prompt = prompt.replace(f"<@{mention.id}>", "").strip()
                prompt = prompt.replace(f"<@!{mention.id}>", "").strip()

        if not prompt:
            await message.reply("Please provide a message.")
            return

        # Check session limit
        max_sessions = self._config.session.max_sessions_per_user
        current_count = self._sessions.user_session_count(message.author.id)
        session_info = self._sessions.get_info(
            message.author.id, message.channel.id
        )
        if session_info is None and current_count >= max_sessions:
            await message.reply(
                f"You have reached the maximum of {max_sessions} active sessions. "
                "Use `/reset` to free one."
            )
            return

        # Show typing indicator while processing
        async with message.channel.typing():
            response = await self._sessions.query(
                user_id=message.author.id,
                channel_id=message.channel.id,
                prompt=prompt,
            )

        # Decide where to send the response
        reply_target = await self._get_reply_target(message)

        # Split and send
        chunks = split_message(response.text)
        for chunk in chunks:
            await reply_target.send(chunk)

    async def _get_reply_target(
        self, message: discord.Message
    ) -> discord.abc.Messageable:
        """Return the target channel/thread to send the response to."""
        # DM — reply directly
        if isinstance(message.channel, discord.DMChannel):
            return message.channel

        # Server channel with thread mode enabled
        if self._config.discord.thread_mode and isinstance(
            message.channel, discord.TextChannel
        ):
            # If already in a thread, reuse it
            if isinstance(message.channel, discord.Thread):
                return message.channel

            # Create a new thread from the message
            thread_name = message.content[:80] or "Agent conversation"
            thread = await message.create_thread(
                name=thread_name, auto_archive_duration=60
            )
            return thread

        # Fallback: reply in the same channel
        return message.channel
