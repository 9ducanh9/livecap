"""Weekly session allowance endpoint for the frontend."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.config import get_settings
from app.services.auth import AuthenticatedUser, is_admin_user, optional_authenticated_user
from app.services.usage_quota import (
    FREE_SESSION_MAX_SECONDS,
    WEEKLY_MINUTE_LIMIT,
    WEEKLY_SESSION_LIMIT,
    get_user_usage,
    check_quota,
)

router = APIRouter(prefix="/api", tags=["quota"])


@router.get("/usage")
async def get_usage(
    user: AuthenticatedUser | None = Depends(optional_authenticated_user),
):
    """Return the authenticated user's current weekly session and minute allowance."""
    settings = get_settings()

    # Anonymous workshop deployments do not identify a user to count.
    if not settings.enable_auth or not user:
        return {
            "sessions_used": 0,
            "minutes_used": 0,
            "is_admin": False,
            "tier": "free",
            "limits": {
                "max_sessions_per_week": WEEKLY_SESSION_LIMIT,
                "max_minutes_per_week": WEEKLY_MINUTE_LIMIT,
                "max_session_seconds": settings.session_timeout or FREE_SESSION_MAX_SECONDS,
                "unlimited_session_duration": True,
            },
            "quota_error": None,
        }

    admin = is_admin_user(user)
    usage = get_user_usage(user.user_id)
    quota_error = None if admin else check_quota(user.user_id, is_admin=admin)
    max_session_seconds = None if admin else (settings.session_timeout or FREE_SESSION_MAX_SECONDS)

    return {
        "sessions_used": usage.sessions_used,
        "minutes_used": usage.minutes_used,
        "is_admin": admin,
        "tier": "unlimited" if admin else usage.tier,
        "limits": {
            "max_sessions_per_week": None if admin else WEEKLY_SESSION_LIMIT,
            "max_minutes_per_week": None if admin else WEEKLY_MINUTE_LIMIT,
            "max_session_seconds": max_session_seconds,
            "unlimited_session_duration": bool(admin),
        },
        "quota_error": quota_error,
    }
