"""Feature-gated shared-room API and viewer WebSocket."""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, WebSocket
from fastapi import WebSocketDisconnect, status
from pydantic import BaseModel, Field
from botocore.exceptions import BotoCoreError, ClientError

from app.config import get_settings
from app.services.auth import AuthenticatedUser, require_authenticated_user
from app.services.idle_scaler import get_idle_scale_down_scheduler
from app.services.room_service import get_room_service
from app.services.session_registry import get_session_registry
from app.services.ivs_realtime import IvsRealtimeService


router = APIRouter(tags=["shared rooms"])
logger = logging.getLogger(__name__)


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
    media_status: Literal["idle", "live"]


class ParticipantTokenResponse(BaseModel):
    token: str


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
        owner_user_id=_user.user_id if _user else None,
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
        media_status=room["media_status"],
    )


def _require_screen_share_enabled() -> None:
    _require_rooms_enabled()
    if not get_settings().enable_room_screen_share:
        raise HTTPException(status_code=404, detail="Room screen sharing is not enabled")


@router.post("/api/rooms/{room_code}/media/host-token", response_model=ParticipantTokenResponse)
async def create_host_media_token(
    room_code: str,
    room_token: str = Header(alias="X-LiveCap-Room-Token"),
    user: AuthenticatedUser | None = Depends(_authorize_room_host),
) -> ParticipantTokenResponse:
    _require_screen_share_enabled()
    settings = get_settings()
    ivs = IvsRealtimeService(region=settings.ivs_realtime_region)
    try:
        service = get_room_service()
        stage_arn = await service.prepare_media(
            room_code,
            room_token,
            user.user_id if user else None,
            lambda code: ivs.create_stage(room_code=code),
        )
        if stage_arn is None:
            raise HTTPException(status_code=403, detail="Only the room owner can share a screen")
        token = await ivs.create_token(
            stage_arn=stage_arn,
            role="host",
            duration_seconds=settings.ivs_participant_token_seconds,
        )
        activated = await service.activate_media(
            room_code,
            room_token,
            user.user_id if user else None,
            stage_arn,
        )
        if not activated:
            try:
                await ivs.delete_stage(stage_arn)
                await service.complete_media_stop(room_code, stage_arn)
            except (BotoCoreError, ClientError):
                pass
            raise HTTPException(status_code=409, detail="The room changed while screen sharing was starting")
        return ParticipantTokenResponse(token=token)
    except HTTPException:
        raise
    except (BotoCoreError, ClientError, KeyError) as exc:
        if isinstance(exc, ClientError):
            error = exc.response.get("Error", {})
            metadata = exc.response.get("ResponseMetadata", {})
            logger.error(
                "Screen-share host-token creation failed (aws_code=%s, request_id=%s, message=%s)",
                error.get("Code", "unknown"),
                metadata.get("RequestId", "unknown"),
                str(error.get("Message", ""))[:300],
            )
        else:
            logger.error(
                "Screen-share host-token creation failed (%s): %s",
                type(exc).__name__,
                str(exc)[:300],
            )
        pending_arn = await get_room_service().begin_media_stop(
            room_code, room_token, user.user_id if user else None
        )
        if pending_arn:
            try:
                await ivs.delete_stage(pending_arn)
                await get_room_service().complete_media_stop(room_code, pending_arn)
            except (BotoCoreError, ClientError):
                pass
        raise HTTPException(status_code=502, detail="Could not start the screen-share service") from exc


@router.post("/api/rooms/{room_code}/media/viewer-token", response_model=ParticipantTokenResponse)
async def create_viewer_media_token(room_code: str) -> ParticipantTokenResponse:
    _require_screen_share_enabled()
    settings = get_settings()
    stage_arn = await get_room_service().viewer_stage(room_code)
    if not stage_arn:
        raise HTTPException(status_code=409, detail="The host is not sharing a screen")
    try:
        token = await IvsRealtimeService(region=settings.ivs_realtime_region).create_token(
            stage_arn=stage_arn,
            role="viewer",
            duration_seconds=settings.ivs_participant_token_seconds,
        )
        return ParticipantTokenResponse(token=token)
    except (BotoCoreError, ClientError, KeyError) as exc:
        raise HTTPException(status_code=502, detail="Could not join the screen-share service") from exc


@router.post("/api/rooms/{room_code}/media/stop")
async def stop_room_media(
    room_code: str,
    room_token: str = Header(alias="X-LiveCap-Room-Token"),
    user: AuthenticatedUser | None = Depends(_authorize_room_host),
) -> dict[str, str]:
    _require_screen_share_enabled()
    settings = get_settings()
    service = get_room_service()
    stage_arn = await service.begin_media_stop(
        room_code, room_token, user.user_id if user else None
    )
    if not stage_arn:
        raise HTTPException(status_code=404, detail="Active screen share was not found")
    try:
        await IvsRealtimeService(region=settings.ivs_realtime_region).delete_stage(stage_arn)
    except (BotoCoreError, ClientError) as exc:
        raise HTTPException(status_code=502, detail="Screen-share cleanup is pending; please retry") from exc
    await service.complete_media_stop(room_code, stage_arn)
    return {"status": "stopped"}


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
    user: AuthenticatedUser | None = Depends(_authorize_room_host),
) -> dict[str, str]:
    _require_rooms_enabled()
    service = get_room_service()
    settings = get_settings()
    if settings.enable_room_screen_share:
        stage_arn = await service.begin_media_stop(
            room_code, room_token, user.user_id if user else None
        )
        if stage_arn:
            try:
                await IvsRealtimeService(region=settings.ivs_realtime_region).delete_stage(stage_arn)
                await service.complete_media_stop(room_code, stage_arn)
            except (BotoCoreError, ClientError) as exc:
                raise HTTPException(status_code=502, detail="Screen-share cleanup is pending; please retry") from exc
    closed = await service.close_room(room_code, room_token)
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
