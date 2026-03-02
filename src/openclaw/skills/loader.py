"""Skill loader: discovers and loads skill packages from a directory."""

from __future__ import annotations

import importlib
import logging
import sys
from pathlib import Path
from typing import Any

from openclaw.skills.base import Skill

logger = logging.getLogger(__name__)


class SkillLoader:
    """Discovers and loads skills from a directory.

    Each skill is a Python package under ``skills_dir`` with a
    ``skill_class`` attribute in its ``__init__.py``.

    Example structure::

        skills/
          my_skill/
            __init__.py   # skill_class = MySkill
    """

    def __init__(
        self,
        skills_dir: str | Path,
        disabled_skills: list[str] | None = None,
    ) -> None:
        self._skills_dir = Path(skills_dir)
        self._disabled = set(disabled_skills or [])
        self._loaded: dict[str, Skill] = {}

    def load_all(self) -> list[Skill]:
        """Discover and load all valid skill packages."""
        if not self._skills_dir.is_dir():
            logger.info("Skills directory not found: %s", self._skills_dir)
            return []

        # Ensure skills_dir is importable
        skills_parent = str(self._skills_dir.parent)
        if skills_parent not in sys.path:
            sys.path.insert(0, skills_parent)

        for entry in sorted(self._skills_dir.iterdir()):
            if not entry.is_dir():
                continue
            if not (entry / "__init__.py").exists():
                continue

            skill_name = entry.name
            if skill_name in self._disabled:
                logger.info("Skipping disabled skill: %s", skill_name)
                continue

            try:
                module = importlib.import_module(
                    f"{self._skills_dir.name}.{skill_name}"
                )
                skill_cls = getattr(module, "skill_class", None)
                if skill_cls is None:
                    logger.warning(
                        "Skill %s has no skill_class attribute", skill_name
                    )
                    continue

                instance: Skill = skill_cls()
                instance.on_load()
                self._loaded[skill_name] = instance
                meta = instance.metadata()
                logger.info(
                    "Loaded skill: %s v%s", meta.name, meta.version
                )
            except Exception:
                logger.exception("Failed to load skill: %s", skill_name)

        return list(self._loaded.values())

    def get_tools(self) -> list[Any]:
        """Collect tools from all loaded skills."""
        tools: list[Any] = []
        for skill in self._loaded.values():
            skill_tools = skill.tools()
            if skill_tools:
                tools.extend(skill_tools)
        return tools

    def get_hooks(self) -> dict[str, list[Any]]:
        """Collect and merge hooks from all loaded skills."""
        merged: dict[str, list[Any]] = {}
        for skill in self._loaded.values():
            skill_hooks = skill.hooks()
            if skill_hooks:
                for hook_name, matchers in skill_hooks.items():
                    merged.setdefault(hook_name, []).extend(matchers)
        return merged

    def unload_all(self) -> None:
        """Unload all loaded skills."""
        for name, skill in self._loaded.items():
            try:
                skill.on_unload()
            except Exception:
                logger.exception("Error unloading skill: %s", name)
        self._loaded.clear()
