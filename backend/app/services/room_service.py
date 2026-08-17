"""Shared caption room lifecycle with optional DynamoDB persistence."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import secrets
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from fastapi import WebSocket

from app.models import FinalizedSegmentMessage
from app.services.dynamo_room_store import PersistedRoom


logger = logging.getLogger(__name__)

_ROOM_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_ROOM_CODE_LENGTH = 6
_ROOM_CODE_ATTEMPTS = 20


class RoomArchiveStore(Protocol):
    async def reserve_room(self, **kwargs: Any) -> bool: ...

    async def load_room(self, room_code: str) -> PersistedRoom | None: ...

    async def append_segment(self, **kwargs: Any) -> None: ...

    async def mark_ended(self, room_code: str) -> None: ...


@dataclass
class _Room:
    code: str
    host_token_hash: str
    title: str
    created_at: datetime
    live_expires_at: datetime
    archive_expires_at: datetime
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
            "live_expires_at": self.live_expires_at.isoformat(),
            "expires_at": self.archive_expires_at.isoformat(),
            "viewer_count": len(self.subscribers),
            "sequence": self.sequence,
            "segments": list(self.segments),
        }


class RoomService:
    """Own room lifecycle, local fan-out, and optional durable snapshots."""

    def __init__(
        self,
        *,
        store: RoomArchiveStore | None = None,
        retention_days: int = 14,
    ) -> None:
        self._rooms: dict[str, _Room] = {}
        self._lock = asyncio.Lock()
        self._store = store
        self._retention_days = max(1, retention_days)

    async def create_room(
        self,
        *,
        title: str,
        ttl_seconds: int,
        max_segments: int,
    ) -> tuple[dict[str, Any], str]:
        now = datetime.now(timezone.utc)
        host_token = secrets.token_urlsafe(24)
        host_token_hash = _hash_token(host_token)
        live_expires_at = now + timedelta(seconds=ttl_seconds)
        archive_expires_at = live_expires_at + timedelta(
            days=self._retention_days
        )
        async with self._lock:
            self._drop_expired_locked(now)
            for _ in range(_ROOM_CODE_ATTEMPTS):
                code = self._new_code_locked()
                room = _Room(
                    code=code,
                    host_token_hash=host_token_hash,
                    title=title.strip() or "LiveCap room",
                    created_at=now,
                    live_expires_at=live_expires_at,
                    archive_expires_at=archive_expires_at,
                    max_segments=max_segments,
                    segments=deque(maxlen=max_segments),
                )
                if self._store is not None:
                    reserved = await self._store.reserve_room(
                        room_code=room.code,
                        host_token_hash=room.host_token_hash,
                        title=room.title,
                        status=room.status,
                        created_at=room.created_at.isoformat(),
                        live_expires_at=room.live_expires_at.isoformat(),
                        archive_expires_at=room.archive_expires_at.isoformat(),
                        archive_expires_epoch=int(
                            room.archive_expires_at.timestamp()
                        ),
                        max_segments=room.max_segments,
                    )
                    if not reserved:
                        continue
                self._rooms[code] = room
                return room.public_payload(), host_token
        raise RuntimeError("Could not allocate a unique room code")

    async def get_snapshot(self, room_code: str) -> dict[str, Any] | None:
        async with self._lock:
            room = await self._room_locked(room_code)
            return room.public_payload() if room is not None else None

    async def authorize_host(self, room_code: str, host_token: str) -> bool:
        async with self._lock:
            room = await self._room_locked(room_code)
            return bool(
                room is not None
                and room.status == "live"
                and _token_matches(room, host_token)
            )

    async def bind_host_session(
        self,
        room_code: str,
        host_token: str,
        session_id: str,
    ) -> bool:
        async with self._lock:
            room = await self._room_locked(room_code)
            if (
                room is None
                or room.status != "live"
                or not _token_matches(room, host_token)
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
            room = await self._room_locked(room_code)
            if (
                room is None
                or room.status != "live"
                or not _token_matches(room, host_token)
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
            if self._store is not None:
                try:
                    await self._store.append_segment(
                        room_code=room.code,
                        sequence=room.sequence,
                        segment=segment,
                        archive_expires_epoch=int(
                            room.archive_expires_at.timestamp()
                        ),
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.error(
                        "room_segment_persistence_failed",
                        extra={
                            "event": "room_segment_persistence_failed",
                            "room_code": room.code,
                            "sequence": room.sequence,
                            "error": str(exc),
                        },
                    )
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
            room = await self._room_locked(room_code)
            if room is None:
                return None
            if room.status == "live":
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
            room = await self._room_locked(room_code)
            if room is None or not _token_matches(room, host_token):
                return False
            room.status = "ended"
            if self._store is not None:
                try:
                    await self._store.mark_ended(room.code)
                except Exception as exc:  # noqa: BLE001
                    logger.error(
                        "room_close_persistence_failed",
                        extra={
                            "event": "room_close_persistence_failed",
                            "room_code": room.code,
                            "error": str(exc),
                        },
                    )
            payload = {
                "type": "room_closed",
                "room_code": room.code,
                "sequence": room.sequence,
            }
            subscribers = tuple(room.subscribers)
            room.subscribers.clear()

        await self._broadcast(subscribers, payload)
        return True

    async def reset(self) -> None:
        """Clear process-local cache without deleting durable room records."""

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

    async def _room_locked(self, room_code: str) -> _Room | None:
        code = self._normalize_code(room_code)
        now = datetime.now(timezone.utc)
        room = self._rooms.get(code)
        if room is None and self._store is not None:
            persisted = await self._store.load_room(code)
            if persisted is not None:
                room = _room_from_persisted(persisted)
                self._rooms[code] = room
        if room is None:
            return None
        if room.archive_expires_at <= now:
            self._rooms.pop(code, None)
            return None
        if room.status == "live" and room.live_expires_at <= now:
            room.status = "ended"
            if self._store is not None:
                try:
                    await self._store.mark_ended(code)
                except Exception as exc:  # noqa: BLE001
                    logger.error(
                        "room_expiry_persistence_failed",
                        extra={
                            "event": "room_expiry_persistence_failed",
                            "room_code": code,
                            "error": str(exc),
                        },
                    )
        return room

    def _drop_expired_locked(self, now: datetime) -> None:
        expired = [
            code
            for code, room in self._rooms.items()
            if room.archive_expires_at <= now
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


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _token_matches(room: _Room, host_token: str) -> bool:
    return bool(
        host_token
        and secrets.compare_digest(room.host_token_hash, _hash_token(host_token))
    )


def _room_from_persisted(room: PersistedRoom) -> _Room:
    segments = deque(room.segments, maxlen=room.max_segments)
    return _Room(
        code=room.room_code,
        host_token_hash=room.host_token_hash,
        title=room.title,
        status=room.status,
        created_at=datetime.fromisoformat(room.created_at),
        live_expires_at=datetime.fromisoformat(room.live_expires_at),
        archive_expires_at=datetime.fromisoformat(room.archive_expires_at),
        max_segments=room.max_segments,
        sequence=room.sequence,
        segments=segments,
        segment_ids={
            segment_id
            for segment in room.segments
            if isinstance((segment_id := segment.get("segment_id")), str)
        },
    )


_room_service: RoomService | None = None
_room_service_key: tuple[str, str, int] | None = None


def get_room_service() -> RoomService:
    """Return the process-wide room service for the current settings."""

    from app.config import get_settings

    settings = get_settings()
    key = (
        settings.room_table_name,
        settings.aws_region,
        settings.room_retention_days,
    )
    global _room_service, _room_service_key
    if _room_service is None or _room_service_key != key:
        store: RoomArchiveStore | None = None
        if settings.room_table_name:
            from app.services.dynamo_room_store import DynamoRoomStore

            store = DynamoRoomStore(
                table_name=settings.room_table_name,
                region=settings.aws_region,
            )
        _room_service = RoomService(
            store=store,
            retention_days=settings.room_retention_days,
        )
        _room_service_key = key
    return _room_service
