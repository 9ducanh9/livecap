"""Tests for Stripe checkout/portal/webhook logic in stripe_billing.py.

The real `stripe` package is swapped out via `sys.modules` for a small fake
that mirrors the real SDK's shape (verified against the installed
stripe==11.6.0 package: stripe.Customer.{create,retrieve},
stripe.checkout.Session.create, stripe.billing_portal.Session.create,
stripe.Webhook.construct_event). No network calls, no real credentials.
"""

from __future__ import annotations

import json
import sys
import types

import boto3
import pytest
from moto import mock_aws

from app.config import get_settings
from app.services import stripe_billing, usage_quota

TABLE = "livecap-usage-billing-test"
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


class _FakeSignatureVerificationError(Exception):
    pass


class _FakeStripeModule(types.SimpleNamespace):
    """Minimal stand-in for the `stripe` package."""

    def __init__(self) -> None:
        super().__init__()
        self.api_key = None
        self._customers: dict[str, dict] = {}
        self._next_id = 0
        self.error = types.SimpleNamespace(
            SignatureVerificationError=_FakeSignatureVerificationError
        )
        fake = self

        class _Customer:
            @staticmethod
            def create(**kwargs):
                fake._next_id += 1
                customer_id = f"cus_{fake._next_id}"
                record = {"id": customer_id, "metadata": kwargs.get("metadata", {})}
                fake._customers[customer_id] = record
                return record

            @staticmethod
            def retrieve(customer_id):
                return fake._customers[customer_id]

        class _CheckoutSession:
            @staticmethod
            def create(**kwargs):
                return {"id": "cs_test_1", "url": "https://checkout.stripe.com/test-session"}

        class _Checkout:
            Session = _CheckoutSession

        class _PortalSession:
            @staticmethod
            def create(**kwargs):
                return {"id": "bps_test_1", "url": "https://billing.stripe.com/test-portal"}

        class _BillingPortal:
            Session = _PortalSession

        class _Webhook:
            @staticmethod
            def construct_event(payload, sig_header, secret):
                if sig_header != "valid-signature":
                    raise _FakeSignatureVerificationError("bad signature")
                return json.loads(payload)

        self.Customer = _Customer
        self.checkout = _Checkout
        self.billing_portal = _BillingPortal
        self.Webhook = _Webhook


@pytest.fixture
def fake_stripe(monkeypatch):
    fake = _FakeStripeModule()
    monkeypatch.setitem(sys.modules, "stripe", fake)
    return fake


@pytest.fixture
def billing_settings(monkeypatch):
    monkeypatch.setenv("ENABLE_STRIPE_BILLING", "true")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_fake")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_fake")
    monkeypatch.setenv("STRIPE_PRICE_ID_PRO", "price_pro")
    monkeypatch.setenv("STRIPE_PRICE_ID_BUSINESS", "price_business")
    monkeypatch.setenv("USAGE_TABLE_NAME", TABLE)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def dynamo_table():
    with mock_aws():
        client = boto3.client("dynamodb", region_name=REGION)
        _create_table(client)
        yield


def test_price_id_for_tier_resolves_configured_ids(billing_settings):
    assert stripe_billing._price_id_for_tier("pro") == "price_pro"
    assert stripe_billing._price_id_for_tier("business") == "price_business"


def test_price_id_for_tier_rejects_unknown_tier(billing_settings):
    with pytest.raises(stripe_billing.StripeBillingError):
        stripe_billing._price_id_for_tier("enterprise")


def test_ensure_customer_creates_once_and_reuses(billing_settings, fake_stripe, dynamo_table):
    first = stripe_billing.ensure_customer("user-1", "user1@example.com")
    second = stripe_billing.ensure_customer("user-1", "user1@example.com")

    assert first == second
    assert usage_quota.get_user_subscription("user-1").stripe_customer_id == first


