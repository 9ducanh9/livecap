"""Admin user management service.

Provides functions for listing, viewing, and managing users through the admin
panel. Queries Cognito for identity data and DynamoDB for usage/subscription
state.
"""

from __future__ import annotations

import datetime
import json
import logging
import math
import os
import time

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import HTTPException
from pydantic import BaseModel

from app.config import get_settings
from app.services.usage_quota import DEFAULT_TIER, TIERS

# Admin audit service — may not exist yet (created in parallel task)
try:
    from app.services import admin_audit
except ImportError:
    admin_audit = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_TIERS = {"free", "pro", "business"}

FEDERATED_PREFIXES = ("Google_", "Facebook_", "LoginWithAmazon_", "SignInWithApple_")


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class UserRecord(BaseModel):
    cognito_username: str
    email: str
    tier: str  # "free" | "pro" | "business"
    status: str  # "enabled" | "disabled"
    identity_provider: str  # "native" | "Google" | etc.
    created_date: str  # ISO 8601
    last_active: str | None = None  # ISO 8601 or None
    sessions_used: int = 0
    minutes_used: int = 0
    subscription_status: str | None = None


class UserStats(BaseModel):
    total_users: int
    free_count: int
    pro_count: int
    business_count: int


class PaginatedUserList(BaseModel):
    users: list[UserRecord]
    page: int
    page_size: int
    total_pages: int
    total_users: int
    stats: UserStats


class MonthlyUsage(BaseModel):
    month: str  # "YYYY-MM"
    sessions_used: int
    minutes_used: int


class TranscriptSessionSummary(BaseModel):
    session_id: str
    created_at: str  # ISO 8601
    segment_count: int
    duration_seconds: int | None = None


class AuditLogEntry(BaseModel):
    entry_id: str  # UUID
    admin_user_id: str
    target_user_id: str
    action_type: str  # "disable" | "enable" | "reset_password" | "change_tier"
    previous_value: str | None = None
    new_value: str | None = None
    timestamp: str  # ISO 8601 UTC


class UserDetail(BaseModel):
    profile: UserRecord
    usage_history: list[MonthlyUsage]  # last 3 months
    transcript_sessions: list[TranscriptSessionSummary]
    audit_log: list[AuditLogEntry]  # empty for now, Phase 2
    has_stripe_subscription: bool


class UserActionResult(BaseModel):
    success: bool
    message: str
    warning: str | None = None


class TierChangeResult(BaseModel):
    success: bool
    message: str
    updated_user: UserRecord | None = None
    warning: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _usage_table_name() -> str:
    return os.getenv("USAGE_TABLE_NAME", "livecap-usage-dev")


def _transcript_history_table_name() -> str:
    return os.getenv("TRANSCRIPT_HISTORY_TABLE_NAME", "livecap-transcript-history")


def _current_month_key() -> str:
    now = datetime.datetime.now(datetime.timezone.utc)
    return f"MONTH#{now.strftime('%Y-%m')}"


def _detect_identity_provider(username: str, attributes: dict | None = None) -> str:
    """Infer identity provider from the Cognito username format or attributes.

    Federated users have usernames like "Google_<sub>" or "Facebook_<sub>".
    Native users have a UUID or email-style username.
    Also checks the 'identities' attribute for linked provider info.
    """
    # Check identities attribute (JSON list of linked providers)
    if attributes:
        identities = attributes.get("identities", "")
        if identities:
            try:
                providers = json.loads(identities)
                if providers and isinstance(providers, list):
                    return providers[0].get("providerName", "native")
            except (json.JSONDecodeError, IndexError, TypeError):
                pass

    # Fallback: check if username has a known provider prefix
    if "_" in username:
        prefix = username.split("_", 1)[0]
        if prefix in ("Google", "Facebook", "LoginWithAmazon", "SignInWithApple"):
            return prefix
    return "native"


def _parse_cognito_date(dt: datetime.datetime | None) -> str:
    """Convert a Cognito datetime to ISO 8601 string."""
    if dt is None:
        return ""
    if isinstance(dt, datetime.datetime):
        return dt.isoformat()
    return str(dt)


