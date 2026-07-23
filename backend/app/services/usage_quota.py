"""Per-user usage tracking and quota enforcement for B2C billing.

Tracks monthly session minutes per user in DynamoDB. Each tier defines limits
that the backend checks before allowing a new session to start.

Table schema (livecap-usage-{env}):
  pk: "USER#{user_id}"
  sk: "MONTH#{YYYY-MM}"
  sessions_used: int
  minutes_used: int (accumulated transcription minutes)
  tier: str (free | pro | business)
  updated_at: int (epoch)

The table is created by Terraform (usage_quota.tf). This module reads/writes
it at session boundaries.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.config import get_settings

logger = logging.getLogger(__name__)


# --- Tier definitions ---

@dataclass(frozen=True)
class TierLimits:
    """Usage cap for a pricing tier."""
    max_sessions_per_month: int
    max_minutes_per_session: int
    max_minutes_per_month: int
    meeting_notes_enabled: bool


TIERS: dict[str, TierLimits] = {
    "free": TierLimits(
        max_sessions_per_month=3,
        max_minutes_per_session=15,
        max_minutes_per_month=45,
        meeting_notes_enabled=False,
    ),
    "pro": TierLimits(
        max_sessions_per_month=999_999,  # unlimited
        max_minutes_per_session=60,
        max_minutes_per_month=600,  # 10 hours
        meeting_notes_enabled=True,
    ),
    "business": TierLimits(
        max_sessions_per_month=999_999,
        max_minutes_per_session=120,
        max_minutes_per_month=999_999,  # unlimited
        meeting_notes_enabled=True,
    ),
    "unlimited": TierLimits(
        # Manually-assigned tier for internal/admin accounts — not sold, no
        # Stripe price. Every cap set to the same "no real limit" sentinel
        # the frontend already treats as infinite (> 999_000).
        max_sessions_per_month=999_999,
        max_minutes_per_session=999_999,
        max_minutes_per_month=999_999,
        meeting_notes_enabled=True,
    ),
}

DEFAULT_TIER = "free"


def _usage_table_name() -> str:
    return os.getenv("USAGE_TABLE_NAME", "livecap-usage-dev")


def _current_month_key() -> str:
    """Return the sort key for the current billing month."""
    import datetime
    return f"MONTH#{datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m')}"


def _dynamo():
    settings = get_settings()
    return boto3.resource("dynamodb", region_name=settings.aws_region)


@dataclass
class UserUsage:
    """Current month's usage for one user."""
    user_id: str
    tier: str
    sessions_used: int
    minutes_used: int


# --- Persistent subscription state (set by Stripe webhooks) ---
#
# Unlike sessions_used/minutes_used (which reset every month), a user's tier
# is a standing fact independent of any month, so it lives in its own item:
#   pk: "USER#{user_id}"
#   sk: "PROFILE"
#   tier, stripe_customer_id, stripe_subscription_id, subscription_status
#
# This item is the single source of truth for `tier` — see
# app.services.stripe_billing, which is the only writer besides tests.

_PROFILE_SORT_KEY = "PROFILE"


@dataclass
class UserSubscription:
    """Persistent (not monthly) billing state for one user."""
    tier: str
    stripe_customer_id: Optional[str]
    stripe_subscription_id: Optional[str]
    subscription_status: Optional[str]


def get_user_subscription(user_id: str) -> UserSubscription:
    """Fetch the persistent tier/subscription record for a user.

    Defaults to the free tier with no Stripe customer if one was never set
    (e.g. the user has never started a checkout).
    """
    table = _dynamo().Table(_usage_table_name())
    try:
        resp = table.get_item(
            Key={"pk": f"USER#{user_id}", "sk": _PROFILE_SORT_KEY},
            ConsistentRead=True,
        )
        item = resp.get("Item")
        if not item:
            return UserSubscription(
                tier=DEFAULT_TIER,
                stripe_customer_id=None,
                stripe_subscription_id=None,
                subscription_status=None,
            )
        return UserSubscription(
            tier=item.get("tier", DEFAULT_TIER),
            stripe_customer_id=item.get("stripe_customer_id"),
            stripe_subscription_id=item.get("stripe_subscription_id"),
            subscription_status=item.get("subscription_status"),
        )
    except (BotoCoreError, ClientError):
        # Fail open to the free tier — don't block users on DynamoDB errors.
        return UserSubscription(
            tier=DEFAULT_TIER,
            stripe_customer_id=None,
            stripe_subscription_id=None,
            subscription_status=None,
        )


