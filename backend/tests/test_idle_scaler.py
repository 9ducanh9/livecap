from __future__ import annotations

import asyncio

from app.config import Settings
from app.services.idle_scaler import IdleScaleDownScheduler
from app.services.session_registry import ActiveSessionRegistry


class FakeECSScaleClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def scale_down(self, *, cluster_name: str, service_name: str) -> None:
        self.calls.append((cluster_name, service_name))


def make_settings(**overrides) -> Settings:
    defaults = dict(
        enable_idle_scale_down=True,
        idle_scale_down_grace_seconds=0,
        ecs_cluster_name="livecap-cluster-dev",
        ecs_service_name="livecap-backend-service-dev",
        aws_region="ap-southeast-1",
    )
    defaults.update(overrides)
    return Settings(**defaults)


async def wait_for_pending_tasks() -> None:
    await asyncio.sleep(0)
    await asyncio.sleep(0)


def test_idle_scale_down_disabled_without_ecs_config_does_not_crash() -> None:
    registry = ActiveSessionRegistry()
    scheduler = IdleScaleDownScheduler(registry=registry)

    scheduled = scheduler.schedule_if_idle(
        settings=make_settings(
            enable_idle_scale_down=False,
            ecs_cluster_name="",
            ecs_service_name="",
        )
    )

    assert scheduled is False
    assert scheduler.has_pending_task is False


def test_idle_scale_down_not_scheduled_when_sessions_remain_active() -> None:
    registry = ActiveSessionRegistry()
    registry.try_register(
        session_id="active",
        client_ip="203.0.113.10",
        max_total=4,
        max_per_ip=1,
    )
    scheduler = IdleScaleDownScheduler(registry=registry)

    scheduled = scheduler.schedule_if_idle(settings=make_settings())

    assert scheduled is False
    assert scheduler.has_pending_task is False


def test_idle_scale_down_scheduled_when_last_session_ends() -> None:
    async def run() -> None:
        registry = ActiveSessionRegistry()
        registry.try_register(
            session_id="active",
            client_ip="203.0.113.10",
            max_total=4,
            max_per_ip=1,
        )
        registry.unregister("active")
        fake_client = FakeECSScaleClient()
        scheduler = IdleScaleDownScheduler(registry=registry)

        scheduled = scheduler.schedule_if_idle(
            settings=make_settings(),
            ecs_client=fake_client,
        )
        await wait_for_pending_tasks()

        assert scheduled is True
        assert fake_client.calls == [
            ("livecap-cluster-dev", "livecap-backend-service-dev")
        ]

    asyncio.run(run())


def test_new_session_cancels_pending_idle_scale_down() -> None:
    async def run() -> None:
        registry = ActiveSessionRegistry()
        fake_client = FakeECSScaleClient()
        scheduler = IdleScaleDownScheduler(registry=registry)

        scheduled = scheduler.schedule_if_idle(
            settings=make_settings(idle_scale_down_grace_seconds=60),
            ecs_client=fake_client,
        )
        registry.try_register(
            session_id="new-session",
            client_ip="203.0.113.20",
            max_total=4,
            max_per_ip=1,
        )
        scheduler.cancel_pending()
        await wait_for_pending_tasks()

        assert scheduled is True
        assert scheduler.has_pending_task is False
        assert fake_client.calls == []

    asyncio.run(run())
