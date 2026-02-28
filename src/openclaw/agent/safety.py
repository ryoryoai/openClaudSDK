"""Safety handler: PreToolUse hook that blocks dangerous commands and paths."""

from __future__ import annotations

import logging
import re
from typing import Any

from openclaw.config import SafetyConfig

logger = logging.getLogger(__name__)


class SafetyHandler:
    """Block dangerous Bash commands and file-system access via PreToolUse hook."""

    def __init__(self, config: SafetyConfig) -> None:
        self._blocked_commands = [
            re.compile(pattern) for pattern in config.blocked_commands
        ]
        self._blocked_paths = list(config.blocked_paths)

    def _is_command_blocked(self, command: str) -> str | None:
        """Return the matched pattern string if the command is blocked."""
        for pattern in self._blocked_commands:
            if pattern.search(command):
                return pattern.pattern
        return None

    def _is_path_blocked(self, path: str) -> bool:
        """Check whether a file path falls under a blocked directory."""
        for blocked in self._blocked_paths:
            if path == blocked or path.startswith(blocked + "/"):
                return True
        return False

    async def pre_tool_use_hook(
        self,
        input_data: dict[str, Any],
        tool_use_id: str,
        context: Any,
    ) -> dict[str, Any]:
        """PreToolUse hook callback for ClaudeAgentOptions.

        Returns an empty dict to allow, or a dict with ``"decision": "block"``
        and ``"reason"`` to reject the tool call.
        """
        tool_input = input_data.get("tool_input", {})
        tool_name = input_data.get("tool_name", "")

        # --- Bash command check ---
        if tool_name == "Bash":
            command = tool_input.get("command", "")
            matched = self._is_command_blocked(command)
            if matched:
                reason = f"Blocked dangerous command (matched: {matched})"
                logger.warning("SAFETY BLOCK: %s — %s", reason, command[:120])
                return {"decision": "block", "reason": reason}

        # --- File path check (Read / Write / Edit) ---
        if tool_name in ("Read", "Write", "Edit"):
            file_path = tool_input.get("file_path", "")
            if self._is_path_blocked(file_path):
                reason = f"Blocked access to protected path: {file_path}"
                logger.warning("SAFETY BLOCK: %s", reason)
                return {"decision": "block", "reason": reason}

        return {}