def _get_last_n_months(n: int) -> list[str]:
    """Return the last N month keys in YYYY-MM format, most recent first."""
    now = datetime.datetime.now(datetime.timezone.utc)
    months = []
    for i in range(n):
        dt = now - datetime.timedelta(days=30 * i)
        months.append(dt.strftime("%Y-%m"))
    # Deduplicate in case 30-day offsets land in the same month
    seen = set()
    result = []
    for m in months:
        if m not in seen:
            seen.add(m)
            result.append(m)
    return result


# ---------------------------------------------------------------------------
# Data fetching helpers for list_users
# ---------------------------------------------------------------------------


def _fetch_all_cognito_users(region: str, user_pool_id: str) -> list[dict]:
    """Fetch all users from Cognito, handling pagination tokens.

    Returns a list of raw Cognito user dicts. Returns empty list if pool is
    not configured. Returns partial results on mid-pagination failure.
    """
    if not user_pool_id:
        logger.warning("cognito_user_pool_id not configured; returning empty user list")
        return []

    client = boto3.client("cognito-idp", region_name=region)
    all_users: list[dict] = []
    pagination_token: str | None = None

    try:
        while True:
            kwargs: dict = {"UserPoolId": user_pool_id, "Limit": 60}
            if pagination_token:
                kwargs["PaginationToken"] = pagination_token
            response = client.list_users(**kwargs)
            all_users.extend(response.get("Users", []))
            pagination_token = response.get("PaginationToken")
            if not pagination_token:
                break
    except (ClientError, BotoCoreError) as e:
        logger.warning("Cognito ListUsers failed: %s; returning partial data", e)
        return all_users  # Return whatever was fetched before failure

    return all_users


def _scan_all_usage_data(region: str) -> dict[str, dict]:
    """Scan DynamoDB usage table for all user profile and current-month records.

    Returns {user_id: {"profile": item|None, "month": item|None}}.
    Returns partial data on failure.
    """
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
    except (ClientError, BotoCoreError) as e:
        logger.warning("DynamoDB usage table scan failed: %s; usage data incomplete", e)
        return by_user  # Return whatever was scanned before failure

    return by_user


def _merge_user_data(
    cognito_users: list[dict],
    usage_by_user: dict[str, dict],
) -> list[UserRecord]:
    """Merge Cognito user data with DynamoDB usage data into UserRecord list.

    Handles duplicate emails (native + federated) by including both records
    with their respective identity_provider field set.
    """
    records: list[UserRecord] = []
    processed_subs: set[str] = set()

    for user in cognito_users:
        attributes = {a["Name"]: a["Value"] for a in user.get("Attributes", [])}
        sub = attributes.get("sub", "")
        email = attributes.get("email", user.get("Username", ""))
        cognito_username = user.get("Username", "")

        if sub:
            processed_subs.add(sub)

        # Cognito status
        enabled = user.get("Enabled", True)
        status = "enabled" if enabled else "disabled"

        # Identity provider detection
        identity_provider = _detect_identity_provider(cognito_username, attributes)

        # Created date from Cognito
        created_date = _parse_cognito_date(user.get("UserCreateDate"))

        # Usage data from DynamoDB (keyed by sub)
        usage_bucket = usage_by_user.get(sub, {"profile": None, "month": None})
        profile = usage_bucket.get("profile") or {}
        month_data = usage_bucket.get("month") or {}

        tier = str(profile.get("tier", DEFAULT_TIER))
        if tier not in TIERS:
            tier = DEFAULT_TIER

        sessions_used = int(month_data.get("sessions_used", 0))
        minutes_used = int(month_data.get("minutes_used", 0))
        subscription_status = profile.get("subscription_status")

        # Last active: prefer DynamoDB last_active, fallback to Cognito UserLastModifiedDate
        last_active_raw = profile.get("last_active")
        if last_active_raw:
            last_active = str(last_active_raw)
        elif user.get("UserLastModifiedDate"):
            last_active = _parse_cognito_date(user.get("UserLastModifiedDate"))
        else:
            last_active = None

        records.append(
            UserRecord(
                cognito_username=cognito_username,
                email=email,
                tier=tier,
                status=status,
                identity_provider=identity_provider,
                created_date=created_date,
                last_active=last_active,
                sessions_used=sessions_used,
                minutes_used=minutes_used,
                subscription_status=subscription_status,
            )
        )

    # Include users that exist in DynamoDB but not in Cognito (defensive)
    for user_id, bucket in usage_by_user.items():
        if user_id in processed_subs:
            continue
        profile = bucket.get("profile") or {}
        month_data = bucket.get("month") or {}

        tier = str(profile.get("tier", DEFAULT_TIER))
        if tier not in TIERS:
            tier = DEFAULT_TIER

        records.append(
            UserRecord(
                cognito_username=user_id,
                email=str(profile.get("email", "")),
                tier=tier,
                status="enabled",  # Unknown status, default to enabled
                identity_provider="native",
                created_date=str(profile.get("created_at", "")),
                last_active=str(profile.get("last_active", "")) or None,
                sessions_used=int(month_data.get("sessions_used", 0)),
                minutes_used=int(month_data.get("minutes_used", 0)),
                subscription_status=profile.get("subscription_status"),
            )
        )

    return records


