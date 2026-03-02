"""Slash commands: /ask, /reset, /status, /audit, /health, /approve, /deny, /revoke, /voice-join, /voice-leave."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands

from openclaw.discord_adapter.formatter import split_message

if TYPE_CHECKING:
    from openclaw.agent.access_control import AccessController
    from openclaw.agent.audit import AuditLogger
    from openclaw.agent.health import HealthMonitor
    from openclaw.agent.session import SessionManager
    from openclaw.voice.handler import VoiceHandler

logger = logging.getLogger(__name__)


def register_commands(
    tree: app_commands.CommandTree,
    session_manager: SessionManager,
    *,
    audit_logger: AuditLogger | None = None,
    health_monitor: HealthMonitor | None = None,
    access_controller: AccessController | None = None,
    voice_handler: VoiceHandler | None = None,
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

    # --- Audit log command ---
    if audit_logger is not None:

        @tree.command(name="audit", description="Show recent audit log entries")
        async def audit_command(interaction: discord.Interaction) -> None:
            entries = audit_logger.get_recent()
            if not entries:
                await interaction.response.send_message("No audit entries found.")
                return

            embed = discord.Embed(
                title="Audit Log",
                color=discord.Color.orange(),
            )
            for entry in entries[-10:]:
                import time as _time

                ts = _time.strftime("%H:%M:%S", _time.localtime(entry.timestamp))
                icon = "\u2705" if entry.action == "allow" else "\u274c"
                embed.add_field(
                    name=f"{icon} {ts} — {entry.tool_name}",
                    value=entry.reason or "Allowed",
                    inline=False,
                )

            await interaction.response.send_message(embed=embed)

    # --- Health check command ---
    if health_monitor is not None:

        @tree.command(name="health", description="Show bot health status")
        async def health_command(interaction: discord.Interaction) -> None:
            stats = health_monitor.get_stats()
            uptime_h = stats["uptime_seconds"] / 3600

            embed = discord.Embed(
                title="Bot Health",
                color=discord.Color.green()
                if stats["error_rate"] < 0.1
                else discord.Color.red(),
            )
            embed.add_field(name="Uptime", value=f"{uptime_h:.1f}h", inline=True)
            embed.add_field(
                name="Total Requests",
                value=str(stats["total_requests"]),
                inline=True,
            )
            embed.add_field(
                name="Avg Response",
                value=f"{stats['avg_response_ms']:.0f}ms",
                inline=True,
            )
            embed.add_field(
                name="Error Rate",
                value=f"{stats['error_rate']:.1%}",
                inline=True,
            )
            if stats["recent_errors"]:
                embed.add_field(
                    name="Recent Errors",
                    value="\n".join(stats["recent_errors"][-3:]),
                    inline=False,
                )
            await interaction.response.send_message(embed=embed)

    # --- Access control commands ---
    if access_controller is not None:

        @tree.command(
            name="approve",
            description="Approve access with a verification code",
        )
        @app_commands.describe(code="The verification code you received")
        async def approve_command(
            interaction: discord.Interaction, code: str
        ) -> None:
            if access_controller.verify_code(code, interaction.user.id):
                await interaction.response.send_message(
                    "Access approved! You can now use the bot."
                )
            else:
                await interaction.response.send_message(
                    "Invalid or expired code.", ephemeral=True
                )

        @tree.command(
            name="deny",
            description="[Admin] Block a user from accessing the bot",
        )
        @app_commands.describe(user="The user to block")
        async def deny_command(
            interaction: discord.Interaction, user: discord.User
        ) -> None:
            if not access_controller.is_admin(interaction.user.id):
                await interaction.response.send_message(
                    "You do not have permission to use this command.",
                    ephemeral=True,
                )
                return

            from openclaw.agent.access_control import PermissionLevel

            access_controller.set_permission(user.id, PermissionLevel.BLOCKED)
            await interaction.response.send_message(
                f"User {user.display_name} has been blocked."
            )

        @tree.command(
            name="revoke",
            description="[Admin] Revoke a user's approval",
        )
        @app_commands.describe(user="The user to revoke")
        async def revoke_command(
            interaction: discord.Interaction, user: discord.User
        ) -> None:
            if not access_controller.is_admin(interaction.user.id):
                await interaction.response.send_message(
                    "You do not have permission to use this command.",
                    ephemeral=True,
                )
                return

            from openclaw.agent.access_control import PermissionLevel

            access_controller.set_permission(user.id, PermissionLevel.PENDING)
            await interaction.response.send_message(
                f"User {user.display_name}'s access has been revoked."
            )

    # --- Voice commands ---
    if voice_handler is not None:

        @tree.command(
            name="voice-join",
            description="Join your voice channel",
        )
        async def voice_join_command(interaction: discord.Interaction) -> None:
            if not isinstance(interaction.user, discord.Member):
                await interaction.response.send_message(
                    "This command can only be used in a server.",
                    ephemeral=True,
                )
                return

            voice_state = interaction.user.voice
            if voice_state is None or voice_state.channel is None:
                await interaction.response.send_message(
                    "You need to be in a voice channel first.",
                    ephemeral=True,
                )
                return

            await interaction.response.defer()
            await voice_handler.join(voice_state.channel)
            await interaction.followup.send(
                f"Joined **{voice_state.channel.name}**. Listening..."
            )

        @tree.command(
            name="voice-leave",
            description="Leave the voice channel",
        )
        async def voice_leave_command(
            interaction: discord.Interaction,
        ) -> None:
            if interaction.guild is None:
                await interaction.response.send_message(
                    "This command can only be used in a server.",
                    ephemeral=True,
                )
                return

            left = await voice_handler.leave(interaction.guild.id)
            if left:
                await interaction.response.send_message(
                    "Left the voice channel."
                )
            else:
                await interaction.response.send_message(
                    "Not connected to a voice channel.", ephemeral=True
                )
