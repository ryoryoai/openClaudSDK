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

        # Enable voice intents if voice is enabled
        if config.voice.enabled:
            intents.voice_states = True

        super().__init__(intents=intents)

        self._config = config
        self.tree = app_commands.CommandTree(self)

        # --- Optional subsystems ---

        # Audit logger
        self._audit_logger = None
        if config.audit.enabled:
            from openclaw.agent.audit import AuditLogger

            self._audit_logger = AuditLogger(config.audit.log_dir)
            logger.info("Audit logging enabled: %s", config.audit.log_dir)

        # Safety handler (with optional audit)
        from openclaw.agent.safety import SafetyHandler

        safety_handler = SafetyHandler(
            config.safety, audit_logger=self._audit_logger
        )

        # Skill loader
        self._skill_loader = None
        skill_tools: list = []
        skill_hooks: dict = {}
        if config.skills.enabled:
            from openclaw.skills.loader import SkillLoader

            self._skill_loader = SkillLoader(
                config.skills.skills_dir,
                disabled_skills=config.skills.disabled_skills,
            )
            self._skill_loader.load_all()
            skill_tools = self._skill_loader.get_tools()
            skill_hooks = self._skill_loader.get_hooks()
            logger.info("Skills system enabled: %s", config.skills.skills_dir)

        # Agent engine (with safety + skills)
        self._engine = AgentEngine(
            config.agent,
            config.safety,
            safety_handler=safety_handler,
            skill_tools=skill_tools or None,
            skill_hooks=skill_hooks or None,
        )

        # Health monitor
        self._health_monitor = None
        if config.health.enabled:
            from openclaw.agent.health import HealthMonitor

            self._health_monitor = HealthMonitor()
            logger.info("Health monitoring enabled")

        # Session manager (with optional health monitor)
        self._session_manager = SessionManager(
            config, self._engine, health_monitor=self._health_monitor
        )

        # Access controller
        self._access_controller = None
        if config.access_control.enabled:
            from openclaw.agent.access_control import (
                AccessController,
                PermissionLevel,
            )

            self._access_controller = AccessController(
                data_file=config.access_control.data_file,
                admin_user_ids=config.access_control.admin_user_ids,
                default_permission=PermissionLevel(
                    config.access_control.default_permission
                ),
            )
            logger.info("Access control enabled")

        # Vector memory store
        self._vector_store = None
        if config.memory.vector_enabled:
            try:
                from openclaw.memory.vector_store import VectorMemoryStore

                self._vector_store = VectorMemoryStore(
                    data_dir=config.memory.data_dir,
                    collection_name=config.memory.vector_collection_name,
                )
                logger.info("Vector memory enabled")
            except ImportError:
                logger.warning(
                    "chromadb not installed — vector memory disabled"
                )

        # Voice handler
        self._voice_handler = None
        if config.voice.enabled:
            try:
                from openclaw.voice.handler import VoiceHandler

                self._voice_handler = VoiceHandler(
                    session_manager=self._session_manager,
                    stt_model=config.voice.stt_model,
                    tts_model=config.voice.tts_model,
                    tts_voice=config.voice.tts_voice,
                    silence_timeout=config.voice.silence_timeout_seconds,
                )
                logger.info("Voice support enabled")
            except ImportError:
                logger.warning(
                    "openai or discord.py[voice] not installed — voice disabled"
                )

        self._handler: MessageHandler | None = None
        self._ready = False

    async def setup_hook(self) -> None:
        """Called once when the bot connects — register commands and start cleanup."""
        register_commands(
            self.tree,
            self._session_manager,
            audit_logger=self._audit_logger,
            health_monitor=self._health_monitor,
            access_controller=self._access_controller,
            voice_handler=self._voice_handler,
        )
        await self.tree.sync()
        logger.info("Slash commands synced")

        self._session_manager.start_cleanup_loop()
        logger.info("Session cleanup loop started")

    async def on_ready(self) -> None:
        assert self.user is not None
        logger.info("Logged in as %s (id=%s)", self.user, self.user.id)

        # Create handler only once — on_ready can fire multiple times on reconnect
        if self._handler is None:
            self._handler = MessageHandler(
                self._config,
                self._session_manager,
                bot_user_id=self.user.id,
                access_controller=self._access_controller,
            )
        self._ready = True

    async def on_message(self, message: discord.Message) -> None:
        if self._handler is None:
            return
        if not self._handler.should_handle(message):
            return
        await self._handler.handle(message)

    async def close(self) -> None:
        if self._skill_loader is not None:
            self._skill_loader.unload_all()
        await self._session_manager.close()
        await super().close()


def create_bot(config: AppConfig) -> OpenClawBot:
    """Factory that builds a ready-to-run bot."""
    return OpenClawBot(config)
