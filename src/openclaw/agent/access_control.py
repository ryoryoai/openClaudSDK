"""Access control: DM pairing and permission management."""

from __future__ import annotations

import json
import logging
import secrets
import time
from enum import IntEnum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class PermissionLevel(IntEnum):
    """User permission levels, ordered by access."""

    BLOCKED = 0
    PENDING = 1
    APPROVED = 2
    ADMIN = 3


class AccessController:
    """Manages user permissions with JSON persistence and approval codes."""

    def __init__(
        self,
        data_file: str | Path,
        admin_user_ids: list[int] | None = None,
        default_permission: PermissionLevel = PermissionLevel.PENDING,
    ) -> None:
        self._data_file = Path(data_file)
        self._data_file.parent.mkdir(parents=True, exist_ok=True)
        self._admin_user_ids = set(admin_user_ids or [])
        self._default_permission = default_permission
        self._data: dict[str, Any] = self._load()
        self._pending_codes: dict[str, int] = {}  # code -> user_id

    def _load(self) -> dict[str, Any]:
        if not self._data_file.exists():
            return {"users": {}}
        try:
            return json.loads(self._data_file.read_text())
        except (json.JSONDecodeError, OSError):
            logger.warning("Corrupt access control file: %s", self._data_file)
            return {"users": {}}

    def _save(self) -> None:
        self._data_file.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2)
        )

    def get_permission(self, user_id: int) -> PermissionLevel:
        """Get the permission level for a user."""
        if user_id in self._admin_user_ids:
            return PermissionLevel.ADMIN

        user_key = str(user_id)
        user_data = self._data.get("users", {}).get(user_key)
        if user_data is None:
            return self._default_permission

        return PermissionLevel(user_data.get("level", self._default_permission))

    def set_permission(self, user_id: int, level: PermissionLevel) -> None:
        """Set the permission level for a user."""
        user_key = str(user_id)
        users = self._data.setdefault("users", {})
        users[user_key] = {
            "level": int(level),
            "updated_at": time.time(),
        }
        self._save()

    def generate_code(self, user_id: int) -> str:
        """Generate a one-time approval code for a user."""
        code = secrets.token_hex(4)  # 8-char hex code
        self._pending_codes[code] = user_id
        return code

    def verify_code(self, code: str, user_id: int) -> bool:
        """Verify and consume an approval code. Returns True if valid."""
        expected_user_id = self._pending_codes.get(code)
        if expected_user_id is None or expected_user_id != user_id:
            return False
        del self._pending_codes[code]
        self.set_permission(user_id, PermissionLevel.APPROVED)
        return True

    def is_admin(self, user_id: int) -> bool:
        """Check if a user is an admin."""
        return self.get_permission(user_id) == PermissionLevel.ADMIN

    def list_users(self) -> dict[str, dict[str, Any]]:
        """Return all registered users and their permissions."""
        return dict(self._data.get("users", {}))
