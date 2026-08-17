"""Persistence tests for shared rooms using moto DynamoDB."""

from __future__ import annotations

import asyncio

import boto3
from moto import mock_aws

from app.models import FinalizedSegmentMessage
from app.services.dynamo_room_store import DynamoRoomStore
from app.services.room_service import RoomService


TABLE = "livecap-room-events-test"
REGION = "ap-southeast-1"


def _create_table() -> None:
    client = boto3.client("dynamodb", region_name=REGION)
    client.create_table(
        TableName=TABLE,
        KeySchema=[
            {"AttributeName": "room_code", "KeyType": "HASH"},
            {"AttributeName": "record_key", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "room_code", "AttributeType": "S"},
            {"AttributeName": "record_key", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )


def test_closed_room_survives_backend_restart_without_plaintext_host_token() -> None:
    async def scenario() -> None:
        store = DynamoRoomStore(table_name=TABLE, region=REGION)
        first_process = RoomService(store=store, retention_days=14)
        room, host_token = await first_process.create_room(
            title="Architecture review",
            ttl_seconds=600,
            max_segments=20,
        )
        message = FinalizedSegmentMessage(
            segment_id="segment-1",
            speaker_label="Speaker 1",
            text_vi="Xin chao",
            text_en="Hello",
            spoken_language="vi",
            timestamp_start=1.25,
            timestamp_end=2.5,
        )
        assert await first_process.publish_finalized_segment(
            room["room_code"], host_token, message
        )
        assert await first_process.close_room(room["room_code"], host_token)

        table = boto3.resource("dynamodb", region_name=REGION).Table(TABLE)
        metadata = table.get_item(
            Key={"room_code": room["room_code"], "record_key": "META"}
        )["Item"]
        assert metadata["host_token_hash"] != host_token
        assert len(metadata["host_token_hash"]) == 64

        restarted_process = RoomService(
            store=DynamoRoomStore(table_name=TABLE, region=REGION),
            retention_days=14,
        )
        snapshot = await restarted_process.get_snapshot(room["room_code"])
        assert snapshot is not None
        assert snapshot["status"] == "ended"
        assert snapshot["live_expires_at"] < snapshot["expires_at"]
        assert snapshot["segments"] == [message.model_dump(mode="json")]

    with mock_aws():
        _create_table()
        asyncio.run(scenario())
