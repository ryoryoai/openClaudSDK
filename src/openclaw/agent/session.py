"""Session manager: per user+channel session isolation with persistence."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from openclaw.agent.engine import AgentEngine, AgentResponse
from openclaw.agent.health import HealthMonitor
from openclaw.config import AppConfig

logger = logging.getLogger(__name__)


@dataclass
class Session:
    """Represents a single agent conversation session."""

    session_id: str | None = None
    created_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)
    message_count: int = 0


def _session_key(user_id: int, channel_id: int) -> str:
    return f"{user_id}:{channel_id}"


class SessionManager:
    """Manage per-user-per-channel sessions with persistence and idle cleanup."""

    def __init__(
        self,
        config: AppConfig,
        engine: AgentEngine,
        health_monitor: HealthMonitor | None = None,
    ) -> None:
        self._config = config
        self._engine = engine
        self._health_monitor = health_monitor
        self._sessions: dict[str, Session] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._sessions_dir = Path(config.memory.data_dir) / "sessions"
        self._sessions_dir.mkdir(parents=True, exist_ok=True)
        self._cleanup_task: asyncio.Task[None] | None = None

    # --- public API ---

    async def query(
        self,
        user_id: int,
        channel_id: int,
        prompt: str,
        *,
        system_prompt: str | None = None,
    ) -> AgentResponse:
        """Send a prompt within the user's session, creating one if needed."""
        key = _session_key(user_id, channel_id)
        lock = self._locks.setdefault(key, asyncio.Lock())

        async with lock:
            session = self._get_or_create(key)

            start_time = time.time()
            error_message = ""
            success = True

            try:
                response = await self._engine.send_and_collect(
                    prompt,
                    session_id=session.session_id,
                    system_prompt=system_prompt,
                )
            except Exception as exc:
                success = False
                error_message = str(exc)
                raise
            finally:
                if self._health_monitor is not None:
                    duration_ms = (time.time() - start_time) * 1000
                    self._health_monitor.record(
                        user_id=user_id,
                        duration_ms=duration_ms,
                        success=success,
                        error_message=error_message,
                    )

            # Update session state
            if response.session_id:
                session.session_id = response.session_id
            session.last_active = time.time()
            session.message_count += 1
            self._persist(key, session)

            return response

    def reset(self, user_id: int, channel_id: int) -> bool:
        """Reset (delete) a session. Returns True if one existed."""
        key = _session_key(user_id, channel_id)
        if key in self._sessions:
            del self._sessions[key]
            self._delete_persisted(key)
            return True
        return False

    def get_info(self, user_id: int, channel_id: int) -> dict[str, Any] | None:
        """Return session metadata, or None if no session exists."""
        key = _session_key(user_id, channel_id)
        session = self._sessions.get(key)
        if session is None:
            return None
        return {
            "session_id": session.session_id,
            "message_count": session.message_count,
            "idle_seconds": int(time.time() - session.last_active),
        }

    def user_session_count(self, user_id: int) -> int:
        """Count active sessions for a user across all channels."""
        prefix = f"{user_id}:"
        return sum(1 for k in self._sessions if k.startswith(prefix))

    # --- lifecycle ---

    def start_cleanup_loop(self) -> None:
        """Start the background task that evicts idle sessions."""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def close(self) -> None:
        """Cancel the cleanup loop."""
        if self._cleanup_task is not None:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

    # --- internals ---

    def _get_or_create(self, key: str) -> Session:
        if key not in self._sessions:
            # Try loading from disk
            session = self._load_persisted(key)
            if session is None:
                session = Session()
            self._sessions[key] = session
        return self._sessions[key]

    def _persist(self, key: str, session: Session) -> None:
        path = self._sessions_dir / f"{key.replace(':', '_')}.json"
        data = {
            "session_id": session.session_id,
            "created_at": session.created_at,
            "last_active": session.last_active,
            "message_count": session.message_count,
        }
        path.write_text(json.dumps(data))

    def _load_persisted(self, key: str) -> Session | None:
        path = self._sessions_dir / f"{key.replace(':', '_')}.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text())
            return Session(
                session_id=data.get("session_id"),
                created_at=data.get("created_at", time.time()),
                last_active=data.get("last_active", time.time()),
                message_count=data.get("message_count", 0),
            )
        except (json.JSONDecodeError, KeyError):
            logger.warning("Corrupt session file: %s", path)
            return None

    def _delete_persisted(self, key: str) -> None:
        path = self._sessions_dir / f"{key.replace(':', '_')}.json"
        path.unlink(missing_ok=True)

    async def _cleanup_loop(self) -> None:
        """Periodically evict sessions that have been idle too long."""
        timeout = self._config.session.idle_timeout_minutes * 60
        while True:
            await asyncio.sleep(60)
            now = time.time()
            stale_keys = [
                k
                for k, s in self._sessions.items()
                if (now - s.last_active) > timeout
            ]
            for key in stale_keys:
                logger.info("Evicting idle session: %s", key)
                del self._sessions[key]
                self._delete_persisted(key)
