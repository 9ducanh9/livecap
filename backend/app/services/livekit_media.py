"""LiveKit room lifecycle and least-privilege media credentials."""
from datetime import timedelta
import secrets

from livekit import api


class LiveKitMediaService:
    def __init__(self, settings):
        if not (settings.livekit_url and settings.livekit_api_key and settings.livekit_api_secret):
            raise ValueError("LiveKit backend credentials are not configured")
        self.settings = settings

    def client(self):
        return api.LiveKitAPI(
            self.settings.livekit_url, self.settings.livekit_api_key,
            self.settings.livekit_api_secret,
        )

    async def create_stage(self, *, room_code: str) -> str:
        # A fresh name prevents old credentials from joining a restarted broadcast.
        name = f"livecap-{room_code.lower()}-{secrets.token_hex(8)}"
        async with self.client() as client:
            await client.room.create_room(api.CreateRoomRequest(
                name=name, empty_timeout=60, departure_timeout=30,
                max_participants=3,
            ))
        return name

    async def create_token(self, *, stage_arn: str, role: str, duration_seconds: int) -> str:
        host = role == "host"
        return (api.AccessToken(self.settings.livekit_api_key, self.settings.livekit_api_secret)
                .with_identity("host" if host else f"viewer-{secrets.token_hex(12)}")
                .with_ttl(timedelta(seconds=duration_seconds))
                .with_grants(api.VideoGrants(
                    room_join=True, room=stage_arn, can_publish=host,
                    can_subscribe=not host, can_publish_data=False,
                    can_publish_sources=["screen_share", "microphone"] if host else [],
                )).to_jwt())

    async def delete_stage(self, stage_arn: str) -> None:
        async with self.client() as client:
            try:
                await client.room.delete_room(api.DeleteRoomRequest(room=stage_arn))
            except api.TwirpError as exc:
                if exc.code != "not_found":
                    raise