def _apply_filters(
    records: list[UserRecord],
    search_email: str | None = None,
    filter_tier: str | None = None,
    filter_status: str | None = None,
) -> list[UserRecord]:
    """Apply email search and tier/status filters to user records.

    All filters are applied simultaneously (AND logic). Email search is
    case-insensitive substring match.
    """
    filtered = records

    if search_email:
        search_lower = search_email.lower()
        filtered = [r for r in filtered if search_lower in r.email.lower()]

    if filter_tier:
        tier_lower = filter_tier.lower()
        filtered = [r for r in filtered if r.tier == tier_lower]

    if filter_status:
        status_lower = filter_status.lower()
        filtered = [r for r in filtered if r.status == status_lower]

    return filtered


def _compute_stats(records: list[UserRecord]) -> UserStats:
    """Compute aggregate stats for a filtered set of user records."""
    total = len(records)
    free_count = sum(1 for r in records if r.tier == "free")
    pro_count = sum(1 for r in records if r.tier == "pro")
    business_count = sum(1 for r in records if r.tier == "business")

    return UserStats(
        total_users=total,
        free_count=free_count,
        pro_count=pro_count,
        business_count=business_count,
    )


# ---------------------------------------------------------------------------
# Public API — User listing
# ---------------------------------------------------------------------------


def list_users(
    page: int = 1,
    page_size: int = 20,
    search_email: str | None = None,
    filter_tier: str | None = None,
    filter_status: str | None = None,
) -> PaginatedUserList:
    """Return a paginated, filtered list of users merged from Cognito + DynamoDB.

    Steps:
      1. Fetch ALL users from Cognito (with pagination token handling).
      2. Scan ALL usage data from DynamoDB.
      3. Merge into UserRecord list.
      4. Apply filters (email search, tier, status).
      5. Compute stats on the filtered result set.
      6. Paginate and return the requested page.

    Graceful degradation: if Cognito or DynamoDB fails, returns partial data
    from whichever source succeeded.
    """
    settings = get_settings()

    # Fetch data from both sources
    cognito_users = _fetch_all_cognito_users(
        settings.aws_region, settings.cognito_user_pool_id
    )
    usage_data = _scan_all_usage_data(settings.aws_region)

    # Merge Cognito + DynamoDB data
    all_records = _merge_user_data(cognito_users, usage_data)

    # Sort by email (case-insensitive) for stable ordering
    all_records.sort(key=lambda r: (r.email or r.cognito_username).lower())

    # Apply filters
    filtered_records = _apply_filters(
        all_records,
        search_email=search_email,
        filter_tier=filter_tier,
        filter_status=filter_status,
    )

    # Compute stats on filtered result set (reflects filters, not unfiltered total)
    stats = _compute_stats(filtered_records)

    # Pagination
    total_users = len(filtered_records)
    total_pages = max(1, math.ceil(total_users / page_size))

    # Clamp page to valid range
    page = max(1, min(page, total_pages))

    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    page_records = filtered_records[start_idx:end_idx]

    return PaginatedUserList(
        users=page_records,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        total_users=total_users,
        stats=stats,
    )


# ---------------------------------------------------------------------------
# Public API — User detail
# ---------------------------------------------------------------------------


