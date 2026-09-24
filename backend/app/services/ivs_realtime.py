"""Amazon IVS Real-Time stage lifecycle for one-host audience rooms."""

from __future__ import annotations

import asyncio
from functools import lru_cache
from typing import Literal

import boto3
from botocore.config import Config


@lru_cache(maxsize=4)
def _client(region: str):
    return boto3.client(
        "ivs-realtime",
        region_name=region,
        config=Config(
            connect_timeout=3,
            read_timeout=8,
            retries={"mode": "standard", "max_attempts": 3},
        ),
    )


class IvsRealtimeService:
    """Create stages and least-privilege participant tokens."""

    def __init__(self, *, region: str) -> None:
        self._client = _client(region)

    async def create_stage(self, *, room_code: str) -> str:
        response = await asyncio.to_thread(
            self._client.create_stage,
            name=f"livecap-{room_code.lower()}",
            tags={"app": "livecap", "room": room_code},
        )
        return str(response["stage"]["arn"])

    async def create_token(
        self,
        *,
        stage_arn: str,
        role: Literal["host", "viewer"],
        duration_seconds: int,
    ) -> str:
        capability = "PUBLISH" if role == "host" else "SUBSCRIBE"
        response = await asyncio.to_thread(
            self._client.create_participant_token,
            stageArn=stage_arn,
            capabilities=[capability],
            duration=duration_seconds,
            userId=f"{role}-{__import__('secrets').token_hex(8)}",
            attributes={"role": role},
        )
        return str(response["participantToken"]["token"])

    async def delete_stage(self, stage_arn: str) -> None:
        await asyncio.to_thread(self._client.delete_stage, arn=stage_arn)


def clear_ivs_client_cache() -> None:
    _client.cache_clear()
