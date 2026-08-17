"""DynamoDB persistence for shared-room metadata and finalized captions."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from decimal import Decimal
from typing import Any


_META_KEY = "META"
_SEGMENT_PREFIX = "SEGMENT#"


@dataclass(frozen=True)
class PersistedRoom:
    """Room state reconstructed from DynamoDB."""

    room_code: str
    host_token_hash: str
    title: str
    status: str
    created_at: str
    live_expires_at: str
    archive_expires_at: str
    max_segments: int
    sequence: int
    segments: list[dict[str, Any]]


class DynamoRoomStore:
    """Store room metadata and finalized segments in one DynamoDB table."""

    def __init__(
        self,
        *,
        table_name: str,
        region: str,
        table: Any | None = None,
    ) -> None:
        self._table_name = table_name
        self._region = region
        self._table = table

    def _get_table(self) -> Any:
        if self._table is None:
            import boto3  # noqa: PLC0415

            resource = boto3.resource("dynamodb", region_name=self._region)
            self._table = resource.Table(self._table_name)
        return self._table

    async def reserve_room(
        self,
        *,
        room_code: str,
        host_token_hash: str,
        title: str,
        status: str,
        created_at: str,
        live_expires_at: str,
        archive_expires_at: str,
        archive_expires_epoch: int,
        max_segments: int,
    ) -> bool:
        """Create room metadata if the generated code is not already used."""

        table = self._get_table()
        item = {
            "room_code": room_code,
            "record_key": _META_KEY,
            "host_token_hash": host_token_hash,
            "title": title,
            "status": status,
            "created_at": created_at,
            "live_expires_at": live_expires_at,
            "archive_expires_at": archive_expires_at,
            "max_segments": max_segments,
            "sequence": 0,
            "expires_at": archive_expires_epoch,
        }
        try:
            await asyncio.to_thread(
                table.put_item,
                Item=item,
                ConditionExpression=(
                    "attribute_not_exists(room_code) AND "
                    "attribute_not_exists(record_key)"
                ),
            )
        except table.meta.client.exceptions.ConditionalCheckFailedException:
            return False
        return True

    async def load_room(self, room_code: str) -> PersistedRoom | None:
        """Load room metadata plus the newest retained finalized segments."""

        table = self._get_table()
        response = await asyncio.to_thread(
            table.get_item,
            Key={"room_code": room_code, "record_key": _META_KEY},
            ConsistentRead=True,
        )
        metadata = response.get("Item")
        if not isinstance(metadata, dict):
            return None

        max_segments = int(metadata.get("max_segments", 100))
        segments, max_sequence = await self._load_segments(
            table=table,
            room_code=room_code,
            max_segments=max_segments,
        )
        stored_sequence = int(metadata.get("sequence", 0))
        return PersistedRoom(
            room_code=room_code,
            host_token_hash=str(metadata.get("host_token_hash", "")),
            title=str(metadata.get("title", "LiveCap room")),
            status=str(metadata.get("status", "ended")),
            created_at=str(metadata["created_at"]),
            live_expires_at=str(metadata["live_expires_at"]),
            archive_expires_at=str(metadata["archive_expires_at"]),
            max_segments=max_segments,
            sequence=max(stored_sequence, max_sequence),
            segments=segments,
        )

    async def append_segment(
        self,
        *,
        room_code: str,
        sequence: int,
        segment: dict[str, Any],
        archive_expires_epoch: int,
    ) -> None:
        """Persist one finalized segment and advance room sequence metadata."""

        table = self._get_table()
        await asyncio.to_thread(
            table.put_item,
            Item={
                "room_code": room_code,
                "record_key": f"{_SEGMENT_PREFIX}{sequence:010d}",
                "sequence": sequence,
                "segment": _to_dynamo_value(segment),
                "expires_at": archive_expires_epoch,
            },
        )
        await asyncio.to_thread(
            table.update_item,
            Key={"room_code": room_code, "record_key": _META_KEY},
            UpdateExpression="SET #sequence = :sequence",
            ExpressionAttributeNames={"#sequence": "sequence"},
            ExpressionAttributeValues={":sequence": sequence},
        )

    async def mark_ended(self, room_code: str) -> None:
        """Mark a room read-only while retaining its finalized transcript."""

        table = self._get_table()
        await asyncio.to_thread(
            table.update_item,
            Key={"room_code": room_code, "record_key": _META_KEY},
            UpdateExpression="SET #status = :status",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={":status": "ended"},
            ConditionExpression="attribute_exists(room_code)",
        )

    async def _load_segments(
        self,
        *,
        table: Any,
        room_code: str,
        max_segments: int,
    ) -> tuple[list[dict[str, Any]], int]:
        from boto3.dynamodb.conditions import Key  # noqa: PLC0415

        items: list[dict[str, Any]] = []
        start_key: dict[str, Any] | None = None
        while len(items) < max_segments:
            kwargs: dict[str, Any] = {
                "KeyConditionExpression": (
                    Key("room_code").eq(room_code)
                    & Key("record_key").begins_with(_SEGMENT_PREFIX)
                ),
                "ScanIndexForward": False,
                "ConsistentRead": True,
                "Limit": max_segments - len(items),
            }
            if start_key is not None:
                kwargs["ExclusiveStartKey"] = start_key
            response = await asyncio.to_thread(table.query, **kwargs)
            items.extend(response.get("Items", []))
            start_key = response.get("LastEvaluatedKey")
            if not start_key:
                break

        items.reverse()
        segments = [
            _from_dynamo_value(item.get("segment", {}))
            for item in items
            if isinstance(item.get("segment"), dict)
        ]
        max_sequence = max(
            (int(item.get("sequence", 0)) for item in items),
            default=0,
        )
        return segments, max_sequence


def _to_dynamo_value(value: Any) -> Any:
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {key: _to_dynamo_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_dynamo_value(item) for item in value]
    return value


def _from_dynamo_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, dict):
        return {key: _from_dynamo_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_from_dynamo_value(item) for item in value]
    return value
