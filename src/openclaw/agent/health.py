"""Health monitoring: request metrics and uptime tracking."""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RequestMetric:
    """A single request measurement."""

    timestamp: float
    user_id: int
    duration_ms: float
    success: bool
    error_message: str = ""


class HealthMonitor:
    """Tracks request metrics using a bounded deque."""

    def __init__(self, maxlen: int = 1000) -> None:
        self._metrics: deque[RequestMetric] = deque(maxlen=maxlen)
        self._start_time: float = time.time()

    def record(
        self,
        *,
        user_id: int,
        duration_ms: float,
        success: bool,
        error_message: str = "",
    ) -> None:
        """Record a request metric."""
        self._metrics.append(
            RequestMetric(
                timestamp=time.time(),
                user_id=user_id,
                duration_ms=duration_ms,
                success=success,
                error_message=error_message,
            )
        )

    def get_stats(self) -> dict[str, Any]:
        """Compute aggregate statistics from recorded metrics."""
        now = time.time()
        uptime_seconds = now - self._start_time
        total = len(self._metrics)

        if total == 0:
            return {
                "uptime_seconds": uptime_seconds,
                "total_requests": 0,
                "avg_response_ms": 0.0,
                "error_rate": 0.0,
                "recent_errors": [],
            }

        successes = sum(1 for m in self._metrics if m.success)
        failures = total - successes
        avg_ms = sum(m.duration_ms for m in self._metrics) / total
        error_rate = failures / total

        recent_errors = [
            m.error_message
            for m in list(self._metrics)[-5:]
            if not m.success and m.error_message
        ]

        return {
            "uptime_seconds": uptime_seconds,
            "total_requests": total,
            "avg_response_ms": round(avg_ms, 1),
            "error_rate": round(error_rate, 4),
            "recent_errors": recent_errors,
        }
