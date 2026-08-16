"""Tests for the feature-gated shared-room vertical slice."""

from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app
from app.models import FinalizedSegmentMessage
from app.services.room_service import RoomService, get_room_service


class _FakeWebSocket:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def send_json(self, payload: dict) -> None:
        self.messages.append(payload)


def test_room_service_requires_host_token_and_deduplicates_segments() -> None:
    async def scenario() -> None:
        service = RoomService()
        room, token = await service.create_room(
            title="Architecture review",
            ttl_seconds=600,
            max_segments=20,
        )
        viewer = _FakeWebSocket()
        snapshot = await service.subscribe(room["room_code"], viewer)  # type: ignore[arg-type]
        assert snapshot is not None
        assert snapshot["segments"] == []

        message = FinalizedSegmentMessage(
            segment_id="segment-1",
            speaker_label="Speaker 1",
            text_vi="Xin chao",
            text_en="Hello",
            spoken_language="vi",
            timestamp_start=0,
            timestamp_end=1,
        )
        assert not await service.publish_finalized_segment(
            room["room_code"], "wrong-token", message
        )
        assert viewer.messages == []

        assert await service.publish_finalized_segment(
            room["room_code"], token, message
        )
        assert await service.publish_finalized_segment(
            room["room_code"], token, message
        )
        assert [item["type"] for item in viewer.messages] == ["room_segment"]

        late_snapshot = await service.get_snapshot(room["room_code"])
        assert late_snapshot is not None
        assert [item["segment_id"] for item in late_snapshot["segments"]] == [
            "segment-1"
        ]

    asyncio.run(scenario())


def test_room_service_notifies_viewers_when_host_closes_room() -> None:
    async def scenario() -> None:
        service = RoomService()
        room, token = await service.create_room(
            title="Town hall",
            ttl_seconds=600,
            max_segments=20,
        )
        viewer = _FakeWebSocket()
        await service.subscribe(room["room_code"], viewer)  # type: ignore[arg-type]

        assert not await service.close_room(room["room_code"], "wrong-token")
        assert await service.close_room(room["room_code"], token)
        assert viewer.messages == [
            {
                "type": "room_closed",
                "room_code": room["room_code"],
                "sequence": 0,
            }
        ]

    asyncio.run(scenario())


def test_room_api_is_hidden_when_feature_is_disabled(monkeypatch) -> None:
    monkeypatch.setenv("ENABLE_SHARED_ROOMS", "false")
    get_settings.cache_clear()
    with TestClient(app) as client:
        response = client.post("/api/rooms", json={"title": "Hidden room"})
    assert response.status_code == 404
    get_settings.cache_clear()


def test_room_api_creates_snapshot_and_closes_room(monkeypatch) -> None:
    monkeypatch.setenv("ENABLE_SHARED_ROOMS", "true")
    monkeypatch.setenv("ENABLE_AUTH", "false")
    monkeypatch.setenv("FRONTEND_BASE_URL", "http://localhost:5173")
    get_settings.cache_clear()
    asyncio.run(get_room_service().reset())

    with TestClient(app) as client:
        created = client.post("/api/rooms", json={"title": "Live workshop"})
        assert created.status_code == 201
        payload = created.json()
        assert len(payload["room_code"]) == 6
        assert payload["join_url"].endswith(f"/rooms/{payload['room_code']}")
        assert payload["host_token"] not in payload["join_url"]

        snapshot = client.get(f"/api/rooms/{payload['room_code']}")
        assert snapshot.status_code == 200
        assert snapshot.json()["title"] == "Live workshop"
        assert "host_token" not in snapshot.json()

        rejected = client.post(
            f"/api/rooms/{payload['room_code']}/close",
            headers={"X-LiveCap-Room-Token": "wrong-token"},
        )
        assert rejected.status_code == 404

        closed = client.post(
            f"/api/rooms/{payload['room_code']}/close",
            headers={"X-LiveCap-Room-Token": payload["host_token"]},
        )
        assert closed.status_code == 200
        assert closed.json() == {"status": "closed"}

    get_settings.cache_clear()
