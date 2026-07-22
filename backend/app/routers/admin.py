"""Admin dashboard REST endpoint.

``GET /api/admin/overview`` returns every user, aggregated usage/revenue
stats, and coarse system health. Requires Cognito "admin" group membership
(``app.services.auth.require_admin_user``): a signed-in user who isn't a
member gets 403; a missing/invalid token or accounts being disabled entirely
gets the usual 401/409 from the underlying auth dependency.
"""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends

from app.services.admin_service import get_admin_overview
from app.services.auth import AuthenticatedUser, require_admin_user

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/overview")
async def get_overview(_admin: AuthenticatedUser = Depends(require_admin_user)):
    """Return the full admin dashboard payload for the current admin user."""

    overview = get_admin_overview()
    return {
        "users": [asdict(row) for row in overview.users],
        "stats": overview.stats,
        "system": overview.system,
    }
