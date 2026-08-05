"""Admin dashboard REST endpoints.

``GET /api/admin/overview`` returns every user, aggregated usage/revenue
stats, and coarse system health. Requires Cognito "admin" group membership
(``app.services.auth.require_admin_user``): a signed-in user who isn't a
member gets 403; a missing/invalid token or accounts being disabled entirely
gets the usual 401/409 from the underlying auth dependency.

Phase 1 additions:
- ``GET /api/admin/users`` — paginated, filterable user list
- ``GET /api/admin/users/{cognito_username}`` — single user detail

Phase 2 additions:
- ``POST /api/admin/users/{cognito_username}/disable`` — disable a user
- ``POST /api/admin/users/{cognito_username}/enable`` — enable a user
- ``POST /api/admin/users/{cognito_username}/reset-password`` — trigger password reset
- ``POST /api/admin/users/{cognito_username}/change-tier`` — change subscription tier
- ``DELETE /api/admin/users/{cognito_username}`` — permanently delete a user
"""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.services.admin_service import get_admin_overview
from app.services import admin_audit
from app.services.admin_analytics import (
    get_monthly_usage,
    get_tier_distribution,
    get_top_users,
)
from app.services.admin_revenue import RevenueMetrics, get_revenue_metrics
from app.services.admin_health import SystemHealth, get_system_health
from app.services.admin_users import (
    AuditLogEntry,
    PaginatedUserList,
    TierChangeResult,
    UserActionResult,
    UserDetail,
    change_tier,
    delete_user,
    disable_user,
    enable_user,
    get_user_detail,
    list_users,
    reset_password,
)
from app.services.auth import AuthenticatedUser, require_admin_user

router = APIRouter(prefix="/api/admin", tags=["admin"])


class TierChangeRequest(BaseModel):
    """Request body for the change-tier endpoint."""

    tier: str


@router.get("/overview")
async def get_overview(_admin: AuthenticatedUser = Depends(require_admin_user)):
    """Return the full admin dashboard payload for the current admin user."""

    overview = get_admin_overview()
    return {
        "users": [asdict(row) for row in overview.users],
        "stats": overview.stats,
        "system": overview.system,
    }


@router.get("/users", response_model=PaginatedUserList)
async def get_users(
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    search_email: str | None = Query(None, description="Case-insensitive email substring search"),
    filter_tier: str | None = Query(None, description="Filter by tier: free, pro, business"),
    filter_status: str | None = Query(None, description="Filter by status: enabled, disabled"),
    _admin: AuthenticatedUser = Depends(require_admin_user),
) -> PaginatedUserList:
    """Return a paginated, filterable list of all users."""

    return list_users(
        page=page,
        page_size=page_size,
        search_email=search_email,
        filter_tier=filter_tier,
        filter_status=filter_status,
    )


@router.get("/users/{cognito_username}", response_model=UserDetail)
async def get_user(
    cognito_username: str,
    _admin: AuthenticatedUser = Depends(require_admin_user),
) -> UserDetail:
    """Return detailed information for a single user, including audit log."""

    detail = get_user_detail(cognito_username)

    # Enrich with audit log entries
    raw_entries = admin_audit.get_audit_entries_for_user(cognito_username)
    audit_entries = [
        AuditLogEntry(
            entry_id=entry.get("entry_id", ""),
            admin_user_id=entry.get("admin_user_id", ""),
            target_user_id=entry.get("target_user_id", ""),
            action_type=entry.get("action_type", ""),
            previous_value=entry.get("previous_value"),
            new_value=entry.get("new_value"),
            timestamp=entry.get("timestamp", ""),
        )
        for entry in raw_entries
    ]
    detail.audit_log = audit_entries

    return detail


@router.post("/users/{cognito_username}/disable", response_model=UserActionResult)
async def post_disable_user(
    cognito_username: str,
    admin: AuthenticatedUser = Depends(require_admin_user),
) -> UserActionResult:
    """Disable a user account in Cognito."""

    return disable_user(cognito_username, admin.user_id)


@router.post("/users/{cognito_username}/enable", response_model=UserActionResult)
async def post_enable_user(
    cognito_username: str,
    admin: AuthenticatedUser = Depends(require_admin_user),
) -> UserActionResult:
    """Enable a previously disabled user account."""

    return enable_user(cognito_username, admin.user_id)


@router.delete("/users/{cognito_username}", response_model=UserActionResult)
async def delete_user_endpoint(
    cognito_username: str,
    admin: AuthenticatedUser = Depends(require_admin_user),
) -> UserActionResult:
    """Permanently delete a user's Cognito account and usage-table rows."""

    return delete_user(cognito_username, admin.user_id)


@router.post("/users/{cognito_username}/reset-password", response_model=UserActionResult)
async def post_reset_password(
    cognito_username: str,
    admin: AuthenticatedUser = Depends(require_admin_user),
) -> UserActionResult:
    """Trigger a password reset for a user."""

    return reset_password(cognito_username, admin.user_id)


@router.post("/users/{cognito_username}/change-tier", response_model=TierChangeResult)
async def post_change_tier(
    cognito_username: str,
    body: TierChangeRequest,
    admin: AuthenticatedUser = Depends(require_admin_user),
) -> TierChangeResult:
    """Change a user's subscription tier."""

    return change_tier(cognito_username, body.tier, admin.user_id)


@router.get("/usage")
async def get_usage(
    start_month: str | None = Query(None, description="Start month in YYYY-MM format"),
    end_month: str | None = Query(None, description="End month in YYYY-MM format"),
    _admin: AuthenticatedUser = Depends(require_admin_user),
):
    """Return aggregated monthly usage data and tier distribution."""

    usage_data = get_monthly_usage(start_month=start_month, end_month=end_month)
    tier_dist = get_tier_distribution()

    return {
        "months": [asdict(m) for m in usage_data.months],
        "totals": asdict(usage_data.totals),
        "tier_distribution": asdict(tier_dist),
    }


@router.get("/usage/top-users")
async def get_usage_top_users(
    month: str | None = Query(None, description="Month in YYYY-MM format"),
    _admin: AuthenticatedUser = Depends(require_admin_user),
):
    """Return the top 10 users by minutes used for a given month."""

    rows = get_top_users(month=month)
    return [asdict(row) for row in rows]


@router.get("/revenue", response_model=RevenueMetrics)
async def get_revenue(
    _admin: AuthenticatedUser = Depends(require_admin_user),
) -> RevenueMetrics:
    """Return revenue metrics including MRR, subscriptions, and recent transactions."""

    return get_revenue_metrics()


@router.get("/system", response_model=SystemHealth)
async def get_system(
    _admin: AuthenticatedUser = Depends(require_admin_user),
) -> SystemHealth:
    """Return system health data including ECS status, CloudWatch alarms, and cost estimate."""

    return get_system_health()
