"""Tests for admin_service: DynamoDB scan aggregation merged with the Cognito
user list, plus ECS system health.

DynamoDB uses moto, matching the existing usage_quota test convention (see
test_usage_quota_subscription.py). Cognito/ECS are patched directly at the
`boto3.client` call site since this suite is about the aggregation logic, not
AWS API fidelity -- `_scan_usage_table` uses `boto3.resource` (untouched by
this patch, so it still goes through moto), only `_list_cognito_users` and
`_system_health` use `boto3.client`.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

from app.config import get_settings
from app.services import admin_service

TABLE = "livecap-usage-test-admin"
REGION = "ap-southeast-1"


def _create_table(client) -> None:
    client.create_table(
        TableName=TABLE,
        KeySchema=[
            {"AttributeName": "pk", "KeyType": "HASH"},
            {"AttributeName": "sk", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "pk", "AttributeType": "S"},
            {"AttributeName": "sk", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )


@pytest.fixture
def dynamo_table(monkeypatch):
    monkeypatch.setenv("USAGE_TABLE_NAME", TABLE)
    get_settings.cache_clear()
    with mock_aws():
        client = boto3.client("dynamodb", region_name=REGION)
        _create_table(client)
        yield
    get_settings.cache_clear()


def _put_profile(user_id: str, tier: str, **extra) -> None:
    table = boto3.resource("dynamodb", region_name=REGION).Table(TABLE)
    table.put_item(Item={"pk": f"USER#{user_id}", "sk": "PROFILE", "tier": tier, "updated_at": 0, **extra})


def _put_month(user_id: str, sessions_used: int, minutes_used: int, month_key: str) -> None:
    table = boto3.resource("dynamodb", region_name=REGION).Table(TABLE)
    table.put_item(Item={
        "pk": f"USER#{user_id}", "sk": month_key,
        "sessions_used": sessions_used, "minutes_used": minutes_used, "updated_at": 0,
    })


def test_scan_usage_table_buckets_profile_and_month_items(dynamo_table):
    month_key = admin_service._current_month_key()
    _put_profile("user-1", "pro", stripe_customer_id="cus_1", subscription_status="active")
    _put_month("user-1", 2, 30, month_key)
    _put_month("user-1", 999, 999, "MONTH#2000-01")  # a past month, must be ignored

    by_user = admin_service._scan_usage_table(REGION)

    assert by_user["user-1"]["profile"]["tier"] == "pro"
    assert by_user["user-1"]["month"]["sessions_used"] == 2
    assert by_user["user-1"]["month"]["minutes_used"] == 30


def test_scan_usage_table_returns_empty_on_missing_table(monkeypatch):
    monkeypatch.setenv("USAGE_TABLE_NAME", "does-not-exist-table")
    get_settings.cache_clear()
    with mock_aws():
        result = admin_service._scan_usage_table(REGION)
    assert result == {}
    get_settings.cache_clear()


def _fake_cognito_client(users: list[dict]):
    client = MagicMock()
    client.list_users.return_value = {"Users": users, "PaginationToken": None}
    return client


def test_get_admin_overview_merges_cognito_and_usage(dynamo_table, monkeypatch):
    monkeypatch.setenv("COGNITO_USER_POOL_ID", "pool-1")
    monkeypatch.setenv("ECS_CLUSTER_NAME", "cluster-1")
    monkeypatch.setenv("ECS_SERVICE_NAME", "service-1")
    get_settings.cache_clear()

    month_key = admin_service._current_month_key()
    _put_profile("user-1", "pro")
    _put_month("user-1", 3, 45, month_key)
    _put_profile("user-2", "free")

    cognito_users = [
        {"Username": "u1", "Attributes": [{"Name": "sub", "Value": "user-1"}, {"Name": "email", "Value": "a@x.com"}]},
        {"Username": "u2", "Attributes": [{"Name": "sub", "Value": "user-2"}, {"Name": "email", "Value": "b@x.com"}]},
        # Registered but never started a session / never checked out -- no DynamoDB item at all.
        {"Username": "u3", "Attributes": [{"Name": "sub", "Value": "user-3"}, {"Name": "email", "Value": "c@x.com"}]},
    ]

    fake_ecs = MagicMock()
    fake_ecs.describe_services.return_value = {
        "services": [{"desiredCount": 1, "runningCount": 1, "pendingCount": 0}]
    }

    def _client_factory(service_name, region_name=None):
        if service_name == "cognito-idp":
            return _fake_cognito_client(cognito_users)
        if service_name == "ecs":
            return fake_ecs
        raise AssertionError(f"unexpected boto3.client({service_name!r})")

    with patch.object(admin_service.boto3, "client", side_effect=_client_factory):
        overview = admin_service.get_admin_overview()

    by_id = {row.user_id: row for row in overview.users}
    assert by_id["user-1"].tier == "pro"
    assert by_id["user-1"].email == "a@x.com"
    assert by_id["user-1"].sessions_used == 3
    assert by_id["user-1"].minutes_used == 45
    assert by_id["user-2"].tier == "free"
    assert by_id["user-3"].tier == "free"  # no PROFILE item -> defaults
    assert by_id["user-3"].sessions_used == 0

    assert overview.stats["total_users"] == 3
    assert overview.stats["by_tier"]["pro"] == 1
    assert overview.stats["by_tier"]["free"] == 2
    assert overview.stats["by_tier"]["business"] == 0
    assert overview.stats["total_sessions_this_month"] == 3
    assert overview.stats["total_minutes_this_month"] == 45
    assert overview.stats["estimated_mrr_usd"] == 10  # 1 pro user * $10/mo

    assert overview.system["backend_reachable"] is True
    assert overview.system["desired_count"] == 1
    assert overview.system["running_count"] == 1


def test_system_health_reports_unreachable_on_ecs_error():
    fake_ecs = MagicMock()
    fake_ecs.describe_services.side_effect = ClientError(
        {"Error": {"Code": "ClusterNotFoundException", "Message": "no"}}, "DescribeServices"
    )
    with patch.object(admin_service.boto3, "client", return_value=fake_ecs):
        result = admin_service._system_health(REGION, "cluster-1", "service-1")
    assert result["backend_reachable"] is False
    assert result["desired_count"] is None


def test_system_health_no_cluster_configured():
    result = admin_service._system_health(REGION, "", "")
    assert result["backend_reachable"] is False
    assert result["desired_count"] is None


def test_list_cognito_users_empty_when_pool_not_configured():
    assert admin_service._list_cognito_users(REGION, "") == {}
