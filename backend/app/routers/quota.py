"""Weekly session allowance endpoint for the frontend."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.config import get_settings
from app.services.auth import AuthenticatedUser, optional_authenticated_user
from app.services.usage_quota import (
    WEEKLY_SESSION_LIMIT,
    get_user_usage,
    check_quota,
)

router = APIRouter(prefix="/api", tags=["quota"])


@router.get("/usage")
async def get_usage(
    user: AuthenticatedUser | None = Depends(optional_authenticated_user),
):
    """Return the authenticated user's current weekly session allowance."""
    settings = get_settings()

    # Anonymous workshop deployments do not identify a user to count.
    if not settings.enable_auth or not user:
        return {
            "sessions_used": 0,
            "limits": {
                "max_sessions_per_week": WEEKLY_SESSION_LIMIT,
                "unlimited_session_duration": True,
            },
            "quota_error": None,
        }

    usage = get_user_usage(user.user_id)
    quota_error = check_quota(user.user_id)

    return {
        "sessions_used": usage.sessions_used,
        "limits": {
            "max_sessions_per_week": WEEKLY_SESSION_LIMIT,
            "unlimited_session_duration": True,
        },
        "quota_error": quota_error,
    }
