"""DynamoDB-backed active session registry.

A drop-in replacement for :class:`~app.services.session_registry.ActiveSessionRegistry`
that shares the active-session limits across ECS tasks, which is the prerequisite
for running more than one backend task (horizontal scaling).

Design
------
* Table key: ``pk = <session_id>`` (String). Each active WebSocket session is one
  item carrying ``client_ip`` and a ``expires_at`` TTL attribute. Keying on the
  session id makes ``unregister`` a single ``DeleteItem`` (it only has the id).
* Counts are computed with a consistent ``Scan`` (``Select=COUNT``), optionally
  filtered by ``client_ip``. The table holds at most a handful of items at this
  scale, so scans are cheap; TTL removes rows left by crashed tasks, so counts
  self-heal instead of drifting.
* ``try_register`` is check-then-put, so under heavy concurrency it can admit one
  or two sessions over the limit. That is acceptable for an abuse guard; the
  goal is a shared bound, not exact accounting. A conditional ``PutItem`` keeps
  registration idempotent for a repeated session id.

boto3 is imported lazily so importing this module never requires botocore.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from app.services.logging_service import get_logger
from app.services.session_registry import SessionLimitResult

_MAX_SCAN_PAGES = 50


class DynamoDbSessionRegistry:
    """Active-session registry stored in a DynamoDB table."""

    def __init__(
        self,
        *,
        table_name: str,
        region: str,
        ttl_seconds: int,
        client: Any | None = None,
    ) -> None:
        self._table_name = table_name
        self._region = region
        self._ttl_seconds = ttl_seconds
        self._client = client  # allows injection in tests
        self._logger: logging.Logger = get_logger()

    # ------------------------------------------------------------------
    # boto3 client (lazy)
    # ------------------------------------------------------------------
    def _get_client(self) -> Any:
        if self._client is None:
            import boto3  # noqa: PLC0415

            self._client = boto3.client("dynamodb", region_name=self._region)
        return self._client

    # ------------------------------------------------------------------
    # Counting helpers
    # ------------------------------------------------------------------
    def _count(self, client_ip: str | None = None) -> int:
        client = self._get_client()
        kwargs: dict[str, Any] = {
            "TableName": self._table_name,
            "Select": "COUNT",
            "ConsistentRead": True,
        }
        if client_ip is not None:
            kwargs["FilterExpression"] = "client_ip = :ip"
            kwargs["ExpressionAttributeValues"] = {":ip": {"S": client_ip}}

        total = 0
        start_key = None
        for _ in range(_MAX_SCAN_PAGES):
            if start_key is not None:
                kwargs["ExclusiveStartKey"] = start_key
            resp = client.scan(**kwargs)
            total += int(resp.get("Count", 0))
            start_key = resp.get("LastEvaluatedKey")
            if not start_key:
                break
        return total

    # ------------------------------------------------------------------
    # Public interface (mirrors ActiveSessionRegistry)
    # ------------------------------------------------------------------
    def try_register(
        self,
        *,
        session_id: str,
        client_ip: str,
        max_total: int,
        max_per_ip: int,
    ) -> SessionLimitResult:
        client = self._get_client()

        if self._count() >= max_total:
            return SessionLimitResult(allowed=False, reason="global_limit")
        if self._count(client_ip) >= max_per_ip:
            return SessionLimitResult(allowed=False, reason="per_ip_limit")

        expires_at = int(time.time()) + self._ttl_seconds
        try:
            client.put_item(
                TableName=self._table_name,
                Item={
                    "pk": {"S": session_id},
                    "client_ip": {"S": client_ip},
                    "expires_at": {"N": str(expires_at)},
                },
                ConditionExpression="attribute_not_exists(pk)",
            )
        except Exception as exc:  # noqa: BLE001
            # A conditional failure means the id is already registered → allow
            # (idempotent). Any other error is surfaced as a global rejection so
            # the caller closes the socket rather than proceeding unbounded.
            if _is_conditional_failure(exc):
                return SessionLimitResult(allowed=True)
            self._logger.error(
                "session_registry_put_failed",
                extra={
                    "event": "session_registry_put_failed",
                    "session_id": session_id,
                    "error": str(exc),
                },
            )
            return SessionLimitResult(allowed=False, reason="store_error")

        return SessionLimitResult(allowed=True)

    def unregister(self, session_id: str) -> None:
        client = self._get_client()
        try:
            client.delete_item(
                TableName=self._table_name,
                Key={"pk": {"S": session_id}},
            )
        except Exception as exc:  # noqa: BLE001
            self._logger.error(
                "session_registry_delete_failed",
                extra={
                    "event": "session_registry_delete_failed",
                    "session_id": session_id,
                    "error": str(exc),
                },
            )

    def clear(self) -> None:
        """Delete all session items. Intended for tests/operations."""
        client = self._get_client()
        start_key = None
        for _ in range(_MAX_SCAN_PAGES):
            kwargs: dict[str, Any] = {
                "TableName": self._table_name,
                "ProjectionExpression": "pk",
            }
            if start_key is not None:
                kwargs["ExclusiveStartKey"] = start_key
            resp = client.scan(**kwargs)
            for item in resp.get("Items", []):
                client.delete_item(
                    TableName=self._table_name, Key={"pk": item["pk"]}
                )
            start_key = resp.get("LastEvaluatedKey")
            if not start_key:
                break

    @property
    def active_count(self) -> int:
        return self._count()

    def active_count_for_ip(self, client_ip: str) -> int:
        return self._count(client_ip)


def _is_conditional_failure(exc: Exception) -> bool:
    """True when *exc* is a DynamoDB ConditionalCheckFailedException."""
    response = getattr(exc, "response", None)
    if isinstance(response, dict):
        code = response.get("Error", {}).get("Code", "")
        return code == "ConditionalCheckFailedException"
    return exc.__class__.__name__ == "ConditionalCheckFailedException"
