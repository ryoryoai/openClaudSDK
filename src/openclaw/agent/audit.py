"""Audit logging: JSONL-based security audit trail."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class AuditEntry:
    """A single audit log entry."""

    timestamp: float
    user_id: int
    tool_name: str
    action: str  # "allow" or "block"
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


class AuditLogger:
    """Append-only JSONL audit logger with daily file rotation."""

    def __init__(self, log_dir: str | Path) -> None:
        self._log_dir = Path(log_dir)
        self._log_dir.mkdir(parents=True, exist_ok=True)

    def _today_path(self) -> Path:
        date_str = time.strftime("%Y-%m-%d")
        return self._log_dir / f"{date_str}.jsonl"

    def log(
        self,
        *,
        user_id: int,
        tool_name: str,
        action: str,
        reason: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Append an audit entry to today's log file."""
        entry = AuditEntry(
            timestamp=time.time(),
            user_id=user_id,
            tool_name=tool_name,
            action=action,
            reason=reason,
            metadata=metadata or {},
        )
        path = self._today_path()
        try:
            with open(path, "a") as f:
                f.write(entry.to_json() + "\n")
        except OSError:
            logger.exception("Failed to write audit log")

    def get_recent(self, max_entries: int = 20) -> list[AuditEntry]:
        """Read the most recent entries from today's log file."""
        path = self._today_path()
        if not path.exists():
            return []

        entries: list[AuditEntry] = []
        try:
            lines = path.read_text().strip().splitlines()
            for line in lines[-max_entries:]:
                data = json.loads(line)
                entries.append(AuditEntry(**data))
        except (json.JSONDecodeError, OSError, TypeError):
            logger.warning("Failed to read audit log: %s", path)

        return entries
