"""Slash commands: /ask, /reset, /status."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands

from openclaw.discord_adapter.formatter import split_message

if TYPE_CHECKING:
    from openclaw.agent.session import SessionManager

logger = logging.getLogger(__name__)


def register_commands(
    tree: app_commands.CommandTree,
    session_manager: SessionManager,
) -> None:
    """Register slash commands on the command tree."""

    @tree.command(name="ask", description="Ask the AI agent a question")
    @app_commands.describe(prompt="Your question or instruction")
    async def ask_command(interaction: discord.Interaction, prompt: str) -> None:
        await interaction.response.defer(thinking=True)

        try:
            response = await session_manager.query(
                user_id=interaction.user.id,
                channel_id=interaction.channel_id,
                prompt=prompt,
            )

            chunks = split_message(response.text)
            # Send the first chunk as the follow-up to the deferred interaction
            await interaction.followup.send(chunks[0])
            # Send remaining chunks as regular messages
            for chunk in chunks[1:]:
                await interaction.followup.send(chunk)

        except Exception:
            logger.exception("Error in /ask command")
            await interaction.followup.send(
                "An error occurred while processing your request."
            )

    @tree.command(name="reset", description="Reset your conversation session")
    async def reset_command(interaction: discord.Interaction) -> None:
        existed = session_manager.reset(
            interaction.user.id, interaction.channel_id
        )
        if existed:
            await interaction.response.send_message(
                "Session reset. Starting fresh!"
            )
        else:
            await interaction.response.send_message(
                "No active session to reset."
            )

    @tree.command(
        name="status", description="Show your current session status"
    )
    async def status_command(interaction: discord.Interaction) -> None:
        info = session_manager.get_info(
            interaction.user.id, interaction.channel_id
        )
        if info is None:
            await interaction.response.send_message("No active session.")
            return

        idle_min = info["idle_seconds"] // 60
        await interaction.response.send_message(
            f"**Session Status**\n"
            f"- Messages: {info['message_count']}\n"
            f"- Idle: {idle_min} min\n"
            f"- Session ID: `{info['session_id'] or 'pending'}`"
        )
