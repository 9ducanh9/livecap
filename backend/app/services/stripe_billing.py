"""Stripe subscription billing for the Pro/Business tiers.

Architecture (see COLLAB_LOG.md for the full write-up): Stripe Checkout
(hosted) creates the subscription; the Stripe Customer Portal (hosted) lets a
signed-in user upgrade, downgrade, or cancel; webhooks keep the DynamoDB
per-user profile record (``usage_quota.get_user_subscription`` /
``set_user_subscription``) in sync so ``GET /api/usage`` and quota checks
always reflect the real subscription state.

Off by default (``ENABLE_STRIPE_BILLING``). A Stripe Price's
``metadata.livecap_tier`` (set at Price-creation time to "pro" or "business")
is the source of truth mapping a Stripe object back to a LiveCap tier, so
this module never hardcodes a Price ID -> tier table — only a tier -> Price ID
one, read from settings.
"""

from __future__ import annotations

import logging
from typing import Optional

from app.config import get_settings
from app.services import usage_quota

logger = logging.getLogger(__name__)


class StripeBillingError(Exception):
    """Raised for any Stripe billing failure the caller should surface as an HTTP error."""


def _stripe():
    """Import and configure the ``stripe`` SDK lazily.

    Imported lazily so the dependency is only required when billing is
    actually enabled/exercised, and so ``STRIPE_SECRET_KEY`` is always read
    fresh from current settings rather than baked in at module import time.
    """
    import stripe  # local import: only needed when billing is enabled

    settings = get_settings()
    if not settings.stripe_secret_key:
        raise StripeBillingError("STRIPE_SECRET_KEY is not configured")
    stripe.api_key = settings.stripe_secret_key
    return stripe


def _price_id_for_tier(tier: str) -> str:
    settings = get_settings()
    price_id = {
        "pro": settings.stripe_price_id_pro,
        "business": settings.stripe_price_id_business,
    }.get(tier, "")
    if not price_id:
        raise StripeBillingError(f"No Stripe price configured for tier '{tier}'")
    return price_id


def ensure_customer(user_id: str, email: Optional[str]) -> str:
    """Return the user's Stripe Customer ID, creating one if this is their first checkout."""
    stripe = _stripe()
    subscription = usage_quota.get_user_subscription(user_id)
    if subscription.stripe_customer_id:
        return subscription.stripe_customer_id

    customer = stripe.Customer.create(
        email=email or None,
        metadata={"cognito_user_id": user_id},
    )
    usage_quota.set_user_subscription(
        user_id, tier=subscription.tier, stripe_customer_id=customer["id"]
    )
    return customer["id"]


def create_checkout_session(user_id: str, email: Optional[str], tier: str) -> str:
    """Create a Stripe Checkout session for a Pro/Business subscription.

    Returns the hosted Checkout URL to redirect the browser to.
    """
    if tier not in ("pro", "business"):
        raise StripeBillingError("tier must be 'pro' or 'business'")
    stripe = _stripe()
    settings = get_settings()
    customer_id = ensure_customer(user_id, email)
    base_url = settings.frontend_base_url.rstrip("/")
    session = stripe.checkout.Session.create(
        mode="subscription",
        customer=customer_id,
        client_reference_id=user_id,
        line_items=[{"price": _price_id_for_tier(tier), "quantity": 1}],
        success_url=f"{base_url}/app?billing=success",
        cancel_url=f"{base_url}/app?billing=cancelled",
        metadata={"cognito_user_id": user_id, "livecap_tier": tier},
        allow_promotion_codes=True,
    )
    return session["url"]


def create_portal_session(user_id: str) -> str:
    """Create a Stripe Customer Portal session so the user can manage their subscription."""
    stripe = _stripe()
    settings = get_settings()
    subscription = usage_quota.get_user_subscription(user_id)
    if not subscription.stripe_customer_id:
        raise StripeBillingError("No Stripe customer on file yet — start a subscription first")
    base_url = settings.frontend_base_url.rstrip("/")
    session = stripe.billing_portal.Session.create(
        customer=subscription.stripe_customer_id,
        return_url=f"{base_url}/app",
    )
    return session["url"]


