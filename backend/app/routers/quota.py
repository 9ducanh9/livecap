"""Usage quota REST endpoints for the frontend billing UI.

GET /api/usage — returns current month's usage + tier limits for the
authenticated user. Used by the Dashboard to show remaining sessions/minutes
and by the session-start flow to pre-check quota before opening a WebSocket.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.config import get_settings
from app.services.auth import AuthenticatedUser, optional_authenticated_user
from app.services.usage_quota import (
    TIERS,
    DEFAULT_TIER,
    get_user_usage,
    check_quota,
)

router = APIRouter(prefix="/api", tags=["quota"])


@router.get("/usage")
async def get_usage(
    user: AuthenticatedUser | None = Depends(optional_authenticated_user),
):
    """Return the authenticated user's current month usage and tier limits."""
    settings = get_settings()

    # If auth is off or quota is disabled, return unlimited
    if not settings.enable_auth or not user:
        return {
            "tier": "unlimited",
            "sessions_used": 0,
            "minutes_used": 0,
            "limits": {
                "max_sessions_per_month": 999_999,
                "max_minutes_per_session": 120,
                "max_minutes_per_month": 999_999,
                "meeting_notes_enabled": True,
            },
            "quota_error": None,
        }

    usage = get_user_usage(user.sub)
    limits = TIERS.get(usage.tier, TIERS[DEFAULT_TIER])
    quota_error = check_quota(user.sub)

    return {
        "tier": usage.tier,
        "sessions_used": usage.sessions_used,
        "minutes_used": usage.minutes_used,
        "limits": {
            "max_sessions_per_month": limits.max_sessions_per_month,
            "max_minutes_per_session": limits.max_minutes_per_session,
            "max_minutes_per_month": limits.max_minutes_per_month,
            "meeting_notes_enabled": limits.meeting_notes_enabled,
        },
        "quota_error": quota_error,
    }
