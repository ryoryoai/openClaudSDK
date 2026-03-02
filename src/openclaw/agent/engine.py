"""AgentEngine: ClaudeSDKClient wrapper for sending prompts and collecting responses."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    HookMatcher,
    ResultMessage,
    SystemMessage,
    TextBlock,
)

from openclaw.agent.safety import SafetyHandler
from openclaw.config import AgentConfig, SafetyConfig

logger = logging.getLogger(__name__)


@dataclass
class AgentResponse:
    """Collected result from a single agent query."""

    text: str
    session_id: str | None = None
    cost_usd: float | None = None
    raw_messages: list[Any] = field(default_factory=list)


class AgentEngine:
    """Wraps ClaudeSDKClient to provide a simple send → collect interface."""

    def __init__(
        self,
        agent_config: AgentConfig,
        safety_config: SafetyConfig,
    ) -> None:
        self._agent_config = agent_config
        self._safety = SafetyHandler(safety_config)

    def _build_options(
        self,
        *,
        session_id: str | None = None,
        system_prompt: str | None = None,
        cwd: str | None = None,
    ) -> ClaudeAgentOptions:
        """Build ClaudeAgentOptions from config, optionally resuming a session."""
        kwargs: dict[str, Any] = {
            "model": self._agent_config.model,
            "permission_mode": self._agent_config.permission_mode,
            "max_turns": self._agent_config.max_turns,
            "max_budget_usd": self._agent_config.max_budget_usd,
            "allowed_tools": list(self._agent_config.allowed_tools),
            "hooks": {
                "PreToolUse": [
                    HookMatcher(
                        matcher="Bash|Read|Write|Edit",
                        hooks=[self._safety.pre_tool_use_hook],
                    ),
                ],
            },
        }

        if cwd:
            kwargs["cwd"] = cwd
        elif self._agent_config.cwd:
            kwargs["cwd"] = self._agent_config.cwd

        if session_id:
            kwargs["resume"] = session_id

        if system_prompt:
            kwargs["system_prompt"] = system_prompt

        return ClaudeAgentOptions(**kwargs)

    async def send_and_collect(
        self,
        prompt: str,
        *,
        session_id: str | None = None,
        system_prompt: str | None = None,
        cwd: str | None = None,
    ) -> AgentResponse:
        """Send a prompt and collect the full response.

        If *session_id* is provided the existing session is resumed,
        keeping full conversational context.
        """
        options = self._build_options(
            session_id=session_id,
            system_prompt=system_prompt,
            cwd=cwd,
        )

        text_parts: list[str] = []
        captured_session_id: str | None = session_id
        raw_messages: list[Any] = []

        async with ClaudeSDKClient(options=options) as client:
            await client.query(prompt)

            async for message in client.receive_response():
                raw_messages.append(message)

                if isinstance(message, SystemMessage) and message.subtype == "init":
                    captured_session_id = message.data.get("session_id")

                elif isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            text_parts.append(block.text)

                elif isinstance(message, ResultMessage):
                    if message.result:
                        text_parts.append(message.result)

        return AgentResponse(
            text="\n".join(text_parts) if text_parts else "(no response)",
            session_id=captured_session_id,
            raw_messages=raw_messages,
        )
