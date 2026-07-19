"""Tests for the billing router: auth requirement, feature flag gate, and
error mapping. Stripe calls themselves are exercised in test_stripe_billing.py;
here `app.services.stripe_billing` functions are patched so these tests focus
purely on routing/HTTP behaviour.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import get_settings
from app.routers import billing
from app.routers.billing import router
from app.services.auth import AuthenticatedUser, require_authenticated_user
from app.services.stripe_billing import StripeBillingError


def _client(with_auth: bool = True) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    if with_auth:
        app.dependency_overrides[require_authenticated_user] = lambda: AuthenticatedUser(
            "user-1", "user-1", "user1@example.com"
        )
    return TestClient(app)


@pytest.fixture(autouse=True)
def clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_checkout_session_404_when_billing_disabled(monkeypatch):
    monkeypatch.delenv("ENABLE_STRIPE_BILLING", raising=False)
    resp = _client().post("/api/billing/checkout-session", json={"tier": "pro"})
    assert resp.status_code == 404


def test_checkout_session_requires_auth(monkeypatch):
    monkeypatch.setenv("ENABLE_STRIPE_BILLING", "true")
    resp = _client(with_auth=False).post("/api/billing/checkout-session", json={"tier": "pro"})
    assert resp.status_code == 401


def test_checkout_session_returns_url(monkeypatch):
    monkeypatch.setenv("ENABLE_STRIPE_BILLING", "true")
    with patch.object(billing.stripe_billing, "create_checkout_session", return_value="https://checkout.stripe.com/x") as m:
        resp = _client().post("/api/billing/checkout-session", json={"tier": "pro"})
    assert resp.status_code == 200
    assert resp.json() == {"url": "https://checkout.stripe.com/x"}
    m.assert_called_once_with("user-1", "user1@example.com", "pro")


def test_checkout_session_maps_billing_error_to_400(monkeypatch):
    monkeypatch.setenv("ENABLE_STRIPE_BILLING", "true")
    with patch.object(
        billing.stripe_billing, "create_checkout_session", side_effect=StripeBillingError("bad tier")
    ):
        resp = _client().post("/api/billing/checkout-session", json={"tier": "nope"})
    assert resp.status_code == 400


def test_portal_session_requires_auth(monkeypatch):
    monkeypatch.setenv("ENABLE_STRIPE_BILLING", "true")
    resp = _client(with_auth=False).post("/api/billing/portal-session")
    assert resp.status_code == 401


def test_portal_session_returns_url(monkeypatch):
    monkeypatch.setenv("ENABLE_STRIPE_BILLING", "true")
    with patch.object(billing.stripe_billing, "create_portal_session", return_value="https://billing.stripe.com/x"):
        resp = _client().post("/api/billing/portal-session")
    assert resp.status_code == 200
    assert resp.json() == {"url": "https://billing.stripe.com/x"}


def test_webhook_404_when_billing_disabled(monkeypatch):
    monkeypatch.delenv("ENABLE_STRIPE_BILLING", raising=False)
    resp = _client(with_auth=False).post("/api/billing/webhook", data=b"{}")
    assert resp.status_code == 404


def test_webhook_does_not_require_cognito_auth(monkeypatch):
    """Stripe calls this endpoint directly; it must not require a bearer token."""
    monkeypatch.setenv("ENABLE_STRIPE_BILLING", "true")
    with patch.object(billing.stripe_billing, "handle_webhook_event", return_value=None) as m:
        resp = _client(with_auth=False).post(
            "/api/billing/webhook", data=b'{"type": "x"}', headers={"stripe-signature": "sig"}
        )
    assert resp.status_code == 200
    assert resp.json() == {"received": True}
    m.assert_called_once_with(b'{"type": "x"}', "sig")


def test_webhook_bad_signature_returns_400(monkeypatch):
    monkeypatch.setenv("ENABLE_STRIPE_BILLING", "true")
    with patch.object(
        billing.stripe_billing, "handle_webhook_event", side_effect=StripeBillingError("bad sig")
    ):
        resp = _client(with_auth=False).post("/api/billing/webhook", data=b"{}")
    assert resp.status_code == 400


def test_webhook_unexpected_error_returns_500_so_stripe_retries(monkeypatch):
    monkeypatch.setenv("ENABLE_STRIPE_BILLING", "true")
    with patch.object(billing.stripe_billing, "handle_webhook_event", side_effect=RuntimeError("boom")):
        resp = _client(with_auth=False).post("/api/billing/webhook", data=b"{}")
    assert resp.status_code == 500