def _user_id_from_customer(stripe, customer_id: str) -> Optional[str]:
    """Look up the Cognito user_id stashed in a Stripe Customer's metadata.

    Subscription-lifecycle webhooks only carry the Stripe customer/subscription
    IDs, not our own user_id, so we resolve it via the metadata set in
    ``ensure_customer``/``create_checkout_session``.
    """
    try:
        customer = stripe.Customer.retrieve(customer_id)
    except Exception:  # noqa: BLE001 - any Stripe API error; log and give up gracefully
        logger.warning("Could not retrieve Stripe customer to resolve owning user", exc_info=True)
        return None
    return (customer.get("metadata") or {}).get("cognito_user_id")


def _tier_from_subscription_items(data: dict) -> str:
    items = (data.get("items") or {}).get("data") or []
    if not items:
        return usage_quota.DEFAULT_TIER
    price = items[0].get("price") or {}
    return (price.get("metadata") or {}).get("livecap_tier") or usage_quota.DEFAULT_TIER


def handle_webhook_event(payload: bytes, signature_header: str) -> None:
    """Verify and process one Stripe webhook event.

    Raises ``StripeBillingError`` on a bad/missing signature (the router
    should return 400) or any other failure (the router should return 5xx so
    Stripe retries delivery rather than silently losing the update).
    """
    stripe = _stripe()
    settings = get_settings()
    if not settings.stripe_webhook_secret:
        raise StripeBillingError("STRIPE_WEBHOOK_SECRET is not configured")

    try:
        event = stripe.Webhook.construct_event(
            payload, signature_header, settings.stripe_webhook_secret
        )
    except Exception as exc:  # noqa: BLE001 - covers ValueError (bad payload) and
        # stripe's SignatureVerificationError, whose import path has moved
        # across SDK major versions; both cases mean "reject this request".
        raise StripeBillingError(f"Invalid Stripe webhook payload or signature: {exc}") from exc

    event_type = event["type"]
    data = event["data"]["object"]
    logger.info("Processing Stripe webhook event: %s", event_type)

    if event_type == "checkout.session.completed":
        user_id = data.get("client_reference_id") or (data.get("metadata") or {}).get("cognito_user_id")
        if not user_id:
            logger.warning("checkout.session.completed had no client_reference_id/metadata user id")
            return
        tier = (data.get("metadata") or {}).get("livecap_tier", usage_quota.DEFAULT_TIER)
        usage_quota.set_user_subscription(
            user_id,
            tier=tier,
            stripe_customer_id=data.get("customer"),
            stripe_subscription_id=data.get("subscription"),
            subscription_status="active",
        )

    elif event_type in ("customer.subscription.updated", "customer.subscription.created"):
        customer_id = data.get("customer")
        user_id = _user_id_from_customer(stripe, customer_id) if customer_id else None
        if not user_id:
            logger.warning("%s had no resolvable owning user for customer %s", event_type, customer_id)
            return
        status = data.get("status")
        tier = _tier_from_subscription_items(data) if status in ("active", "trialing") else usage_quota.DEFAULT_TIER
        usage_quota.set_user_subscription(
            user_id,
            tier=tier,
            stripe_customer_id=customer_id,
            stripe_subscription_id=data.get("id"),
            subscription_status=status,
        )

    elif event_type == "customer.subscription.deleted":
        customer_id = data.get("customer")
        user_id = _user_id_from_customer(stripe, customer_id) if customer_id else None
        if not user_id:
            logger.warning("subscription.deleted had no resolvable owning user for customer %s", customer_id)
            return
        usage_quota.set_user_subscription(
            user_id,
            tier=usage_quota.DEFAULT_TIER,
            stripe_subscription_id=data.get("id"),
            subscription_status="canceled",
        )

    elif event_type == "invoice.payment_failed":
        customer_id = data.get("customer")
        user_id = _user_id_from_customer(stripe, customer_id) if customer_id else None
        if not user_id:
            return
        # Don't change tier here — Stripe's Smart Retries keep attempting the
        # charge; only record the status so the UI/support can flag it.
        current = usage_quota.get_user_subscription(user_id)
        usage_quota.set_user_subscription(
            user_id, tier=current.tier, subscription_status="past_due"
        )

    else:
        logger.info("Unhandled Stripe webhook event type: %s", event_type)
