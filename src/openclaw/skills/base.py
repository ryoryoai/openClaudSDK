"""Base classes for the skill / plugin system."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class SkillMetadata:
    """Descriptive metadata for a skill."""

    name: str
    version: str
    description: str = ""
    author: str = ""


class Skill(ABC):
    """Abstract base class for OpenClaw skills.

    To create a skill, subclass this and set ``skill_class = YourSkill``
    in the package's ``__init__.py``.
    """

    @abstractmethod
    def metadata(self) -> SkillMetadata:
        """Return metadata describing this skill."""
        ...

    def tools(self) -> list[Any] | None:
        """Return MCP server parameters for tools this skill provides.

        Each item should be a ``StdioServerParameters`` or an in-process
        MCP server created via ``create_sdk_mcp_server``.
        """
        return None

    def hooks(self) -> dict[str, list[Any]] | None:
        """Return hook matchers this skill provides.

        Keys should be hook names like ``"PreToolUse"`` and values
        should be lists of ``HookMatcher`` instances.
        """
        return None

    def on_load(self, config: dict[str, Any] | None = None) -> None:
        """Called when the skill is loaded. Override for initialization."""

    def on_unload(self) -> None:
        """Called when the skill is unloaded. Override for cleanup."""
