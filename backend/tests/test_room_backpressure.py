import asyncio
from app.models import PartialSegmentMessage
from app.services.room_service import RoomService

class FakeWebSocket:
    def __init__(self):
        self.messages = []
    async def send_json(self, payload):
        self.messages.append(payload)

def test_stalled_viewer_does_not_block_room_captions(monkeypatch) -> None:
    monkeypatch.setattr("app.services.room_service._ROOM_SEND_TIMEOUT_SECONDS", 0.01)

    class StalledViewer(FakeWebSocket):
        async def send_json(self, payload: dict) -> None:
            await asyncio.Event().wait()

    async def scenario() -> None:
        service = RoomService()
        room, token = await service.create_room(title="Slow viewer", ttl_seconds=600, max_segments=20)
        healthy, stalled = FakeWebSocket(), StalledViewer()
        await service.subscribe(room["room_code"], healthy)
        await service.subscribe(room["room_code"], stalled)
        partial = PartialSegmentMessage(segment_id="one", speaker_label="Speaker 1", text_en="Hello there", spoken_language="en")
        await asyncio.wait_for(service.publish_partial_segment(room["room_code"], token, partial), 0.5)
        await asyncio.wait_for(service.publish_partial_segment(room["room_code"], token, partial), 0.5)
        assert len(healthy.messages) == 2
        snapshot = await service.get_snapshot(room["room_code"])
        assert snapshot["viewer_count"] == 1

    asyncio.run(scenario())


