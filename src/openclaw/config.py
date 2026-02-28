"""YAML configuration loader with environment variable expansion."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


def _expand_env_vars(value: Any) -> Any:
    """Recursively expand ${VAR} references in string values."""
    if isinstance(value, str):
        return re.sub(
            r"\$\{(\w+)\}",
            lambda m: os.environ.get(m.group(1), m.group(0)),
            value,
        )
    if isinstance(value, dict):
        return {k: _expand_env_vars(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env_vars(v) for v in value]
    return value


@dataclass
class AgentConfig:
    model: str = "claude-sonnet-4-6"
    permission_mode: str = "acceptEdits"
    max_turns: int = 25
    max_budget_usd: float = 1.0
    cwd: str = "."
    allowed_tools: list[str] = field(
        default_factory=lambda: [
            "Read", "Write", "Edit", "Bash", "Glob", "Grep",
            "WebSearch", "WebFetch",
        ]
    )


@dataclass
class SafetyConfig:
    blocked_commands: list[str] = field(
        default_factory=lambda: [
            r"rm\s+-rf\s+/",
            r"sudo\s+",
            r"curl.*\|\s*sh",
            r":\(\)\{.*\}",
        ]
    )
    blocked_paths: list[str] = field(
        default_factory=lambda: ["/etc", "/usr", "/System", "/var"]
    )


@dataclass
class DiscordConfig:
    token: str = ""
    allowed_channel_ids: list[int] = field(default_factory=list)
    thread_mode: bool = True


@dataclass
class MemoryConfig:
    data_dir: str = "./data"


@dataclass
class SessionConfig:
    idle_timeout_minutes: int = 30
    max_sessions_per_user: int = 3


@dataclass
class AppConfig:
    agent: AgentConfig = field(default_factory=AgentConfig)
    safety: SafetyConfig = field(default_factory=SafetyConfig)
    discord: DiscordConfig = field(default_factory=DiscordConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    session: SessionConfig = field(default_factory=SessionConfig)


def load_config(path: str | Path = "config.yaml") -> AppConfig:
    """Load configuration from a YAML file, expanding environment variables."""
    path = Path(path)
    if not path.exists():
        return AppConfig()

    with open(path) as f:
        raw = yaml.safe_load(f) or {}

    raw = _expand_env_vars(raw)

    cfg = AppConfig()

    if "agent" in raw:
        cfg.agent = AgentConfig(**{
            k: v for k, v in raw["agent"].items()
            if k in AgentConfig.__dataclass_fields__
        })

    if "safety" in raw:
        cfg.safety = SafetyConfig(**{
            k: v for k, v in raw["safety"].items()
            if k in SafetyConfig.__dataclass_fields__
        })

    if "discord" in raw:
        d = raw["discord"]
        cfg.discord = DiscordConfig(
            token=d.get("token", ""),
            allowed_channel_ids=[
                int(cid) for cid in d.get("allowed_channel_ids", []) if cid
            ],
            thread_mode=d.get("thread_mode", True),
        )

    if "memory" in raw:
        cfg.memory = MemoryConfig(**{
            k: v for k, v in raw["memory"].items()
            if k in MemoryConfig.__dataclass_fields__
        })

    if "session" in raw:
        cfg.session = SessionConfig(**{
            k: v for k, v in raw["session"].items()
            if k in SessionConfig.__dataclass_fields__
        })

    return cfg
