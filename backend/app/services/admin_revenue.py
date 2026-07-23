"""Admin revenue service — Stripe-based revenue metrics and transaction history.

Queries Stripe's Subscriptions and Charges APIs to compute MRR, active/churned
subscription counts, and recent transaction activity. All Stripe calls are
wrapped in try/except for graceful degradation: if Stripe is unreachable the
response includes ``stripe_data_available=False`` with a warning message.

Requirements: 12.1, 12.2, 12.3, 12.5
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

from pydantic import BaseModel

from app.config import get_settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class StripeTransaction(BaseModel):
    """A single Stripe transaction (charge or refund)."""

    date: str  # ISO 8601
    user_email: str | None
    amount_cents: int
    currency: str
    transaction_type: str  # "payment" | "refund" | "subscription_change"


class RevenueMetrics(BaseModel):
    """Aggregated revenue metrics from Stripe."""

    mrr_usd: float
    active_subscriptions: int
    churned_subscriptions: int
    recent_transactions: list[StripeTransaction]
    stripe_data_available: bool
    warning: str | None = None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_stripe():
    """Import and configure the Stripe SDK lazily.

    Mirrors the pattern in stripe_billing.py — only imports stripe when
    actually needed and reads the secret key from current settings.
    """
    import stripe

    settings = get_settings()
    if not settings.stripe_secret_key:
        raise RuntimeError("STRIPE_SECRET_KEY is not configured")
    stripe.api_key = settings.stripe_secret_key
    return stripe


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_recent_transactions(limit: int = 20) -> list[StripeTransaction]:
    """Fetch recent Stripe charges and map them to StripeTransaction models.

    On any Stripe error, returns an empty list (caller handles degradation).
    """
    try:
        stripe = _get_stripe()
        charges = stripe.Charge.list(limit=limit, expand=["data.customer"])

        transactions: list[StripeTransaction] = []
        for charge in charges.get("data", []):
            # Determine transaction type
            if charge.get("refunded"):
                txn_type = "refund"
            else:
                txn_type = "payment"

            # Extract user email from expanded customer or charge receipt_email
            user_email: str | None = None
            customer = charge.get("customer")
            if isinstance(customer, dict):
                user_email = customer.get("email")
            if not user_email:
                user_email = charge.get("receipt_email")

            # Convert timestamp to ISO 8601
            created_ts = charge.get("created", 0)
            date_str = datetime.fromtimestamp(created_ts, tz=timezone.utc).isoformat()

            transactions.append(
                StripeTransaction(
                    date=date_str,
                    user_email=user_email,
                    amount_cents=charge.get("amount", 0),
                    currency=charge.get("currency", "usd"),
                    transaction_type=txn_type,
                )
            )

        return transactions

    except Exception:
        logger.warning("Failed to fetch recent Stripe transactions", exc_info=True)
        return []


def get_revenue_metrics() -> RevenueMetrics:
    """Compute revenue metrics from Stripe Subscriptions API.

    - MRR: sum of unit_amount for all active subscription items (converted to dollars)
    - Active subscriptions: count of subscriptions with status 'active' or 'trialing'
    - Churned subscriptions: count canceled in the last 30 days
    - Recent transactions: last 20 charges via get_recent_transactions()

    On Stripe API failure, returns a response with stripe_data_available=False
    and a warning message describing the issue.
    """
    try:
        stripe = _get_stripe()
    except RuntimeError as exc:
        return RevenueMetrics(
            mrr_usd=0.0,
            active_subscriptions=0,
            churned_subscriptions=0,
            recent_transactions=[],
            stripe_data_available=False,
            warning=str(exc),
        )

    try:
        # --- Active subscriptions & MRR ---
        mrr_cents = 0
        active_count = 0
        has_more = True
        starting_after: str | None = None

        while has_more:
            params: dict = {"status": "active", "limit": 100}
            if starting_after:
                params["starting_after"] = starting_after

            response = stripe.Subscription.list(**params)
            subscriptions = response.get("data", [])

            for sub in subscriptions:
                active_count += 1
                # Sum recurring amounts from subscription items
                items = sub.get("items", {}).get("data", [])
                for item in items:
                    price = item.get("price", {})
                    unit_amount = price.get("unit_amount", 0) or 0
                    # Handle different billing intervals — normalize to monthly
                    interval = price.get("recurring", {}).get("interval", "month") if price.get("recurring") else "month"
                    interval_count = price.get("recurring", {}).get("interval_count", 1) if price.get("recurring") else 1

                    if interval == "year":
                        # Convert annual to monthly
                        mrr_cents += unit_amount // (12 * interval_count)
                    elif interval == "month":
                        mrr_cents += unit_amount // interval_count if interval_count > 1 else unit_amount
                    elif interval == "week":
                        # Approximate: 4.33 weeks per month
                        mrr_cents += int(unit_amount * 4.33 / interval_count)
                    elif interval == "day":
                        # Approximate: 30.44 days per month
                        mrr_cents += int(unit_amount * 30.44 / interval_count)
                    else:
                        mrr_cents += unit_amount

            has_more = response.get("has_more", False)
            if subscriptions:
                starting_after = subscriptions[-1].get("id")

        # Also count trialing subscriptions as active
        has_more = True
        starting_after = None

        while has_more:
            params = {"status": "trialing", "limit": 100}
            if starting_after:
                params["starting_after"] = starting_after

            response = stripe.Subscription.list(**params)
            subscriptions = response.get("data", [])

            for sub in subscriptions:
                active_count += 1
                items = sub.get("items", {}).get("data", [])
                for item in items:
                    price = item.get("price", {})
                    unit_amount = price.get("unit_amount", 0) or 0
                    interval = price.get("recurring", {}).get("interval", "month") if price.get("recurring") else "month"
                    interval_count = price.get("recurring", {}).get("interval_count", 1) if price.get("recurring") else 1

                    if interval == "year":
                        mrr_cents += unit_amount // (12 * interval_count)
                    elif interval == "month":
                        mrr_cents += unit_amount // interval_count if interval_count > 1 else unit_amount
                    elif interval == "week":
                        mrr_cents += int(unit_amount * 4.33 / interval_count)
                    elif interval == "day":
                        mrr_cents += int(unit_amount * 30.44 / interval_count)
                    else:
                        mrr_cents += unit_amount

            has_more = response.get("has_more", False)
            if subscriptions:
                starting_after = subscriptions[-1].get("id")

        # --- Churned subscriptions (canceled in last 30 days) ---
        churned_count = 0
        thirty_days_ago = int((datetime.now(timezone.utc) - timedelta(days=30)).timestamp())
        has_more = True
        starting_after = None

        while has_more:
            params = {"status": "canceled", "limit": 100}
            if starting_after:
                params["starting_after"] = starting_after

            response = stripe.Subscription.list(**params)
            subscriptions = response.get("data", [])

            for sub in subscriptions:
                canceled_at = sub.get("canceled_at")
                if canceled_at and canceled_at >= thirty_days_ago:
                    churned_count += 1

            has_more = response.get("has_more", False)
            if subscriptions:
                starting_after = subscriptions[-1].get("id")
            else:
                has_more = False

        # --- Recent transactions ---
        recent_transactions = get_recent_transactions(limit=20)

        # Convert MRR from cents to dollars
        mrr_usd = round(mrr_cents / 100.0, 2)

        return RevenueMetrics(
            mrr_usd=mrr_usd,
            active_subscriptions=active_count,
            churned_subscriptions=churned_count,
            recent_transactions=recent_transactions,
            stripe_data_available=True,
            warning=None,
        )

    except Exception as exc:
        logger.warning("Stripe API error while fetching revenue metrics", exc_info=True)
        return RevenueMetrics(
            mrr_usd=0.0,
            active_subscriptions=0,
            churned_subscriptions=0,
            recent_transactions=[],
            stripe_data_available=False,
            warning=f"Stripe API unavailable: {exc}",
        )
