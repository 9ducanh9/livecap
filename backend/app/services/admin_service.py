"""Aggregated data for the admin dashboard: all users, revenue estimate, and
coarse system health.

Backed by three AWS calls: Cognito `ListUsers` (for the user list + emails),
a `Scan` of the usage_quota DynamoDB table (for tier/sessions/minutes/
subscription per user), and ECS `DescribeServices` (a coarse "is the backend
actually running" signal). Every call fails soft -- an empty list, zero
counts, or an unreachable-system marker -- rather than raising, so one
degraded AWS dependency doesn't take down the whole dashboard for an admin
who's trying to diagnose exactly that kind of problem.
"""

from __future__ import annotations

import datetime
import logging
import os
from dataclasses import dataclass

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.config import get_settings
from app.services.usage_quota import DEFAULT_TIER, TIERS

logger = logging.getLogger(__name__)

# Flat, display-only price list for the MRR estimate. This is NOT the source
# of truth for what a Stripe Price actually charges -- that's each Price's
# `metadata.livecap_tier` (see stripe_billing.py). It only produces a ballpark
# "if these subscriptions are active, revenue is about $X/mo" dashboard number.
_TIER_MONTHLY_USD = {"pro": 10, "business": 30}


@dataclass
class AdminUserRow:
    user_id: str
    email: str
    tier: str
    sessions_used: int
    minutes_used: int
    subscription_status: str | None


@dataclass
class AdminOverview:
    users: list[AdminUserRow]
    stats: dict
    system: dict


def _usage_table_name() -> str:
    return os.getenv("USAGE_TABLE_NAME", "livecap-usage-dev")


def _current_month_key() -> str:
    now = datetime.datetime.now(datetime.timezone.utc)
    return f"MONTH#{now.strftime('%Y-%m')}"


def _list_cognito_users(region: str, user_pool_id: str) -> dict[str, str]:
    """Return ``{sub: email}`` for every user in the pool.

    Empty (not an exception) if the pool isn't configured or any AWS call
    fails -- the dashboard should degrade to "no users shown", not 500.
    """

    if not user_pool_id:
        return {}
    client = boto3.client("cognito-idp", region_name=region)
    emails: dict[str, str] = {}
    pagination_token: str | None = None
    try:
        while True:
            kwargs: dict = {"UserPoolId": user_pool_id, "Limit": 60}
            if pagination_token:
                kwargs["PaginationToken"] = pagination_token
            response = client.list_users(**kwargs)
            for user in response.get("Users", []):
                attributes = {a["Name"]: a["Value"] for a in user.get("Attributes", [])}
                sub = attributes.get("sub")
                if sub:
                    emails[sub] = attributes.get("email", user.get("Username", ""))
            pagination_token = response.get("PaginationToken")
            if not pagination_token:
                break
    except (ClientError, BotoCoreError):
        logger.warning("cognito-idp ListUsers failed; admin dashboard will show 0 users")
        return {}
    return emails


def _scan_usage_table(region: str) -> dict[str, dict]:
    """Return ``{user_id: {"profile": item|None, "month": item|None}}``."""

    resource = boto3.resource("dynamodb", region_name=region)
    table = resource.Table(_usage_table_name())
    by_user: dict[str, dict] = {}
    month_key = _current_month_key()
    try:
        scan_kwargs: dict = {}
        while True:
            response = table.scan(**scan_kwargs)
            for item in response.get("Items", []):
                pk = str(item.get("pk", ""))
                if not pk.startswith("USER#"):
                    continue
                user_id = pk[len("USER#"):]
                bucket = by_user.setdefault(user_id, {"profile": None, "month": None})
                sk = str(item.get("sk", ""))
                if sk == "PROFILE":
                    bucket["profile"] = item
                elif sk == month_key:
                    bucket["month"] = item
            last_key = response.get("LastEvaluatedKey")
            if not last_key:
                break
            scan_kwargs = {"ExclusiveStartKey": last_key}
    except (ClientError, BotoCoreError):
        logger.warning("usage table scan failed; admin dashboard usage data will be incomplete")
        return {}
    return by_user


def _system_health(region: str, cluster: str, service: str) -> dict:
    if not cluster or not service:
        return {
            "backend_reachable": False,
            "desired_count": None,
            "running_count": None,
            "pending_count": None,
        }
    try:
        client = boto3.client("ecs", region_name=region)
        response = client.describe_services(cluster=cluster, services=[service])
        services = response.get("services", [])
        if not services:
            return {
                "backend_reachable": False,
                "desired_count": 0,
                "running_count": 0,
                "pending_count": 0,
            }
        service_state = services[0]
        return {
            "backend_reachable": True,
            "desired_count": service_state.get("desiredCount", 0),
            "running_count": service_state.get("runningCount", 0),
            "pending_count": service_state.get("pendingCount", 0),
        }
    except (ClientError, BotoCoreError):
        logger.warning("ecs DescribeServices failed; admin dashboard system panel will be empty")
        return {
            "backend_reachable": False,
            "desired_count": None,
            "running_count": None,
            "pending_count": None,
        }


def get_admin_overview() -> AdminOverview:
    """Build the full admin dashboard payload from live AWS state."""

    settings = get_settings()
    emails = _list_cognito_users(settings.aws_region, settings.cognito_user_pool_id)
    usage_by_user = _scan_usage_table(settings.aws_region)

    # Union of Cognito users and anyone with a usage record -- covers both a
    # user who registered but never started a session, and (defensively) a
    # usage row whose Cognito account was since deleted.
    all_user_ids = set(emails) | set(usage_by_user)

    rows: list[AdminUserRow] = []
    by_tier: dict[str, int] = {}
    total_sessions = 0
    total_minutes = 0

    for user_id in all_user_ids:
        bucket = usage_by_user.get(user_id, {"profile": None, "month": None})
        profile = bucket.get("profile") or {}
        month = bucket.get("month") or {}
        tier = str(profile.get("tier", DEFAULT_TIER))
        if tier not in TIERS:
            tier = DEFAULT_TIER
        sessions_used = int(month.get("sessions_used", 0))
        minutes_used = int(month.get("minutes_used", 0))

        rows.append(
            AdminUserRow(
                user_id=user_id,
                email=emails.get(user_id, ""),
                tier=tier,
                sessions_used=sessions_used,
                minutes_used=minutes_used,
                subscription_status=profile.get("subscription_status"),
            )
        )
        by_tier[tier] = by_tier.get(tier, 0) + 1
        total_sessions += sessions_used
        total_minutes += minutes_used

    rows.sort(key=lambda row: (row.email or row.user_id).lower())

    estimated_mrr_usd = sum(
        by_tier.get(tier, 0) * price for tier, price in _TIER_MONTHLY_USD.items()
    )

    stats = {
        "total_users": len(rows),
        "by_tier": {tier: by_tier.get(tier, 0) for tier in TIERS},
        "total_sessions_this_month": total_sessions,
        "total_minutes_this_month": total_minutes,
        "estimated_mrr_usd": estimated_mrr_usd,
    }

    system = _system_health(
        settings.aws_region, settings.ecs_cluster_name, settings.ecs_service_name
    )

    return AdminOverview(users=rows, stats=stats, system=system)
