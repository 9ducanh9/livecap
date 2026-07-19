"""Stripe subscription billing endpoints.

- ``POST /api/billing/checkout-session`` — signed-in user starts a Pro/Business
  subscription; returns a hosted Stripe Checkout URL to redirect to.
- ``POST /api/billing/portal-session`` — signed-in user manages an existing
  subscription (upgrade/downgrade/cancel/payment method) via the hosted
  Stripe Customer Portal.
- ``POST /api/billing/webhook`` — Stripe calls this directly (no Cognito
  auth; verified instead by the Stripe-Signature header) to notify us of
  subscription lifecycle changes.

All three are no-ops (404) unless ``ENABLE_STRIPE_BILLING`` is set, matching
the flag-gated pattern used by every other optional feature in this backend.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from app.config import get_settings
from app.services import stripe_billing
from app.services.auth import AuthenticatedUser, require_authenticated_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/billing", tags=["billing"])


def _require_enabled() -> None:
    if not get_settings().enable_stripe_billing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Billing is not enabled",
        )


class CheckoutSessionRequest(BaseModel):
    tier: str  # "pro" | "business"


@router.post("/checkout-session")
async def create_checkout_session(
    body: CheckoutSessionRequest,
    user: AuthenticatedUser = Depends(require_authenticated_user),
):
    """Create a Stripe Checkout session for the caller's chosen tier."""
    _require_enabled()
    try:
        url = stripe_billing.create_checkout_session(user.user_id, user.email or None, body.tier)
    except stripe_billing.StripeBillingError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"url": url}


@router.post("/portal-session")
async def create_portal_session(
    user: AuthenticatedUser = Depends(require_authenticated_user),
):
    """Create a Stripe Customer Portal session for the caller to manage their subscription."""
    _require_enabled()
    try:
        url = stripe_billing.create_portal_session(user.user_id)
    except stripe_billing.StripeBillingError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"url": url}


@router.post("/webhook")
async def stripe_webhook(request: Request):
    """Receive and process a Stripe webhook event.

    Reads the raw request body (required for signature verification — a
    parsed-then-re-serialized body would not match the signature Stripe
    computed over the original bytes).
    """
    _require_enabled()
    payload = await request.body()
    signature_header = request.headers.get("stripe-signature", "")
    try:
        stripe_billing.handle_webhook_event(payload, signature_header)
    except stripe_billing.StripeBillingError as exc:
        logger.warning("Rejected Stripe webhook: %s", exc)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - surfaced as 500 so Stripe retries delivery
        logger.exception("Unhandled error processing Stripe webhook")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Webhook processing failed"
        ) from exc
    return {"received": True}
