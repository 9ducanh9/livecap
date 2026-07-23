"""Usage analytics for the admin dashboard: monthly aggregates, top users,
and tier distribution.

Reads the DynamoDB usage table (same table as usage_quota.py) but focuses on
aggregate views across all users rather than per-user quota enforcement.

DynamoDB TTL expires MONTH# items after ~90 days, so this module enforces a
90-day lookback limit on all date-range queries.
"""

from __future__ import annotations

import datetime
import logging
import os
from dataclasses import dataclass

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.config import get_settings

logger = logging.getLogger(__name__)

# Maximum lookback window in days. DynamoDB TTL expires monthly usage items
# after approximately 90 days, so querying further back yields no data.
_MAX_LOOKBACK_DAYS = 90


# --- Data classes ---


@dataclass
class MonthSummary:
    """Aggregated usage for a single calendar month."""

    month: str  # "YYYY-MM"
    total_sessions: int
    total_minutes: int
    unique_active_users: int


@dataclass
class UsageTotals:
    """Grand totals across the requested date range."""

    total_sessions: int
    total_minutes: int
    unique_active_users: int


@dataclass
class MonthlyUsageData:
    """Full monthly usage response."""

    months: list[MonthSummary]
    totals: UsageTotals


@dataclass
class TopUserRow:
    """A single entry in the top-users ranking."""

    email: str
    tier: str
    sessions_used: int
    minutes_used: int


@dataclass
class TierStats:
    """Count and percentage for a single tier."""

    count: int
    percentage: float


@dataclass
class TierDistribution:
    """User distribution across tiers."""

    free: TierStats
    pro: TierStats
    business: TierStats


# --- Helpers ---


def _usage_table_name() -> str:
    return os.getenv("USAGE_TABLE_NAME", "livecap-usage-dev")


def _now_utc() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _current_month_str() -> str:
    """Return the current month as 'YYYY-MM'."""
    return _now_utc().strftime("%Y-%m")


def _earliest_allowed_month() -> str:
    """Return the earliest month within the 90-day lookback window."""
    earliest = _now_utc() - datetime.timedelta(days=_MAX_LOOKBACK_DAYS)
    return earliest.strftime("%Y-%m")


def _clamp_month(month: str, earliest: str, latest: str) -> str:
    """Clamp a month string to [earliest, latest]."""
    if month < earliest:
        return earliest
    if month > latest:
        return latest
    return month


def _scan_all_items(table) -> list[dict]:
    """Paginated scan of the entire table. Returns all items."""
    items: list[dict] = []
    scan_kwargs: dict = {}
    while True:
        response = table.scan(**scan_kwargs)
        items.extend(response.get("Items", []))
        last_key = response.get("LastEvaluatedKey")
        if not last_key:
            break
        scan_kwargs = {"ExclusiveStartKey": last_key}
    return items


def _get_table():
    """Return the DynamoDB Table resource for the usage table."""
    settings = get_settings()
    resource = boto3.resource("dynamodb", region_name=settings.aws_region)
    return resource.Table(_usage_table_name())


# --- Public functions ---


def get_monthly_usage(
    start_month: str | None = None,
    end_month: str | None = None,
) -> MonthlyUsageData:
    """Aggregate sessions, minutes, and unique users per month.

    Parameters
    ----------
    start_month : str | None
        Inclusive start month in "YYYY-MM" format. Defaults to current month.
    end_month : str | None
        Inclusive end month in "YYYY-MM" format. Defaults to current month.

    Returns
    -------
    MonthlyUsageData
        Per-month summaries and grand totals for the requested range.
        Returns empty data (zero totals) if DynamoDB is unreachable.
    """
    current = _current_month_str()
    earliest = _earliest_allowed_month()

    # Default to current month if not specified
    if not start_month:
        start_month = current
    if not end_month:
        end_month = current

    # Clamp to the allowed window
    start_month = _clamp_month(start_month, earliest, current)
    end_month = _clamp_month(end_month, earliest, current)

    # Ensure start <= end
    if start_month > end_month:
        start_month, end_month = end_month, start_month

    try:
        table = _get_table()
        items = _scan_all_items(table)
    except (BotoCoreError, ClientError):
        logger.warning(
            "DynamoDB scan failed in get_monthly_usage; returning empty data"
        )
        return MonthlyUsageData(
            months=[],
            totals=UsageTotals(
                total_sessions=0, total_minutes=0, unique_active_users=0
            ),
        )

    # Aggregate per month: {month_str: {"sessions": int, "minutes": int, "users": set}}
    by_month: dict[str, dict] = {}

    for item in items:
        pk = str(item.get("pk", ""))
        sk = str(item.get("sk", ""))

        if not pk.startswith("USER#"):
            continue
        if not sk.startswith("MONTH#"):
            continue

        month_str = sk[len("MONTH#"):]  # "YYYY-MM"

        # Filter to requested range
        if month_str < start_month or month_str > end_month:
            continue

        user_id = pk[len("USER#"):]
        sessions = int(item.get("sessions_used", 0))
        minutes = int(item.get("minutes_used", 0))

        if month_str not in by_month:
            by_month[month_str] = {"sessions": 0, "minutes": 0, "users": set()}

        by_month[month_str]["sessions"] += sessions
        by_month[month_str]["minutes"] += minutes
        if sessions > 0:
            by_month[month_str]["users"].add(user_id)

    # Build sorted month summaries
    month_summaries: list[MonthSummary] = []
    for month_str in sorted(by_month.keys()):
        data = by_month[month_str]
        month_summaries.append(
            MonthSummary(
                month=month_str,
                total_sessions=data["sessions"],
                total_minutes=data["minutes"],
                unique_active_users=len(data["users"]),
            )
        )

    # Grand totals
    grand_sessions = sum(m.total_sessions for m in month_summaries)
    grand_minutes = sum(m.total_minutes for m in month_summaries)
    all_active_users: set[str] = set()
    for data in by_month.values():
        all_active_users.update(data["users"])

    return MonthlyUsageData(
        months=month_summaries,
        totals=UsageTotals(
            total_sessions=grand_sessions,
            total_minutes=grand_minutes,
            unique_active_users=len(all_active_users),
        ),
    )


