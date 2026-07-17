"""Tests for the DynamoDB-backed active session registry.

Uses moto's in-memory DynamoDB so the registry is exercised against a real
DynamoDB API surface without touching AWS.
"""

from __future__ import annotations

import boto3
import pytest
from moto import mock_aws

from app.services.dynamo_session_registry import DynamoDbSessionRegistry

TABLE = "livecap-sessions-test"
REGION = "ap-southeast-1"


def _create_table(client) -> None:
    client.create_table(
        TableName=TABLE,
        KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )


@pytest.fixture
def registry():
    with mock_aws():
        client = boto3.client("dynamodb", region_name=REGION)
        _create_table(client)
        yield DynamoDbSessionRegistry(
            table_name=TABLE, region=REGION, ttl_seconds=3600, client=client
        )


def test_register_within_limits(registry):
    result = registry.try_register(
        session_id="s1", client_ip="1.1.1.1", max_total=4, max_per_ip=1
    )
    assert result.allowed is True
    assert registry.active_count == 1
    assert registry.active_count_for_ip("1.1.1.1") == 1


def test_global_limit_rejects(registry):
    for i in range(4):
        r = registry.try_register(
            session_id=f"s{i}", client_ip=f"10.0.0.{i}", max_total=4, max_per_ip=5
        )
        assert r.allowed is True
    blocked = registry.try_register(
        session_id="s5", client_ip="10.0.0.99", max_total=4, max_per_ip=5
    )
    assert blocked.allowed is False
    assert blocked.reason == "global_limit"


def test_per_ip_limit_rejects(registry):
    first = registry.try_register(
        session_id="a", client_ip="2.2.2.2", max_total=10, max_per_ip=1
    )
    assert first.allowed is True
    second = registry.try_register(
        session_id="b", client_ip="2.2.2.2", max_total=10, max_per_ip=1
    )
    assert second.allowed is False
    assert second.reason == "per_ip_limit"


def test_unregister_frees_capacity(registry):
    registry.try_register(
        session_id="x", client_ip="3.3.3.3", max_total=1, max_per_ip=1
    )
    assert registry.active_count == 1
    # At capacity: a different IP is rejected.
    assert (
        registry.try_register(
            session_id="y", client_ip="4.4.4.4", max_total=1, max_per_ip=1
        ).allowed
        is False
    )
    registry.unregister("x")
    assert registry.active_count == 0
    # Capacity freed.
    assert (
        registry.try_register(
            session_id="y", client_ip="4.4.4.4", max_total=1, max_per_ip=1
        ).allowed
        is True
    )


def test_reregister_same_id_is_idempotent(registry):
    r1 = registry.try_register(
        session_id="dup", client_ip="5.5.5.5", max_total=4, max_per_ip=5
    )
    r2 = registry.try_register(
        session_id="dup", client_ip="5.5.5.5", max_total=4, max_per_ip=5
    )
    assert r1.allowed is True
    assert r2.allowed is True
    assert registry.active_count == 1


def test_unregister_unknown_id_is_safe(registry):
    registry.unregister("does-not-exist")  # must not raise
    assert registry.active_count == 0


def test_clear_removes_all(registry):
    for i in range(3):
        registry.try_register(
            session_id=f"c{i}", client_ip="6.6.6.6", max_total=10, max_per_ip=10
        )
    assert registry.active_count == 3
    registry.clear()
    assert registry.active_count == 0


def test_per_ip_count_isolates_ips(registry):
    registry.try_register(session_id="p1", client_ip="7.7.7.7", max_total=10, max_per_ip=10)
    registry.try_register(session_id="p2", client_ip="7.7.7.7", max_total=10, max_per_ip=10)
    registry.try_register(session_id="p3", client_ip="8.8.8.8", max_total=10, max_per_ip=10)
    assert registry.active_count_for_ip("7.7.7.7") == 2
    assert registry.active_count_for_ip("8.8.8.8") == 1
    assert registry.active_count == 3
