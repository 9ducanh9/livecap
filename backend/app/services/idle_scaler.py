"""Delayed ECS scale-to-zero for idle backend tasks.

This module is intentionally disabled by default. When enabled in ECS, it waits
for a grace period after the last active WebSocket session ends, then asks ECS
to set the service desired count to zero. A new session cancels the pending
scale-down.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Protocol

import boto3

from app.config import Settings
from app.services.session_registry import ActiveSessionRegistry

logger = logging.getLogger(__name__)


class ECSScaleClient(Protocol):
    """Small protocol for the ECS action this module needs."""

    async def scale_down(self, *, cluster_name: str, service_name: str) -> None:
        """Set ECS service desired count to zero."""


@dataclass(frozen=True)
class IdleScaleDownConfig:
    """Runtime config for delayed idle scale-down."""

    enabled: bool
    grace_seconds: int
    cluster_name: str
    service_name: str

    @classmethod
    def from_settings(cls, settings: Settings) -> "IdleScaleDownConfig":
        return cls(
            enabled=settings.enable_idle_scale_down,
            grace_seconds=settings.idle_scale_down_grace_seconds,
            cluster_name=settings.ecs_cluster_name,
            service_name=settings.ecs_service_name,
        )

    @property
    def is_complete(self) -> bool:
        return bool(self.cluster_name and self.service_name)


class Boto3ECSScaleClient:
    """ECS UpdateService client used by production idle scale-down."""

    def __init__(self, *, region_name: str) -> None:
        self._ecs_client = boto3.client("ecs", region_name=region_name)

    async def scale_down(self, *, cluster_name: str, service_name: str) -> None:
        await asyncio.to_thread(
            self._ecs_client.update_service,
            cluster=cluster_name,
            service=service_name,
            desiredCount=0,
        )


class IdleScaleDownScheduler:
    """Owns the one pending idle scale-down task for this backend process."""

    def __init__(
        self,
        *,
        registry: ActiveSessionRegistry,
        ecs_client: ECSScaleClient | None = None,
    ) -> None:
        self._registry = registry
        self._ecs_client = ecs_client
        self._pending_task: asyncio.Task[None] | None = None

    @property
    def has_pending_task(self) -> bool:
        return self._pending_task is not None and not self._pending_task.done()

    def cancel_pending(self) -> None:
        """Cancel any delayed scale-down because a new session is active."""

        if self._pending_task is not None and not self._pending_task.done():
            self._pending_task.cancel()
        self._pending_task = None

    def schedule_if_idle(
        self,
        *,
        settings: Settings,
        ecs_client: ECSScaleClient | None = None,
    ) -> bool:
        """Schedule ECS desired_count=0 if enabled and no sessions remain."""

        config = IdleScaleDownConfig.from_settings(settings)
        if not config.enabled:
            return False
        if not config.is_complete:
            logger.warning(
                "idle_scale_down_missing_ecs_config",
                extra={
                    "event": "idle_scale_down_missing_ecs_config",
                    "has_cluster": bool(config.cluster_name),
                    "has_service": bool(config.service_name),
                },
            )
            return False
        if self._registry.active_count > 0:
            return False

        self.cancel_pending()
        client = ecs_client or self._ecs_client or Boto3ECSScaleClient(
            region_name=settings.aws_region
        )
        self._pending_task = asyncio.create_task(self._scale_down_after_grace(config, client))
        return True

    async def _scale_down_after_grace(
        self,
        config: IdleScaleDownConfig,
        ecs_client: ECSScaleClient,
    ) -> None:
        try:
            await asyncio.sleep(config.grace_seconds)
            if self._registry.active_count > 0:
                return
            await ecs_client.scale_down(
                cluster_name=config.cluster_name,
                service_name=config.service_name,
            )
            logger.info(
                "idle_scale_down_requested",
                extra={
                    "event": "idle_scale_down_requested",
                    "cluster": config.cluster_name,
                    "service": config.service_name,
                },
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "idle_scale_down_failed",
                extra={
                    "event": "idle_scale_down_failed",
                    "cluster": config.cluster_name,
                    "service": config.service_name,
                    "error": str(exc),
                },
            )
        finally:
            current_task = asyncio.current_task()
            if self._pending_task is current_task:
                self._pending_task = None


idle_scale_down_scheduler: IdleScaleDownScheduler | None = None


def get_idle_scale_down_scheduler(
    registry: ActiveSessionRegistry,
) -> IdleScaleDownScheduler:
    """Return the process-wide idle scale-down scheduler."""

    global idle_scale_down_scheduler
    if idle_scale_down_scheduler is None:
        idle_scale_down_scheduler = IdleScaleDownScheduler(registry=registry)
    return idle_scale_down_scheduler