def get_user_detail(cognito_username: str) -> UserDetail:
    """Fetch detailed information for a single user.

    Queries Cognito for the user profile, DynamoDB usage table for the last
    3 months of usage, and the transcript history table for recent sessions.

    Raises:
        HTTPException(404): If the user is not found in Cognito.
    """
    settings = get_settings()
    region = settings.aws_region
    user_pool_id = settings.cognito_user_pool_id

    # --- 1. Query Cognito for user profile ---
    cognito_client = boto3.client("cognito-idp", region_name=region)
    try:
        response = cognito_client.admin_get_user(
            UserPoolId=user_pool_id,
            Username=cognito_username,
        )
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code", "")
        if error_code == "UserNotFoundException":
            raise HTTPException(status_code=404, detail="User not found")
        logger.error("Cognito AdminGetUser failed: %s", error_code)
        raise HTTPException(status_code=502, detail="Failed to query user from Cognito")
    except BotoCoreError as exc:
        logger.error("Cognito AdminGetUser request failed: %s", type(exc).__name__)
        raise HTTPException(status_code=502, detail="Failed to query user from Cognito")

    # Parse Cognito response
    attributes = {
        attr["Name"]: attr["Value"] for attr in response.get("UserAttributes", [])
    }
    email = attributes.get("email", cognito_username)
    user_status = "enabled" if response.get("Enabled", True) else "disabled"
    created_date = ""
    if response.get("UserCreateDate"):
        created_date = response["UserCreateDate"].isoformat()
    identity_provider = _detect_identity_provider(cognito_username, attributes)

    # --- 2. Query DynamoDB usage table for profile + monthly usage ---
    dynamodb = boto3.resource("dynamodb", region_name=region)
    usage_table = dynamodb.Table(_usage_table_name())

    # Get user profile (tier, subscription)
    tier = DEFAULT_TIER
    subscription_status: str | None = None
    sessions_used_current = 0
    minutes_used_current = 0

    try:
        profile_resp = usage_table.get_item(
            Key={"pk": f"USER#{cognito_username}", "sk": "PROFILE"},
        )
        profile_item = profile_resp.get("Item")
        if profile_item:
            tier = str(profile_item.get("tier", DEFAULT_TIER))
            if tier not in TIERS:
                tier = DEFAULT_TIER
            subscription_status = profile_item.get("subscription_status")
    except (ClientError, BotoCoreError):
        logger.warning("Failed to fetch user profile from usage table for %s", cognito_username)

    # Get last 3 months of usage
    months = _get_last_n_months(3)
    usage_history: list[MonthlyUsage] = []

    for month in months:
        try:
            month_resp = usage_table.get_item(
                Key={"pk": f"USER#{cognito_username}", "sk": f"MONTH#{month}"},
            )
            month_item = month_resp.get("Item")
            sessions = int(month_item.get("sessions_used", 0)) if month_item else 0
            minutes = int(month_item.get("minutes_used", 0)) if month_item else 0
            usage_history.append(MonthlyUsage(
                month=month,
                sessions_used=sessions,
                minutes_used=minutes,
            ))
            # Track current month usage for the profile record
            if month == months[0]:
                sessions_used_current = sessions
                minutes_used_current = minutes
        except (ClientError, BotoCoreError):
            logger.warning("Failed to fetch usage for month %s for user %s", month, cognito_username)
            usage_history.append(MonthlyUsage(
                month=month,
                sessions_used=0,
                minutes_used=0,
            ))

    # --- 3. Query DynamoDB transcript-history table for recent sessions ---
    transcript_sessions: list[TranscriptSessionSummary] = []
    try:
        history_client = boto3.client("dynamodb", region_name=region)
        history_resp = history_client.query(
            TableName=_transcript_history_table_name(),
            KeyConditionExpression="user_id = :uid",
            ExpressionAttributeValues={":uid": {"S": cognito_username}},
            ScanIndexForward=False,
            Limit=20,
        )
        for item in history_resp.get("Items", []):
            try:
                session_id = item.get("session_id", {}).get("S", "")
                created_at = item.get("created_at", {}).get("S", "")
                segment_count = int(item.get("segment_count", {}).get("N", "0"))
                # duration_seconds may not exist in all records
                duration_raw = item.get("duration_seconds", {}).get("N")
                duration_seconds = int(duration_raw) if duration_raw else None
                transcript_sessions.append(TranscriptSessionSummary(
                    session_id=session_id,
                    created_at=created_at,
                    segment_count=segment_count,
                    duration_seconds=duration_seconds,
                ))
            except (KeyError, TypeError, ValueError):
                continue
    except (ClientError, BotoCoreError):
        logger.warning("Failed to fetch transcript history for user %s", cognito_username)

    # --- 4. Build the profile record ---
    profile = UserRecord(
        cognito_username=cognito_username,
        email=email,
        tier=tier,
        status=user_status,
        identity_provider=identity_provider,
        created_date=created_date,
        last_active=None,
        sessions_used=sessions_used_current,
        minutes_used=minutes_used_current,
        subscription_status=subscription_status,
    )

    # --- 5. Determine Stripe subscription status ---
    has_stripe_subscription = subscription_status == "active"

    return UserDetail(
        profile=profile,
        usage_history=usage_history,
        transcript_sessions=transcript_sessions,
        audit_log=[],  # Phase 2 — will be populated by admin_audit service
        has_stripe_subscription=has_stripe_subscription,
    )