def test_create_checkout_session_rejects_unknown_tier(billing_settings, fake_stripe, dynamo_table):
    with pytest.raises(stripe_billing.StripeBillingError):
        stripe_billing.create_checkout_session("user-1", "user1@example.com", "enterprise")


def test_create_checkout_session_returns_url(billing_settings, fake_stripe, dynamo_table):
    url = stripe_billing.create_checkout_session("user-1", "user1@example.com", "pro")
    assert url == "https://checkout.stripe.com/test-session"


def test_create_portal_session_requires_existing_customer(billing_settings, fake_stripe, dynamo_table):
    with pytest.raises(stripe_billing.StripeBillingError):
        stripe_billing.create_portal_session("user-without-subscription")


def test_create_portal_session_returns_url_once_customer_exists(
    billing_settings, fake_stripe, dynamo_table
):
    stripe_billing.ensure_customer("user-1", "user1@example.com")
    url = stripe_billing.create_portal_session("user-1")
    assert url == "https://billing.stripe.com/test-portal"


def test_webhook_rejects_bad_signature(billing_settings, fake_stripe, dynamo_table):
    with pytest.raises(stripe_billing.StripeBillingError):
        stripe_billing.handle_webhook_event(b"{}", "wrong-signature")


def test_webhook_checkout_completed_sets_tier(billing_settings, fake_stripe, dynamo_table):
    payload = json.dumps(
        {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "client_reference_id": "user-1",
                    "customer": "cus_1",
                    "subscription": "sub_1",
                    "metadata": {"cognito_user_id": "user-1", "livecap_tier": "pro"},
                }
            },
        }
    ).encode()

    stripe_billing.handle_webhook_event(payload, "valid-signature")

    sub = usage_quota.get_user_subscription("user-1")
    assert sub.tier == "pro"
    assert sub.stripe_customer_id == "cus_1"
    assert sub.stripe_subscription_id == "sub_1"
    assert sub.subscription_status == "active"


def test_webhook_subscription_deleted_reverts_to_free(billing_settings, fake_stripe, dynamo_table):
    customer = fake_stripe.Customer.create(metadata={"cognito_user_id": "user-1"})
    usage_quota.set_user_subscription(
        "user-1", tier="pro", stripe_customer_id=customer["id"], stripe_subscription_id="sub_1"
    )

    payload = json.dumps(
        {
            "type": "customer.subscription.deleted",
            "data": {"object": {"id": "sub_1", "customer": customer["id"]}},
        }
    ).encode()

    stripe_billing.handle_webhook_event(payload, "valid-signature")

    sub = usage_quota.get_user_subscription("user-1")
    assert sub.tier == "free"
    assert sub.subscription_status == "canceled"


def test_webhook_subscription_updated_reads_tier_from_price_metadata(
    billing_settings, fake_stripe, dynamo_table
):
    customer = fake_stripe.Customer.create(metadata={"cognito_user_id": "user-1"})

    payload = json.dumps(
        {
            "type": "customer.subscription.updated",
            "data": {
                "object": {
                    "id": "sub_1",
                    "customer": customer["id"],
                    "status": "active",
                    "items": {
                        "data": [
                            {"price": {"id": "price_business", "metadata": {"livecap_tier": "business"}}}
                        ]
                    },
                }
            },
        }
    ).encode()

    stripe_billing.handle_webhook_event(payload, "valid-signature")

    sub = usage_quota.get_user_subscription("user-1")
    assert sub.tier == "business"
    assert sub.subscription_status == "active"


def test_webhook_unresolvable_customer_is_ignored_not_raised(
    billing_settings, fake_stripe, dynamo_table
):
    payload = json.dumps(
        {
            "type": "customer.subscription.deleted",
            "data": {"object": {"id": "sub_1", "customer": "cus_does_not_exist"}},
        }
    ).encode()

    # Should not raise even though the customer lookup fails.
    stripe_billing.handle_webhook_event(payload, "valid-signature")