def set_user_subscription(
    user_id: str,
    *,
    tier: str,
    stripe_customer_id: Optional[str] = None,
    stripe_subscription_id: Optional[str] = None,
    subscription_status: Optional[str] = None,
) -> None:
    """Upsert the persistent tier/subscription record for a user.

    Called only by Stripe webhook handling (and tests). Fields left as
    ``None`` are left unchanged in the stored record rather than overwritten.
    Raises on a DynamoDB failure (unlike the read helpers here, which fail
    open) so the webhook router can return 5xx and let Stripe retry delivery
    instead of silently losing a billing-state update.
    """
    table = _dynamo().Table(_usage_table_name())
    set_parts = ["tier = :tier", "updated_at = :now"]
    values: dict = {":tier": tier, ":now": int(time.time())}
    if stripe_customer_id is not None:
        set_parts.append("stripe_customer_id = :cust")
        values[":cust"] = stripe_customer_id
    if stripe_subscription_id is not None:
        set_parts.append("stripe_subscription_id = :sub")
        values[":sub"] = stripe_subscription_id
    if subscription_status is not None:
        set_parts.append("subscription_status = :status")
        values[":status"] = subscription_status
    try:
        table.update_item(
            Key={"pk": f"USER#{user_id}", "sk": _PROFILE_SORT_KEY},
            UpdateExpression="SET " + ", ".join(set_parts),
            ExpressionAttributeValues=values,
        )
    except (BotoCoreError, ClientError):
        logger.exception("Failed to persist Stripe subscription state for a user")
        raise


def get_user_usage(user_id: str) -> UserUsage:
    """Fetch the current month's usage record for a user.

    ``tier`` is always sourced from the persistent subscription record
    (``get_user_subscription``), not from this month's item — a user's plan
    doesn't reset just because a new month's usage counters do.
    """
    subscription = get_user_subscription(user_id)
    table = _dynamo().Table(_usage_table_name())
    try:
        resp = table.get_item(
            Key={"pk": f"USER#{user_id}", "sk": _current_month_key()},
            ConsistentRead=True,
        )
        item = resp.get("Item")
        sessions_used = int(item.get("sessions_used", 0)) if item else 0
        minutes_used = int(item.get("minutes_used", 0)) if item else 0
        return UserUsage(
            user_id=user_id,
            tier=subscription.tier,
            sessions_used=sessions_used,
            minutes_used=minutes_used,
        )
    except (BotoCoreError, ClientError):
        # Fail open — don't block users on DynamoDB errors
        return UserUsage(user_id=user_id, tier=subscription.tier, sessions_used=0, minutes_used=0)


def check_quota(user_id: str) -> Optional[str]:
    """Check if user can start a new session. Returns error message or None if OK."""
    usage = get_user_usage(user_id)
    limits = TIERS.get(usage.tier, TIERS[DEFAULT_TIER])

    if usage.sessions_used >= limits.max_sessions_per_month:
        return f"Monthly session limit reached ({limits.max_sessions_per_month} sessions). Upgrade to continue."

    if usage.minutes_used >= limits.max_minutes_per_month:
        return f"Monthly minutes limit reached ({limits.max_minutes_per_month} min). Upgrade for more."

    return None


def get_session_time_limit(user_id: str) -> int:
    """Return max seconds allowed for this user's next session."""
    usage = get_user_usage(user_id)
    limits = TIERS.get(usage.tier, TIERS[DEFAULT_TIER])
    remaining_minutes = limits.max_minutes_per_month - usage.minutes_used
    per_session_limit = limits.max_minutes_per_session
    effective_minutes = min(per_session_limit, remaining_minutes)
    return max(60, effective_minutes * 60)  # at least 1 minute


def increment_session(user_id: str, tier: str = DEFAULT_TIER) -> None:
    """Record that a user started a new session this month."""
    table = _dynamo().Table(_usage_table_name())
    try:
        table.update_item(
            Key={"pk": f"USER#{user_id}", "sk": _current_month_key()},
            UpdateExpression="SET sessions_used = if_not_exists(sessions_used, :zero) + :one, "
                            "tier = :tier, updated_at = :now",
            ExpressionAttributeValues={
                ":zero": 0,
                ":one": 1,
                ":tier": tier,
                ":now": int(time.time()),
            },
        )
    except (BotoCoreError, ClientError):
        pass  # Fail open


def add_minutes(user_id: str, minutes: int) -> None:
    """Add transcription minutes to the user's monthly usage."""
    if minutes <= 0:
        return
    table = _dynamo().Table(_usage_table_name())
    try:
        table.update_item(
            Key={"pk": f"USER#{user_id}", "sk": _current_month_key()},
            UpdateExpression="SET minutes_used = if_not_exists(minutes_used, :zero) + :mins, "
                            "updated_at = :now",
            ExpressionAttributeValues={
                ":zero": 0,
                ":mins": minutes,
                ":now": int(time.time()),
            },
        )
    except (BotoCoreError, ClientError):
        pass  # Fail open


def can_use_meeting_notes(user_id: str) -> bool:
    """Check if the user's tier allows AI meeting notes."""
    usage = get_user_usage(user_id)
    limits = TIERS.get(usage.tier, TIERS[DEFAULT_TIER])
    return limits.meeting_notes_enabled