# ---------------------------------------------------------------------------
# Public API — User mutations
# ---------------------------------------------------------------------------


def _is_federated_user(cognito_username: str) -> bool:
    """Check if a user is federated-only (no native password)."""
    return any(cognito_username.startswith(prefix) for prefix in FEDERATED_PREFIXES)


def _record_audit(
    admin_user_id: str,
    target_user_id: str,
    action_type: str,
    previous_value: str | None = None,
    new_value: str | None = None,
) -> None:
    """Write audit log entry. Raises on failure so caller can rollback."""
    if admin_audit is None:
        raise RuntimeError("admin_audit service not available")
    admin_audit.record_action(
        admin_user_id=admin_user_id,
        target_user_id=target_user_id,
        action_type=action_type,
        previous_value=previous_value,
        new_value=new_value,
    )


def disable_user(cognito_username: str, admin_user_id: str) -> UserActionResult:
    """Disable a user account in Cognito.

    Calls AdminDisableUser, writes audit log, and rolls back if audit fails.

    Args:
        cognito_username: The Cognito username of the target user.
        admin_user_id: The admin performing the action (for audit).

    Returns:
        UserActionResult indicating success or failure.

    Raises:
        HTTPException(500): If audit logging fails (mutation is rolled back).
        HTTPException(502): If the Cognito call fails.
    """
    settings = get_settings()
    cognito_client = boto3.client("cognito-idp", region_name=settings.aws_region)

    # Execute mutation
    try:
        cognito_client.admin_disable_user(
            UserPoolId=settings.cognito_user_pool_id,
            Username=cognito_username,
        )
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code", "")
        if error_code == "UserNotFoundException":
            raise HTTPException(status_code=404, detail="User not found")
        logger.error("Cognito AdminDisableUser failed: %s", error_code)
        raise HTTPException(
            status_code=502,
            detail=f"Failed to disable user: {error_code}",
        )
    except BotoCoreError as exc:
        logger.error("Cognito AdminDisableUser request failed: %s", type(exc).__name__)
        raise HTTPException(status_code=502, detail="Failed to disable user")

    # Write audit log
    try:
        _record_audit(admin_user_id, cognito_username, "disable", "enabled", "disabled")
    except Exception as exc:
        # Rollback: re-enable the user
        logger.critical(
            "Audit write failed for disable_user(%s); rolling back. Error: %s",
            cognito_username,
            exc,
        )
        try:
            cognito_client.admin_enable_user(
                UserPoolId=settings.cognito_user_pool_id,
                Username=cognito_username,
            )
        except Exception as rollback_exc:
            logger.critical(
                "Rollback (re-enable) also failed for %s: %s",
                cognito_username,
                rollback_exc,
            )
        raise HTTPException(
            status_code=500,
            detail="Action failed: unable to record audit log",
        )

    return UserActionResult(success=True, message="User disabled successfully")