def get_top_users(month: str | None = None, limit: int = 10) -> list[TopUserRow]:
    """Return the top N users by minutes_used for a given month.

    Parameters
    ----------
    month : str | None
        Month in "YYYY-MM" format. Defaults to current month.
    limit : int
        Maximum number of users to return. Defaults to 10.

    Returns
    -------
    list[TopUserRow]
        Top users sorted descending by minutes_used.
        Returns empty list if DynamoDB is unreachable.
    """
    current = _current_month_str()
    earliest = _earliest_allowed_month()

    if not month:
        month = current

    # Enforce 90-day lookback
    month = _clamp_month(month, earliest, current)

    try:
        table = _get_table()
        items = _scan_all_items(table)
    except (BotoCoreError, ClientError):
        logger.warning(
            "DynamoDB scan failed in get_top_users; returning empty list"
        )
        return []

    target_sk = f"MONTH#{month}"

    # Collect per-user usage for the target month
    # {user_id: {"sessions_used": int, "minutes_used": int}}
    user_usage: dict[str, dict] = {}
    # {user_id: {"email": str, "tier": str}}
    user_profiles: dict[str, dict] = {}

    for item in items:
        pk = str(item.get("pk", ""))
        sk = str(item.get("sk", ""))

        if not pk.startswith("USER#"):
            continue

        user_id = pk[len("USER#"):]

        if sk == "PROFILE":
            user_profiles[user_id] = {
                "email": str(item.get("email", "")),
                "tier": str(item.get("tier", "free")),
            }
        elif sk == target_sk:
            user_usage[user_id] = {
                "sessions_used": int(item.get("sessions_used", 0)),
                "minutes_used": int(item.get("minutes_used", 0)),
            }

    # Build result rows, joining usage with profile data
    rows: list[TopUserRow] = []
    for user_id, usage in user_usage.items():
        profile = user_profiles.get(user_id, {})
        rows.append(
            TopUserRow(
                email=profile.get("email", ""),
                tier=profile.get("tier", "free"),
                sessions_used=usage["sessions_used"],
                minutes_used=usage["minutes_used"],
            )
        )

    # Sort descending by minutes_used, then descending by sessions_used as tiebreaker
    rows.sort(key=lambda r: (-r.minutes_used, -r.sessions_used))

    return rows[:limit]


def get_tier_distribution() -> TierDistribution:
    """Count users per tier and calculate percentages.

    Returns
    -------
    TierDistribution
        Count and percentage for each tier (free, pro, business).
        Returns zero counts/percentages if DynamoDB is unreachable.
    """
    try:
        table = _get_table()
        items = _scan_all_items(table)
    except (BotoCoreError, ClientError):
        logger.warning(
            "DynamoDB scan failed in get_tier_distribution; returning zeros"
        )
        return TierDistribution(
            free=TierStats(count=0, percentage=0.0),
            pro=TierStats(count=0, percentage=0.0),
            business=TierStats(count=0, percentage=0.0),
        )

    # Count PROFILE items per tier
    tier_counts: dict[str, int] = {"free": 0, "pro": 0, "business": 0}

    for item in items:
        pk = str(item.get("pk", ""))
        sk = str(item.get("sk", ""))

        if not pk.startswith("USER#"):
            continue
        if sk != "PROFILE":
            continue

        tier = str(item.get("tier", "free")).lower()
        if tier not in tier_counts:
            tier = "free"  # Unknown tiers default to free
        tier_counts[tier] += 1

    total = sum(tier_counts.values())

    def _pct(count: int) -> float:
        if total == 0:
            return 0.0
        return round((count / total) * 100, 2)

    return TierDistribution(
        free=TierStats(count=tier_counts["free"], percentage=_pct(tier_counts["free"])),
        pro=TierStats(count=tier_counts["pro"], percentage=_pct(tier_counts["pro"])),
        business=TierStats(
            count=tier_counts["business"], percentage=_pct(tier_counts["business"])
        ),
    )
