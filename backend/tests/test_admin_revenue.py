"""Integration tests for admin_revenue service.

Tests revenue calculation with mocked Stripe responses and graceful
degradation when Stripe is unreachable.

Validates: Requirements 12.5
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.config import get_settings
from app.services.admin_revenue import (
    RevenueMetrics,
    StripeTransaction,
    get_recent_transactions,
    get_revenue_metrics,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_subscription(sub_id: str, unit_amount: int, interval: str = "month", interval_count: int = 1):
    """Build a fake Stripe subscription dict."""
    return {
        "id": sub_id,
        "status": "active",
        "items": {
            "data": [
                {
                    "price": {
                        "unit_amount": unit_amount,
                        "recurring": {
                            "interval": interval,
                            "interval_count": interval_count,
                        },
                    }
                }
            ]
        },
    }


def _make_canceled_subscription(sub_id: str, canceled_at: int):
    """Build a fake canceled Stripe subscription dict."""
    return {
        "id": sub_id,
        "status": "canceled",
        "canceled_at": canceled_at,
        "items": {"data": []},
    }


def _make_charge(charge_id: str, amount: int, email: str | None = None, refunded: bool = False):
    """Build a fake Stripe charge dict."""
    return {
        "id": charge_id,
        "amount": amount,
        "currency": "usd",
        "refunded": refunded,
        "created": int(time.time()),
        "receipt_email": email,
        "customer": {"email": email} if email else None,
    }


# ---------------------------------------------------------------------------
# Tests: MRR Calculation
# ---------------------------------------------------------------------------


class TestRevenueMetricsMRR:
    """Test MRR calculation with mocked Stripe Subscription.list."""

    def test_mrr_with_three_active_subs_at_10_dollars(self, monkeypatch):
        """3 active subscriptions at $10/month = $30 MRR."""
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_fake")
        get_settings.cache_clear()

        subs = [
            _make_subscription(f"sub_{i}", 1000)  # $10.00 in cents
            for i in range(3)
        ]

        mock_stripe = MagicMock()
        # Active subscription call
        mock_stripe.Subscription.list.side_effect = [
            # First call: active subs
            {"data": subs, "has_more": False},
            # Second call: trialing subs (empty)
            {"data": [], "has_more": False},
            # Third call: canceled subs
            {"data": [], "has_more": False},
        ]
        mock_stripe.Charge.list.return_value = {"data": []}

        with patch("app.services.admin_revenue._get_stripe", return_value=mock_stripe):
            result = get_revenue_metrics()

        assert result.stripe_data_available is True
        assert result.mrr_usd == 30.0
        assert result.active_subscriptions == 3
        assert result.warning is None
        get_settings.cache_clear()

    def test_mrr_with_annual_subscription_normalized_to_monthly(self, monkeypatch):
        """Annual subscription at $120/year → $10/month MRR."""
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_fake")
        get_settings.cache_clear()

        subs = [_make_subscription("sub_annual", 12000, interval="year")]  # $120/year

        mock_stripe = MagicMock()
        mock_stripe.Subscription.list.side_effect = [
            {"data": subs, "has_more": False},
            {"data": [], "has_more": False},
            {"data": [], "has_more": False},
        ]
        mock_stripe.Charge.list.return_value = {"data": []}

        with patch("app.services.admin_revenue._get_stripe", return_value=mock_stripe):
            result = get_revenue_metrics()

        assert result.mrr_usd == 10.0
        get_settings.cache_clear()


# ---------------------------------------------------------------------------
# Tests: Churned Subscriptions
# ---------------------------------------------------------------------------


class TestChurnedSubscriptions:
    """Test churned subscription count (canceled in last 30 days)."""

    def test_churned_count_with_recent_cancellations(self, monkeypatch):
        """2 canceled in last 30 days should produce churned_subscriptions=2."""
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_fake")
        get_settings.cache_clear()

        now_ts = int(time.time())
        # Both canceled within last 30 days
        canceled_subs = [
            _make_canceled_subscription("sub_c1", now_ts - 86400),      # 1 day ago
            _make_canceled_subscription("sub_c2", now_ts - 86400 * 10),  # 10 days ago
            # This one is older than 30 days — should NOT count
            _make_canceled_subscription("sub_c3", now_ts - 86400 * 45),  # 45 days ago
        ]

        mock_stripe = MagicMock()
        mock_stripe.Subscription.list.side_effect = [
            # Active subs
            {"data": [], "has_more": False},
            # Trialing subs
            {"data": [], "has_more": False},
            # Canceled subs
            {"data": canceled_subs, "has_more": False},
        ]
        mock_stripe.Charge.list.return_value = {"data": []}

        with patch("app.services.admin_revenue._get_stripe", return_value=mock_stripe):
            result = get_revenue_metrics()

        assert result.churned_subscriptions == 2
        get_settings.cache_clear()


# ---------------------------------------------------------------------------
# Tests: Graceful Degradation
# ---------------------------------------------------------------------------


class TestRevenueGracefulDegradation:
    """Test graceful degradation when Stripe is unreachable."""

    def test_stripe_key_not_configured_returns_unavailable(self, monkeypatch):
        """Missing STRIPE_SECRET_KEY → stripe_data_available=False + warning."""
        monkeypatch.setenv("STRIPE_SECRET_KEY", "")
        get_settings.cache_clear()

        # _get_stripe raises RuntimeError when key is empty, but it also
        # tries `import stripe` first which may not be installed in test env.
        # Patch _get_stripe to raise RuntimeError directly (simulating the real behavior).
        with patch(
            "app.services.admin_revenue._get_stripe",
            side_effect=RuntimeError("STRIPE_SECRET_KEY is not configured"),
        ):
            result = get_revenue_metrics()

        assert result.stripe_data_available is False
        assert result.warning is not None
        assert "not configured" in result.warning.lower() or "STRIPE_SECRET_KEY" in result.warning
        assert result.mrr_usd == 0.0
        assert result.active_subscriptions == 0
        assert result.churned_subscriptions == 0
        get_settings.cache_clear()

    def test_stripe_api_exception_returns_unavailable(self, monkeypatch):
        """Stripe API raising exception → stripe_data_available=False + warning."""
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_fake")
        get_settings.cache_clear()

        mock_stripe = MagicMock()
        mock_stripe.Subscription.list.side_effect = Exception("Connection timeout")

        with patch("app.services.admin_revenue._get_stripe", return_value=mock_stripe):
            result = get_revenue_metrics()

        assert result.stripe_data_available is False
        assert result.warning is not None
        assert "unavailable" in result.warning.lower() or "timeout" in result.warning.lower()
        assert result.mrr_usd == 0.0
        get_settings.cache_clear()


# ---------------------------------------------------------------------------
# Tests: Recent Transactions Mapping
# ---------------------------------------------------------------------------


class TestRecentTransactions:
    """Test recent transaction mapping from Stripe charges."""

    def test_transactions_mapped_correctly(self, monkeypatch):
        """Charges are correctly mapped to StripeTransaction models."""
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_fake")
        get_settings.cache_clear()

        charges = [
            _make_charge("ch_1", 2000, email="alice@example.com", refunded=False),
            _make_charge("ch_2", 500, email="bob@example.com", refunded=True),
        ]

        mock_stripe = MagicMock()
        mock_stripe.Charge.list.return_value = {"data": charges}

        with patch("app.services.admin_revenue._get_stripe", return_value=mock_stripe):
            result = get_recent_transactions(limit=20)

        assert len(result) == 2
        assert result[0].amount_cents == 2000
        assert result[0].user_email == "alice@example.com"
        assert result[0].transaction_type == "payment"
        assert result[0].currency == "usd"

        assert result[1].amount_cents == 500
        assert result[1].user_email == "bob@example.com"
        assert result[1].transaction_type == "refund"
        get_settings.cache_clear()

    def test_transactions_return_empty_on_stripe_failure(self, monkeypatch):
        """Stripe failure → returns empty list (graceful degradation)."""
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_fake")
        get_settings.cache_clear()

        mock_stripe = MagicMock()
        mock_stripe.Charge.list.side_effect = Exception("API error")

        with patch("app.services.admin_revenue._get_stripe", return_value=mock_stripe):
            result = get_recent_transactions(limit=20)

        assert result == []
        get_settings.cache_clear()