def enable_user(cognito_username: str, admin_user_id: str) -> UserActionResult:
    """Enable a previously disabled user account in Cognito.

    Calls AdminEnableUser, writes audit log, and rolls back if audit fails.

    Args:
        cognito_username: The Cognito username of the target user.
        admin_user_id: The admin performing the action (for audit).

    Returns:
        UserActionResult indicating success or failure.

    Raises:
        HTTPException(500): If audit logging fails (mutation is rolled back).
        HTTPException(502): If the Cognito call fails.
    """
    settings = get_settings()
    cognito_client = boto3.client("cognito-idp", region_name=settings.aws_region)

    # Execute mutation
    try:
        cognito_client.admin_enable_user(
            UserPoolId=settings.cognito_user_pool_id,
            Username=cognito_username,
        )
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code", "")
        if error_code == "UserNotFoundException":
            raise HTTPException(status_code=404, detail="User not found")
        logger.error("Cognito AdminEnableUser failed: %s", error_code)
        raise HTTPException(
            status_code=502,
            detail=f"Failed to enable user: {error_code}",
        )
    except BotoCoreError as exc:
        logger.error("Cognito AdminEnableUser request failed: %s", type(exc).__name__)
        raise HTTPException(status_code=502, detail="Failed to enable user")

    # Write audit log
    try:
        _record_audit(admin_user_id, cognito_username, "enable", "disabled", "enabled")
    except Exception as exc:
        # Rollback: re-disable the user
        logger.critical(
            "Audit write failed for enable_user(%s); rolling back. Error: %s",
            cognito_username,
            exc,
        )
        try:
            cognito_client.admin_disable_user(
                UserPoolId=settings.cognito_user_pool_id,
                Username=cognito_username,
            )
        except Exception as rollback_exc:
            logger.critical(
                "Rollback (re-disable) also failed for %s: %s",
                cognito_username,
                rollback_exc,
            )
        raise HTTPException(
            status_code=500,
            detail="Action failed: unable to record audit log",
        )

    return UserActionResult(success=True, message="User enabled successfully")


def reset_password(cognito_username: str, admin_user_id: str) -> UserActionResult:
    """Trigger a password reset for a user via Cognito.

    Rejects federated-only users (no native password to reset). Writes audit
    log on success; raises HTTPException(500) if audit fails (password reset
    cannot be easily rolled back, so a critical log is emitted).

    Args:
        cognito_username: The Cognito username of the target user.
        admin_user_id: The admin performing the action (for audit).

    Returns:
        UserActionResult indicating success or failure.

    Raises:
        HTTPException(500): If audit logging fails.
        HTTPException(502): If the Cognito call fails.
    """
    # Detect federated-only users — password reset not applicable
    if _is_federated_user(cognito_username):
        return UserActionResult(
            success=False,
            message="Password reset not applicable for federated users",
        )

    settings = get_settings()
    cognito_client = boto3.client("cognito-idp", region_name=settings.aws_region)

    # Execute mutation
    try:
        cognito_client.admin_reset_user_password(
            UserPoolId=settings.cognito_user_pool_id,
            Username=cognito_username,
        )
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code", "")
        if error_code == "UserNotFoundException":
            raise HTTPException(status_code=404, detail="User not found")
        logger.error("Cognito AdminResetUserPassword failed: %s", error_code)
        raise HTTPException(
            status_code=502,
            detail=f"Failed to reset password: {error_code}",
        )
    except BotoCoreError as exc:
        logger.error(
            "Cognito AdminResetUserPassword request failed: %s", type(exc).__name__
        )
        raise HTTPException(status_code=502, detail="Failed to reset password")

    # Write audit log — can't rollback a password reset, so log critically on failure
    try:
        _record_audit(admin_user_id, cognito_username, "reset_password")
    except Exception as exc:
        logger.critical(
            "Audit write failed for reset_password(%s). "
            "Password reset was executed but NOT audited. Error: %s",
            cognito_username,
            exc,
        )
        raise HTTPException(
            status_code=500,
            detail="Action failed: unable to record audit log",
        )

    return UserActionResult(success=True, message="Password reset email sent")


