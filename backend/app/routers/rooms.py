"""Feature-gated shared-room API and viewer WebSocket."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, WebSocket
from fastapi import WebSocketDisconnect, status
from pydantic import BaseModel, Field

from app.config import get_settings
from app.services.auth import AuthenticatedUser, require_authenticated_user
from app.services.idle_scaler import get_idle_scale_down_scheduler
from app.services.room_service import get_room_service
from app.services.session_registry import get_session_registry


router = APIRouter(tags=["shared rooms"])


class CreateRoomRequest(BaseModel):
    title: str = Field(default="LiveCap room", min_length=1, max_length=80)


class CreateRoomResponse(BaseModel):
    room_code: str
    host_token: str
    join_url: str
    title: str
    status: Literal["live", "ended"]
    created_at: str
    live_expires_at: str
    expires_at: str


def _require_rooms_enabled() -> None:
    if not get_settings().enable_shared_rooms:
        raise HTTPException(status_code=404, detail="Shared rooms are not enabled")


async def _authorize_room_host(
    authorization: str | None = Header(default=None),
) -> AuthenticatedUser | None:
    """Hide disabled routes before applying the optional Cognito host gate."""

    _require_rooms_enabled()
    if not get_settings().enable_auth:
        return None
    return await require_authenticated_user(authorization)


@router.post("/api/rooms", response_model=CreateRoomResponse, status_code=201)
async def create_room(
    request: CreateRoomRequest,
    _user: AuthenticatedUser | None = Depends(_authorize_room_host),
) -> CreateRoomResponse:
    settings = get_settings()
    room, host_token = await get_room_service().create_room(
        title=request.title,
        ttl_seconds=settings.room_ttl_seconds,
        max_segments=settings.room_max_segments,
    )
    join_url = (
        f"{settings.frontend_base_url.rstrip('/')}/rooms/{room['room_code']}"
    )
    return CreateRoomResponse(
        room_code=room["room_code"],
        host_token=host_token,
        join_url=join_url,
        title=room["title"],
        status=room["status"],
        created_at=room["created_at"],
        live_expires_at=room["live_expires_at"],
        expires_at=room["expires_at"],
    )


@router.get("/api/rooms/{room_code}")
async def get_room(room_code: str) -> dict:
    _require_rooms_enabled()
    room = await get_room_service().get_snapshot(room_code)
    if room is None:
        raise HTTPException(status_code=404, detail="Room was not found")
    return room


@router.post("/api/rooms/{room_code}/close")
async def close_room(
    room_code: str,
    room_token: str = Header(alias="X-LiveCap-Room-Token"),
) -> dict[str, str]:
    _require_rooms_enabled()
    closed = await get_room_service().close_room(room_code, room_token)
    if not closed:
        raise HTTPException(status_code=404, detail="Room was not found")
    return {"status": "closed"}


@router.websocket("/ws/rooms/{room_code}")
async def room_viewer_socket(websocket: WebSocket, room_code: str) -> None:
    await websocket.accept()
    if not get_settings().enable_shared_rooms:
        await websocket.send_json(
            {"type": "room_error", "message": "Shared rooms are not enabled"}
        )
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    service = get_room_service()
    snapshot = await service.subscribe(room_code, websocket)
    if snapshot is None:
        await websocket.send_json(
            {"type": "room_error", "message": "Room was not found or expired"}
        )
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.send_json(snapshot)
    if snapshot["status"] == "ended":
        await websocket.close(code=status.WS_1000_NORMAL_CLOSURE)
        settings = get_settings()
        registry = get_session_registry(settings)
        get_idle_scale_down_scheduler(registry).schedule_if_idle(
            settings=settings
        )
        return

    try:
        while True:
            message = await websocket.receive_json()
            if isinstance(message, dict) and message.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        await service.unsubscribe(room_code, websocket)
