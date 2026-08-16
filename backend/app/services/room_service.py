"""Process-local shared caption rooms for the Rooms vertical slice.

This implementation intentionally keeps room state in memory. It proves the
host/viewer contract locally without pretending to be the production fan-out
layer. The target architecture replaces this service with AppSync Events and a
short-TTL DynamoDB event table before horizontal scaling.
"""

from __future__ import annotations

import asyncio
import secrets
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import WebSocket

from app.models import FinalizedSegmentMessage


_ROOM_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_ROOM_CODE_LENGTH = 6


@dataclass
class _Room:
    code: str
    host_token: str
    title: str
    created_at: datetime
    expires_at: datetime
    max_segments: int
    status: str = "live"
    host_session_id: str | None = None
    sequence: int = 0
    segments: deque[dict[str, Any]] = field(default_factory=deque)
    subscribers: set[WebSocket] = field(default_factory=set)
    segment_ids: set[str] = field(default_factory=set)

    def public_payload(self) -> dict[str, Any]:
        return {
            "room_code": self.code,
            "title": self.title,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "viewer_count": len(self.subscribers),
            "sequence": self.sequence,
            "segments": list(self.segments),
        }


class RoomService:
    """Own room lifecycle and local WebSocket subscribers."""

    def __init__(self) -> None:
        self._rooms: dict[str, _Room] = {}
        self._lock = asyncio.Lock()

    async def create_room(
        self,
        *,
        title: str,
        ttl_seconds: int,
        max_segments: int,
    ) -> tuple[dict[str, Any], str]:
        now = datetime.now(timezone.utc)
        async with self._lock:
            self._drop_expired_locked(now)
            code = self._new_code_locked()
            room = _Room(
                code=code,
                host_token=secrets.token_urlsafe(24),
                title=title.strip() or "LiveCap room",
                created_at=now,
                expires_at=now + timedelta(seconds=ttl_seconds),
                max_segments=max_segments,
                segments=deque(maxlen=max_segments),
            )
            self._rooms[code] = room
            return room.public_payload(), room.host_token

    async def get_snapshot(self, room_code: str) -> dict[str, Any] | None:
        async with self._lock:
            room = self._active_room_locked(room_code)
            return room.public_payload() if room is not None else None

    async def authorize_host(self, room_code: str, host_token: str) -> bool:
        async with self._lock:
            room = self._active_room_locked(room_code)
            return bool(
                room is not None
                and room.status == "live"
                and host_token
                and secrets.compare_digest(room.host_token, host_token)
            )

    async def bind_host_session(
        self,
        room_code: str,
        host_token: str,
        session_id: str,
    ) -> bool:
        async with self._lock:
            room = self._active_room_locked(room_code)
            if (
                room is None
                or room.status != "live"
                or not host_token
                or not secrets.compare_digest(room.host_token, host_token)
            ):
                return False
            room.host_session_id = session_id
            return True

    async def publish_finalized_segment(
        self,
        room_code: str,
        host_token: str,
        message: FinalizedSegmentMessage,
    ) -> bool:
        async with self._lock:
            room = self._active_room_locked(room_code)
            if (
                room is None
                or room.status != "live"
                or not host_token
                or not secrets.compare_digest(room.host_token, host_token)
            ):
                return False
            if message.segment_id in room.segment_ids:
                return True

            room.sequence += 1
            segment = message.model_dump(mode="json")
            if len(room.segments) == room.max_segments and room.segments:
                oldest_id = room.segments[0].get("segment_id")
                if isinstance(oldest_id, str):
                    room.segment_ids.discard(oldest_id)
            room.segment_ids.add(message.segment_id)
            room.segments.append(segment)
            payload = {
                "type": "room_segment",
                "room_code": room.code,
                "sequence": room.sequence,
                "segment": segment,
            }
            subscribers = tuple(room.subscribers)

        await self._broadcast(subscribers, payload)
        return True

    async def subscribe(
        self,
        room_code: str,
        websocket: WebSocket,
    ) -> dict[str, Any] | None:
        async with self._lock:
            room = self._active_room_locked(room_code)
            if room is None:
                return None
            room.subscribers.add(websocket)
            snapshot = room.public_payload()
            return {"type": "room_snapshot", **snapshot}

    async def unsubscribe(self, room_code: str, websocket: WebSocket) -> None:
        async with self._lock:
            room = self._rooms.get(self._normalize_code(room_code))
            if room is not None:
                room.subscribers.discard(websocket)

    async def close_room(self, room_code: str, host_token: str) -> bool:
        async with self._lock:
            room = self._active_room_locked(room_code)
            if (
                room is None
                or not host_token
                or not secrets.compare_digest(room.host_token, host_token)
            ):
                return False
            room.status = "ended"
            payload = {
                "type": "room_closed",
                "room_code": room.code,
                "sequence": room.sequence,
            }
            subscribers = tuple(room.subscribers)

        await self._broadcast(subscribers, payload)
        return True

    async def reset(self) -> None:
        """Clear all process-local rooms; used by isolated tests."""

        async with self._lock:
            self._rooms.clear()

    async def _broadcast(
        self,
        subscribers: tuple[WebSocket, ...],
        payload: dict[str, Any],
    ) -> None:
        if not subscribers:
            return
        await asyncio.gather(
            *(self._send_json(websocket, payload) for websocket in subscribers),
            return_exceptions=True,
        )

    @staticmethod
    async def _send_json(websocket: WebSocket, payload: dict[str, Any]) -> None:
        await websocket.send_json(payload)

    def _active_room_locked(self, room_code: str) -> _Room | None:
        code = self._normalize_code(room_code)
        room = self._rooms.get(code)
        if room is None:
            return None
        if room.expires_at <= datetime.now(timezone.utc):
            self._rooms.pop(code, None)
            return None
        return room

    def _drop_expired_locked(self, now: datetime) -> None:
        expired = [
            code for code, room in self._rooms.items() if room.expires_at <= now
        ]
        for code in expired:
            self._rooms.pop(code, None)

    def _new_code_locked(self) -> str:
        while True:
            code = "".join(
                secrets.choice(_ROOM_ALPHABET) for _ in range(_ROOM_CODE_LENGTH)
            )
            if code not in self._rooms:
                return code

    @staticmethod
    def _normalize_code(room_code: str) -> str:
        return room_code.strip().upper()


_room_service = RoomService()


def get_room_service() -> RoomService:
    return _room_service
