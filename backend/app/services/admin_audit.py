"""Admin audit logging service (stub).

This module will persist audit log entries for all mutating admin actions.
Full implementation is created in a parallel task. This stub provides the
interface so that dependent code can import and call it.
"""

from __future__ import annotations

import datetime
import logging
import os
import uuid

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.config import get_settings

logger = logging.getLogger(__name__)


def _audit_table_name() -> str:
    return os.getenv("ADMIN_AUDIT_TABLE_NAME", "livecap-admin-audit-dev")


def record_action(
    admin_user_id: str,
    target_user_id: str,
    action_type: str,
    previous_value: str | None = None,
    new_value: str | None = None,
) -> dict:
    """Persist an audit log entry for a mutating admin action.

    Args:
        admin_user_id: The admin who performed the action.
        target_user_id: The user affected by the action.
        action_type: Type of action (disable, enable, reset_password, change_tier).
        previous_value: The value before the change (optional).
        new_value: The value after the change (optional).

    Returns:
        The audit log entry dict.

    Raises:
        Exception: If the DynamoDB write fails (caller must handle rollback).
    """
    settings = get_settings()
    dynamodb = boto3.resource("dynamodb", region_name=settings.aws_region)
    table = dynamodb.Table(_audit_table_name())

    entry_id = str(uuid.uuid4())
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()

    item = {
        "pk": f"USER#{target_user_id}",
        "sk": f"AUDIT#{timestamp}#{entry_id}",
        "entry_id": entry_id,
        "admin_user_id": admin_user_id,
        "target_user_id": target_user_id,
        "action_type": action_type,
        "timestamp": timestamp,
    }
    if previous_value is not None:
        item["previous_value"] = previous_value
    if new_value is not None:
        item["new_value"] = new_value

    # This intentionally raises on failure so callers can rollback
    table.put_item(Item=item)

    return item


def get_audit_entries_for_user(
    target_user_id: str,
    limit: int = 20,
) -> list[dict]:
    """Retrieve recent audit log entries for a given user.

    Args:
        target_user_id: The Cognito username of the target user.
        limit: Maximum number of entries to return (most recent first).

    Returns:
        List of audit log entry dicts, ordered most-recent-first.
    """
    settings = get_settings()
    dynamodb = boto3.resource("dynamodb", region_name=settings.aws_region)
    table = dynamodb.Table(_audit_table_name())

    try:
        response = table.query(
            KeyConditionExpression="pk = :pk AND begins_with(sk, :prefix)",
            ExpressionAttributeValues={
                ":pk": f"USER#{target_user_id}",
                ":prefix": "AUDIT#",
            },
            ScanIndexForward=False,  # Most recent first
            Limit=limit,
        )
        return response.get("Items", [])
    except (ClientError, BotoCoreError) as exc:
        logger.warning(
            "Failed to fetch audit entries for user %s: %s",
            target_user_id,
            exc,
        )
        return []
