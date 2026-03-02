"""File-based memory store for persistent agent memory."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from openclaw.memory.vector_store import VectorMemoryStore

logger = logging.getLogger(__name__)


class MemoryStore:
    """Simple file-based key-value store for agent memory.

    Each user gets a separate JSON file under ``data_dir/memory/``.
    """

    def __init__(
        self,
        data_dir: str | Path,
        vector_store: VectorMemoryStore | None = None,
    ) -> None:
        self._dir = Path(data_dir) / "memory"
        self._dir.mkdir(parents=True, exist_ok=True)
        self._vector_store = vector_store

    def _user_path(self, user_id: int) -> Path:
        return self._dir / f"user_{user_id}.json"

    def _load(self, user_id: int) -> dict[str, Any]:
        path = self._user_path(user_id)
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            logger.warning("Corrupt memory file for user %d", user_id)
            return {}

    def _save(self, user_id: int, data: dict[str, Any]) -> None:
        path = self._user_path(user_id)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2))

    def read(self, user_id: int, key: str) -> str | None:
        """Read a memory entry."""
        data = self._load(user_id)
        entry = data.get(key)
        if entry is None:
            return None
        return entry.get("value")

    def write(self, user_id: int, key: str, value: str) -> None:
        """Write or update a memory entry."""
        data = self._load(user_id)
        data[key] = {"value": value, "updated_at": time.time()}
        self._save(user_id, data)
        if self._vector_store is not None:
            try:
                self._vector_store.add(user_id, key, value)
            except Exception:
                logger.warning("Failed to sync to vector store: %s", key)

    def delete(self, user_id: int, key: str) -> bool:
        """Delete a memory entry. Returns True if it existed."""
        data = self._load(user_id)
        if key not in data:
            return False
        del data[key]
        self._save(user_id, data)
        if self._vector_store is not None:
            try:
                self._vector_store.remove(user_id, key)
            except Exception:
                logger.warning("Failed to remove from vector store: %s", key)
        return True

    def list_keys(self, user_id: int) -> list[str]:
        """List all memory keys for a user."""
        data = self._load(user_id)
        return list(data.keys())
