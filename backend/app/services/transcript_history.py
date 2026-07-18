"""DynamoDB metadata store for signed-in users' transcript exports.

Transcript bodies remain private TXT objects in S3. DynamoDB stores only the
owner, object key, timestamps, and summary metadata required to list and
re-authorize downloads. Records receive the same 14-day TTL as transcripts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError


class TranscriptHistoryError(Exception):
    """Raised when history metadata cannot be persisted or read."""


@dataclass(frozen=True)
class TranscriptHistoryRecord:
    history_id: str
    session_id: str
    created_at: datetime
    segment_count: int
    s3_key: str


def _client(region: str) -> Any:
    return boto3.client("dynamodb", region_name=region)


def _history_id(created_at: datetime, session_id: str) -> str:
    return f"{created_at.isoformat(timespec='milliseconds')}#{session_id}"


def save_history_record(
    *,
    table_name: str,
    region: str,
    user_id: str,
    session_id: str,
    s3_key: str,
    segment_count: int,
    retention_days: int,
    client: Any | None = None,
) -> TranscriptHistoryRecord:
    """Persist export metadata and return the owner-scoped record."""

    created_at = datetime.now(timezone.utc)
    history_id = _history_id(created_at, session_id)
    expires_at = int((created_at + timedelta(days=retention_days)).timestamp())
    dynamodb = client or _client(region)
    try:
        dynamodb.put_item(
            TableName=table_name,
            Item={
                "user_id": {"S": user_id},
                "history_id": {"S": history_id},
                "session_id": {"S": session_id},
                "s3_key": {"S": s3_key},
                "segment_count": {"N": str(segment_count)},
                "created_at": {"S": created_at.isoformat()},
                "expires_at": {"N": str(expires_at)},
            },
        )
    except (BotoCoreError, ClientError) as exc:
        raise TranscriptHistoryError("Failed to save transcript history") from exc
    return TranscriptHistoryRecord(
        history_id=history_id,
        session_id=session_id,
        created_at=created_at,
        segment_count=segment_count,
        s3_key=s3_key,
    )


def list_history_records(
    *, table_name: str, region: str, user_id: str, limit: int, client: Any | None = None
) -> list[TranscriptHistoryRecord]:
    """Return the caller's recent records, newest first."""

    dynamodb = client or _client(region)
    try:
        response = dynamodb.query(
            TableName=table_name,
            KeyConditionExpression="user_id = :user_id",
            ExpressionAttributeValues={":user_id": {"S": user_id}},
            ScanIndexForward=False,
            Limit=limit,
        )
    except (BotoCoreError, ClientError) as exc:
        raise TranscriptHistoryError("Failed to load transcript history") from exc
    records: list[TranscriptHistoryRecord] = []
    for item in response.get("Items", []):
        try:
            records.append(
                TranscriptHistoryRecord(
                    history_id=item["history_id"]["S"],
                    session_id=item["session_id"]["S"],
                    s3_key=item["s3_key"]["S"],
                    segment_count=int(item["segment_count"]["N"]),
                    created_at=datetime.fromisoformat(item["created_at"]["S"]),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    return records


def get_history_record(
    *, table_name: str, region: str, user_id: str, history_id: str, client: Any | None = None
) -> TranscriptHistoryRecord | None:
    """Find a single record only within its owning user's partition."""

    dynamodb = client or _client(region)
    try:
        response = dynamodb.get_item(
            TableName=table_name,
            Key={"user_id": {"S": user_id}, "history_id": {"S": history_id}},
        )
    except (BotoCoreError, ClientError) as exc:
        raise TranscriptHistoryError("Failed to load transcript history") from exc
    item = response.get("Item")
    if not item:
        return None
    return TranscriptHistoryRecord(
        history_id=item["history_id"]["S"],
        session_id=item["session_id"]["S"],
        s3_key=item["s3_key"]["S"],
        segment_count=int(item["segment_count"]["N"]),
        created_at=datetime.fromisoformat(item["created_at"]["S"]),
    )
