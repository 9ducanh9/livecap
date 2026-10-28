from types import SimpleNamespace
import asyncio
from unittest.mock import AsyncMock

import jwt
import pytest

from app.services.livekit_media import LiveKitMediaService


def service():
    return LiveKitMediaService(SimpleNamespace(
        livekit_url="wss://test.livekit.cloud", livekit_api_key="test-key",
        livekit_api_secret="test-secret-for-token-verification-only",
    ))


@pytest.mark.parametrize("role", ["host", "viewer"])
def test_tokens_are_room_scoped_and_least_privilege(role):
    token = asyncio.run(service().create_token(stage_arn="opaque-room", role=role, duration_seconds=300))
    claims = jwt.decode(token, service().settings.livekit_api_secret, algorithms=["HS256"])
    grants = claims["video"]
    assert grants["room"] == "opaque-room"
    assert grants["roomJoin"] is True
    assert grants["canPublish"] is (role == "host")
    assert grants["canSubscribe"] is (role == "viewer")
    assert grants["canPublishData"] is False
    assert not grants.get("roomAdmin")
    assert not grants.get("roomCreate")
    assert claims["exp"] - claims["nbf"] == 300
    if role == "host":
        assert grants["canPublishSources"] == ["screen_share", "microphone"]


def test_room_restart_uses_new_name_and_limits_participants():
    asyncio.run(check_room_lifecycle())


async def check_room_lifecycle():
    provider = service()
    client = AsyncMock()
    client.__aenter__.return_value = client
    provider.client = lambda: client
    first = await provider.create_stage(room_code="ABC234")
    second = await provider.create_stage(room_code="ABC234")
    assert first != second
    request = client.room.create_room.call_args.args[0]
    assert request.max_participants == 3
    assert request.empty_timeout == 60
    await provider.delete_stage(first)
    assert client.room.delete_room.call_args.args[0].room == first


def test_missing_secret_fails_closed():
    with pytest.raises(ValueError):
        LiveKitMediaService(SimpleNamespace(livekit_url="wss://test.livekit.cloud",
                                           livekit_api_key="key", livekit_api_secret=""))


def test_livekit_routes_preserve_host_authorization_and_stop(monkeypatch):
    from fastapi.testclient import TestClient
    from app.config import get_settings
    from app.main import app
    from app.routers import rooms
    from app.services.room_service import get_room_service

    for key, value in {"ENABLE_SHARED_ROOMS": "true", "ENABLE_ROOM_SCREEN_SHARE": "true",
                       "ENABLE_AUTH": "false", "ROOM_MEDIA_PROVIDER": "livekit",
                       "LIVEKIT_URL": "wss://test.livekit.cloud"}.items():
        monkeypatch.setenv(key, value)
    provider = AsyncMock()
    provider.create_stage.return_value = "opaque-broadcast"
    provider.create_token.return_value = "signed-token"
    monkeypatch.setattr(rooms, "_media_service", lambda settings: provider)
    get_settings.cache_clear()
    asyncio.run(get_room_service().reset())
    try:
        with TestClient(app) as client:
            room = client.post("/api/rooms", json={"title": "Test"}).json()
            base = f"/api/rooms/{room['room_code']}/media"
            rejected = client.post(base + "/host-token", headers={"X-LiveCap-Room-Token": "wrong"})
            assert rejected.status_code == 403
            provider.create_stage.assert_not_called()
            headers = {"X-LiveCap-Room-Token": room["host_token"]}
            host = client.post(base + "/host-token", headers=headers)
            assert host.status_code == 200
            assert host.json() == {"token": "signed-token", "provider": "livekit", "url": "wss://test.livekit.cloud"}
            assert client.post(base + "/viewer-token").status_code == 200
            assert provider.create_token.call_args.kwargs["role"] == "viewer"
            assert client.post(base + "/stop", headers=headers).status_code == 200
            provider.delete_stage.assert_awaited_once_with("opaque-broadcast")
            assert client.post(base + "/viewer-token").status_code == 409
    finally:
        get_settings.cache_clear()
