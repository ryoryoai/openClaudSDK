"""Discord bot setup and lifecycle."""

from __future__ import annotations

import logging

import discord
from discord import app_commands

from openclaw.agent.engine import AgentEngine
from openclaw.agent.session import SessionManager
from openclaw.config import AppConfig
from openclaw.discord_adapter.commands import register_commands
from openclaw.discord_adapter.message_handler import MessageHandler

logger = logging.getLogger(__name__)


class OpenClawBot(discord.Client):
    """Discord client that wires up the agent engine and message handling."""

    def __init__(self, config: AppConfig) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        intents.messages = True
        super().__init__(intents=intents)

        self._config = config
        self.tree = app_commands.CommandTree(self)

        # Agent layer
        self._engine = AgentEngine(config.agent, config.safety)
        self._session_manager = SessionManager(config, self._engine)
        self._handler: MessageHandler | None = None

    async def setup_hook(self) -> None:
        """Called once when the bot connects — register commands and start cleanup."""
        register_commands(self.tree, self._session_manager)
        await self.tree.sync()
        logger.info("Slash commands synced")

        self._session_manager.start_cleanup_loop()
        logger.info("Session cleanup loop started")

    async def on_ready(self) -> None:
        assert self.user is not None
        logger.info("Logged in as %s (id=%s)", self.user, self.user.id)

        self._handler = MessageHandler(
            self._config,
            self._session_manager,
            bot_user_id=self.user.id,
        )

    async def on_message(self, message: discord.Message) -> None:
        if self._handler is None:
            return
        if not self._handler.should_handle(message):
            return
        await self._handler.handle(message)

    async def close(self) -> None:
        await self._session_manager.close()
        await super().close()


def create_bot(config: AppConfig) -> OpenClawBot:
    """Factory that builds a ready-to-run bot."""
    return OpenClawBot(config)
