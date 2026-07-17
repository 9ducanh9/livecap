"""In-memory active WebSocket session registry.

The registry is process-local by design. It protects a single backend process
from abuse while the ECS service is constrained to one task. If LiveCap scales
past one task, these limits must move to a shared store such as DynamoDB or
Redis.
"""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock


@dataclass(frozen=True)
class SessionLimitResult:
    """Result returned by an active-session registration attempt."""

    allowed: bool
    reason: str | None = None


class ActiveSessionRegistry:
    """Tracks active WebSocket sessions by Session_ID and client IP."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._session_to_ip: dict[str, str] = {}
        self._ip_counts: dict[str, int] = {}

    def try_register(
        self,
        *,
        session_id: str,
        client_ip: str,
        max_total: int,
        max_per_ip: int,
    ) -> SessionLimitResult:
        """Register a session unless it exceeds the configured limits."""

        with self._lock:
            if session_id in self._session_to_ip:
                return SessionLimitResult(allowed=True)

            total_active = len(self._session_to_ip)
            if total_active >= max_total:
                return SessionLimitResult(allowed=False, reason="global_limit")

            ip_active = self._ip_counts.get(client_ip, 0)
            if ip_active >= max_per_ip:
                return SessionLimitResult(allowed=False, reason="per_ip_limit")

            self._session_to_ip[session_id] = client_ip
            self._ip_counts[client_ip] = ip_active + 1
            return SessionLimitResult(allowed=True)

    def unregister(self, session_id: str) -> None:
        """Remove a session if it is currently registered."""

        with self._lock:
            client_ip = self._session_to_ip.pop(session_id, None)
            if client_ip is None:
                return

            next_count = self._ip_counts.get(client_ip, 0) - 1
            if next_count > 0:
                self._ip_counts[client_ip] = next_count
            else:
                self._ip_counts.pop(client_ip, None)

    def clear(self) -> None:
        """Clear all sessions. Intended for tests."""

        with self._lock:
            self._session_to_ip.clear()
            self._ip_counts.clear()

    @property
    def active_count(self) -> int:
        """Return the total number of active sessions."""

        with self._lock:
            return len(self._session_to_ip)

    def active_count_for_ip(self, client_ip: str) -> int:
        """Return active sessions for a specific client IP."""

        with self._lock:
            return self._ip_counts.get(client_ip, 0)


active_session_registry = ActiveSessionRegistry()


# Cached DynamoDB-backed registry (created on first use when enabled).
_dynamo_session_registry = None


def get_session_registry(settings=None):
    """Return the configured active-session registry.

    ``memory`` (default) returns the process-local singleton. ``dynamodb``
    returns a shared, cross-task registry backed by DynamoDB. The choice is
    driven by ``settings.session_store_backend`` so the default deployment
    behaviour is unchanged.
    """
    from app.config import get_settings  # local import avoids an import cycle

    settings = settings or get_settings()
    if settings.session_store_backend == "dynamodb":
        global _dynamo_session_registry
        if _dynamo_session_registry is None:
            from app.services.dynamo_session_registry import (  # noqa: PLC0415
                DynamoDbSessionRegistry,
            )

            _dynamo_session_registry = DynamoDbSessionRegistry(
                table_name=settings.session_table_name,
                region=settings.aws_region,
                ttl_seconds=settings.session_ttl_seconds,
            )
        return _dynamo_session_registry
    return active_session_registry
