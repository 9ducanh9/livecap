"""Router-level tests for GET /api/admin/overview.

Only the 401-without-a-token and the happy (admin override) path are tested
here via FastAPI's dependency_overrides. The 403-for-a-non-admin path can't be
exercised this way -- require_admin_user calls require_authenticated_user as
a plain function, not a Depends() sub-dependency, so overriding
require_authenticated_user doesn't affect it. That path is covered against a
mocked Cognito client in test_admin_auth.py instead.
"""

from __future__ import annotations

from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import admin
from app.routers.admin import router
from app.services.admin_service import AdminOverview, AdminUserRow
from app.services.auth import AuthenticatedUser, require_admin_user


def _client(with_admin_override: bool = True) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    if with_admin_override:
        app.dependency_overrides[require_admin_user] = lambda: AuthenticatedUser(
            "admin-1", "admin-1", "admin@example.com"
        )
    return TestClient(app)


def test_overview_requires_auth():
    resp = _client(with_admin_override=False).get("/api/admin/overview")
    assert resp.status_code == 401


def test_overview_returns_aggregated_payload():
    fake_overview = AdminOverview(
        users=[
            AdminUserRow(
                user_id="user-1", email="a@x.com", tier="pro",
                sessions_used=2, minutes_used=30, subscription_status="active",
            )
        ],
        stats={"total_users": 1, "by_tier": {"free": 0, "pro": 1, "business": 0},
               "total_sessions_this_month": 2, "total_minutes_this_month": 30,
               "estimated_mrr_usd": 10},
        system={"backend_reachable": True, "desired_count": 1, "running_count": 1, "pending_count": 0},
    )
    with patch.object(admin, "get_admin_overview", return_value=fake_overview) as mocked:
        resp = _client().get("/api/admin/overview")

    assert resp.status_code == 200
    body = resp.json()
    assert body["users"][0]["user_id"] == "user-1"
    assert body["users"][0]["tier"] == "pro"
    assert body["stats"]["estimated_mrr_usd"] == 10
    assert body["system"]["backend_reachable"] is True
    mocked.assert_called_once_with()
