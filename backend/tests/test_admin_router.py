"""Router-level tests for admin endpoints.

Only the 401-without-a-token and the happy (admin override) path are tested
here via FastAPI's dependency_overrides. The 403-for-a-non-admin path can't be
exercised this way -- require_admin_user calls require_authenticated_user as
a plain function, not a Depends() sub-dependency, so overriding
require_authenticated_user doesn't affect it. That path is covered against a
mocked Cognito client in test_admin_auth.py instead.

Phase 1 additions (task 1.5):
- GET /api/admin/users returns 200 with valid PaginatedUserList structure
- GET /api/admin/users/{username} returns 200 with UserDetail
- GET /api/admin/users/nonexistent returns 404
"""

from __future__ import annotations

from unittest.mock import patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.routers import admin
from app.routers.admin import router
from app.services.admin_service import AdminOverview, AdminUserRow
from app.services.admin_users import (
    MonthlyUsage,
    PaginatedUserList,
    TranscriptSessionSummary,
    UserDetail,
    UserRecord,
    UserStats,
)
from app.services.auth import AuthenticatedUser, require_admin_user


def _client(with_admin_override: bool = True) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    if with_admin_override:
        app.dependency_overrides[require_admin_user] = lambda: AuthenticatedUser(
            "admin-1", "admin-1", "admin@example.com"
        )
    return TestClient(app)


# ---------------------------------------------------------------------------
# Existing tests: /api/admin/overview
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Phase 1 router tests: GET /api/admin/users
# ---------------------------------------------------------------------------


def _fake_paginated_user_list() -> PaginatedUserList:
    """Build a fake PaginatedUserList for mocking list_users."""
    return PaginatedUserList(
        users=[
            UserRecord(
                cognito_username="user-1",
                email="alice@example.com",
                tier="pro",
                status="enabled",
                identity_provider="native",
                created_date="2024-01-15T10:00:00",
                last_active="2024-06-01T12:00:00",
                sessions_used=5,
                minutes_used=120,
                subscription_status="active",
            ),
            UserRecord(
                cognito_username="user-2",
                email="bob@example.com",
                tier="free",
                status="enabled",
                identity_provider="Google",
                created_date="2024-02-01T08:00:00",
                last_active=None,
                sessions_used=1,
                minutes_used=10,
                subscription_status=None,
            ),
        ],
        page=1,
        page_size=20,
        total_pages=1,
        total_users=2,
        stats=UserStats(total_users=2, free_count=1, pro_count=1, business_count=0),
    )


def _fake_user_detail() -> UserDetail:
    """Build a fake UserDetail for mocking get_user_detail."""
    return UserDetail(
        profile=UserRecord(
            cognito_username="user-1",
            email="alice@example.com",
            tier="pro",
            status="enabled",
            identity_provider="native",
            created_date="2024-01-15T10:00:00",
            last_active="2024-06-01T12:00:00",
            sessions_used=5,
            minutes_used=120,
            subscription_status="active",
        ),
        usage_history=[
            MonthlyUsage(month="2024-06", sessions_used=5, minutes_used=120),
            MonthlyUsage(month="2024-05", sessions_used=3, minutes_used=90),
        ],
        transcript_sessions=[
            TranscriptSessionSummary(
                session_id="sess-001",
                created_at="2024-06-01T10:00:00+00:00",
                segment_count=15,
                duration_seconds=300,
            ),
        ],
        audit_log=[],
        has_stripe_subscription=True,
    )


class TestGetUsersEndpoint:
    """Test GET /api/admin/users router endpoint."""

    def test_returns_200_with_valid_structure(self):
        """GET /api/admin/users returns 200 with PaginatedUserList structure."""
        with patch.object(admin, "list_users", return_value=_fake_paginated_user_list()):
            resp = _client().get("/api/admin/users")

        assert resp.status_code == 200
        body = resp.json()
        assert "users" in body
        assert "page" in body
        assert "page_size" in body
        assert "total_pages" in body
        assert "total_users" in body
        assert "stats" in body
        assert body["page"] == 1
        assert body["total_users"] == 2
        assert len(body["users"]) == 2
        assert body["users"][0]["email"] == "alice@example.com"
        assert body["stats"]["pro_count"] == 1

    def test_passes_query_params_to_service(self):
        """Query params are forwarded to the list_users service function."""
        with patch.object(admin, "list_users", return_value=_fake_paginated_user_list()) as mocked:
            _client().get(
                "/api/admin/users",
                params={"page": 2, "page_size": 10, "search_email": "alice", "filter_tier": "pro", "filter_status": "enabled"},
            )

        mocked.assert_called_once_with(
            page=2,
            page_size=10,
            search_email="alice",
            filter_tier="pro",
            filter_status="enabled",
        )

    def test_requires_auth(self):
        """GET /api/admin/users without auth returns 401."""
        resp = _client(with_admin_override=False).get("/api/admin/users")
        assert resp.status_code == 401


class TestGetUserDetailEndpoint:
    """Test GET /api/admin/users/{cognito_username} router endpoint."""

    def test_returns_200_with_valid_user(self):
        """GET /api/admin/users/{username} returns 200 with UserDetail."""
        with patch.object(admin, "get_user_detail", return_value=_fake_user_detail()):
            resp = _client().get("/api/admin/users/user-1")

        assert resp.status_code == 200
        body = resp.json()
        assert "profile" in body
        assert "usage_history" in body
        assert "transcript_sessions" in body
        assert "has_stripe_subscription" in body
        assert body["profile"]["email"] == "alice@example.com"
        assert body["has_stripe_subscription"] is True
        assert len(body["usage_history"]) == 2

    def test_returns_404_for_nonexistent_user(self):
        """GET /api/admin/users/nonexistent returns 404."""
        with patch.object(
            admin, "get_user_detail",
            side_effect=HTTPException(status_code=404, detail="User not found"),
        ):
            resp = _client().get("/api/admin/users/nonexistent")

        assert resp.status_code == 404
        body = resp.json()
        assert "not found" in body["detail"].lower()

    def test_requires_auth(self):
        """GET /api/admin/users/{username} without auth returns 401."""
        resp = _client(with_admin_override=False).get("/api/admin/users/user-1")
        assert resp.status_code == 401