def change_tier(
    cognito_username: str, new_tier: str, admin_user_id: str
) -> TierChangeResult:
    """Change a user's subscription tier in DynamoDB.

    Validates the tier value, updates the tier and quota limits in the usage
    table, writes audit log, and rolls back on audit failure. Includes a
    warning if the user has an active Stripe subscription.

    Args:
        cognito_username: The Cognito username of the target user.
        new_tier: The new tier value ("free", "pro", or "business").
        admin_user_id: The admin performing the action (for audit).

    Returns:
        TierChangeResult with updated user info and optional warning.

    Raises:
        HTTPException(422): If new_tier is not a valid tier value.
        HTTPException(500): If audit logging fails (tier is rolled back).
        HTTPException(502): If the DynamoDB update fails.
    """
    # Validate tier
    if new_tier not in VALID_TIERS:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid tier '{new_tier}'. Must be one of: free, pro, business",
        )

    settings = get_settings()
    dynamodb = boto3.resource("dynamodb", region_name=settings.aws_region)
    usage_table = dynamodb.Table(_usage_table_name())

    # Fetch current profile to get previous tier and subscription status
    try:
        profile_resp = usage_table.get_item(
            Key={"pk": f"USER#{cognito_username}", "sk": "PROFILE"},
        )
    except (ClientError, BotoCoreError) as exc:
        logger.error("Failed to fetch user profile for tier change: %s", exc)
        raise HTTPException(status_code=502, detail="Failed to read user profile")

    profile_item = profile_resp.get("Item") or {}
    previous_tier = str(profile_item.get("tier", DEFAULT_TIER))
    subscription_status = profile_item.get("subscription_status")

    # Get new tier limits for quota update
    tier_limits = TIERS[new_tier]

    # Update tier + quota limits in DynamoDB
    try:
        usage_table.update_item(
            Key={"pk": f"USER#{cognito_username}", "sk": "PROFILE"},
            UpdateExpression=(
                "SET tier = :tier, "
                "sessions_limit = :sessions_limit, "
                "minutes_limit = :minutes_limit, "
                "updated_at = :now"
            ),
            ExpressionAttributeValues={
                ":tier": new_tier,
                ":sessions_limit": tier_limits.max_sessions_per_month,
                ":minutes_limit": tier_limits.max_minutes_per_month,
                ":now": int(time.time()),
            },
        )
    except (ClientError, BotoCoreError) as exc:
        logger.error("DynamoDB tier update failed for %s: %s", cognito_username, exc)
        raise HTTPException(status_code=502, detail="Failed to update user tier")

    # Write audit log
    try:
        _record_audit(
            admin_user_id, cognito_username, "change_tier", previous_tier, new_tier
        )
    except Exception as exc:
        # Rollback: revert tier in DynamoDB
        logger.critical(
            "Audit write failed for change_tier(%s, %s); rolling back. Error: %s",
            cognito_username,
            new_tier,
            exc,
        )
        previous_limits = TIERS.get(previous_tier, TIERS[DEFAULT_TIER])
        try:
            usage_table.update_item(
                Key={"pk": f"USER#{cognito_username}", "sk": "PROFILE"},
                UpdateExpression=(
                    "SET tier = :tier, "
                    "sessions_limit = :sessions_limit, "
                    "minutes_limit = :minutes_limit, "
                    "updated_at = :now"
                ),
                ExpressionAttributeValues={
                    ":tier": previous_tier,
                    ":sessions_limit": previous_limits.max_sessions_per_month,
                    ":minutes_limit": previous_limits.max_minutes_per_month,
                    ":now": int(time.time()),
                },
            )
        except Exception as rollback_exc:
            logger.critical(
                "Rollback (revert tier) also failed for %s: %s",
                cognito_username,
                rollback_exc,
            )
        raise HTTPException(
            status_code=500,
            detail="Action failed: unable to record audit log",
        )

    # Build warning if active Stripe subscription exists
    warning: str | None = None
    if subscription_status == "active":
        warning = (
            "This user has an active Stripe subscription. "
            "The tier change does not modify the underlying Stripe subscription."
        )

    # Build updated user record for response
    updated_user = UserRecord(
        cognito_username=cognito_username,
        email=str(profile_item.get("email", "")),
        tier=new_tier,
        status=str(profile_item.get("status", "enabled")),
        identity_provider=str(profile_item.get("identity_provider", "native")),
        created_date=str(profile_item.get("created_at", "")),
        last_active=str(profile_item.get("last_active", "")) or None,
        sessions_used=int(profile_item.get("sessions_used", 0)),
        minutes_used=int(profile_item.get("minutes_used", 0)),
        subscription_status=subscription_status,
    )

    return TierChangeResult(
        success=True,
        message=f"Tier changed from {previous_tier} to {new_tier}",
        updated_user=updated_user,
        warning=warning,
    )
