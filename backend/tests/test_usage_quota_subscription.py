"""Tests for the persistent per-user subscription record (Stripe-driven tier).

Uses moto's in-memory DynamoDB, matching the existing
test_dynamo_session_registry.py convention. The point of this suite: a
user's `tier` must come from the persistent "PROFILE" item (set by Stripe
webhooks), never from a monthly usage counter item, since a subscription
doesn't reset just because a new month's session/minute counters do.
"""

from __future__ import annotations

import boto3
import pytest
from moto import mock_aws

from app.services import usage_quota

TABLE = "livecap-usage-test"
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
    with mock_aws():
        client = boto3.client("dynamodb", region_name=REGION)
        _create_table(client)
        yield


def test_get_user_subscription_defaults_to_free(dynamo_table):
    sub = usage_quota.get_user_subscription("user-1")
    assert sub.tier == "free"
    assert sub.stripe_customer_id is None
    assert sub.stripe_subscription_id is None
    assert sub.subscription_status is None


def test_set_user_subscription_persists_and_is_read_back(dynamo_table):
    usage_quota.set_user_subscription(
        "user-1",
        tier="pro",
        stripe_customer_id="cus_123",
        stripe_subscription_id="sub_123",
        subscription_status="active",
    )

    sub = usage_quota.get_user_subscription("user-1")

    assert sub.tier == "pro"
    assert sub.stripe_customer_id == "cus_123"
    assert sub.stripe_subscription_id == "sub_123"
    assert sub.subscription_status == "active"


def test_set_user_subscription_partial_update_does_not_clobber(dynamo_table):
    usage_quota.set_user_subscription("user-1", tier="pro", stripe_customer_id="cus_123")

    # A later call (e.g. from invoice.payment_failed) only updates status.
    usage_quota.set_user_subscription("user-1", tier="pro", subscription_status="past_due")

    sub = usage_quota.get_user_subscription("user-1")
    assert sub.tier == "pro"
    assert sub.stripe_customer_id == "cus_123"  # untouched by the second call
    assert sub.subscription_status == "past_due"


def test_get_user_usage_sources_tier_from_subscription_not_monthly_item(dynamo_table):
    # Simulate a webhook setting the tier without any session ever starting
    # this month.
    usage_quota.set_user_subscription("user-1", tier="business", stripe_customer_id="cus_1")

    usage = usage_quota.get_user_usage("user-1")

    assert usage.tier == "business"
    assert usage.sessions_used == 0
    assert usage.minutes_used == 0


def test_increment_session_no_longer_overrides_subscription_tier(dynamo_table):
    usage_quota.set_user_subscription("user-1", tier="business")

    # increment_session's own `tier` kwarg only ever wrote the *monthly* item's
    # tier field; that field is no longer read by get_user_usage.
    usage_quota.increment_session("user-1", tier="free")

    usage = usage_quota.get_user_usage("user-1")
    assert usage.tier == "business"
    assert usage.sessions_used == 1


def test_unknown_user_defaults_free_tier_limits(dynamo_table):
    usage = usage_quota.get_user_usage("brand-new-user")
    assert usage.tier == usage_quota.DEFAULT_TIER
    limits = usage_quota.TIERS[usage.tier]
    assert limits.max_sessions_per_month == 3
