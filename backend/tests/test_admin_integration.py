"""End-to-end integration tests for the admin panel API.

Tests exercise the full request lifecycle through FastAPI's TestClient with
the admin dependency overridden. All AWS services (Cognito, DynamoDB) and
Stripe are mocked at the service layer level.

Validates: Requirements 1.1, 2.1, 4.1, 6.1, 10.1, 12.1, 13.1
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers.admin import router
from app.services.admin_users import (
    AuditLogEntry,
    MonthlyUsage,
    PaginatedUserList,
    TierChangeResult,
    TranscriptSessionSummary,
    UserActionResult,
    UserDetail,
    UserRecord,
    UserStats,
)
from app.services.auth import AuthenticatedUser, require_admin_user


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


def _make_app() -> FastAPI:
    """Create a FastAPI app with admin router and admin auth override."""
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_admin_user] = lambda: AuthenticatedUser(
        "admin-001", "admin-001", "admin@livecap.io"
    )
    return app


def _client() -> TestClient:
    return TestClient(_make_app())


def _sample_user(
    username: str = "user-1",
    email: str = "alice@example.com",
    tier: str = "pro",
    status: str = "enabled",
) -> UserRecord:
    return UserRecord(
        cognito_username=username,
        email=email,
        tier=tier,
        status=status,
        identity_provider="native",
        created_date="2024-01-15T10:00:00",
        last_active="2024-06-01T12:00:00",
        sessions_used=5,
        minutes_used=120,
        subscription_status="active",
    )


def _sample_paginated_list(
    users: list[UserRecord] | None = None,
    total_users: int | None = None,
    filter_tier: str | None = None,
) -> PaginatedUserList:
    if users is None:
        users = [
            _sample_user("user-1", "alice@example.com", "pro"),
            _sample_user("user-2", "bob@example.com", "free"),
            _sample_user("user-3", "carol@example.com", "business"),
        ]
    total = total_users if total_users is not None else len(users)
    free_count = sum(1 for u in users if u.tier == "free")
    pro_count = sum(1 for u in users if u.tier == "pro")
    business_count = sum(1 for u in users if u.tier == "business")
    return PaginatedUserList(
        users=users,
        page=1,
        page_size=20,
        total_pages=1,
        total_users=total,
        stats=UserStats(
            total_users=total,
            free_count=free_count,
            pro_count=pro_count,
            business_count=business_count,
        ),
    )


def _sample_user_detail(username: str = "user-1") -> UserDetail:
    return UserDetail(
        profile=_sample_user(username),
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


# ---------------------------------------------------------------------------
# Test: User Management Flow
# Validates: Requirements 1.1, 2.1, 4.1
# ---------------------------------------------------------------------------


class TestUserManagementFlow:
    """Test the full user management flow: list → filter → detail → disable → enable."""

    def test_full_user_management_flow(self):
        """Exercise list, filter, detail, disable, enable in sequence."""
        client = _client()

        # Step 1: GET /api/admin/users → returns paginated list
        with patch("app.routers.admin.list_users", return_value=_sample_paginated_list()):
            resp = client.get("/api/admin/users")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_users"] == 3
        assert len(body["users"]) == 3
        assert body["stats"]["pro_count"] == 1

        # Step 2: GET /api/admin/users?filter_tier=pro → filters work
        filtered_users = [_sample_user("user-1", "alice@example.com", "pro")]
        with patch(
            "app.routers.admin.list_users",
            return_value=_sample_paginated_list(users=filtered_users),
        ) as mock_list:
            resp = client.get("/api/admin/users", params={"filter_tier": "pro"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_users"] == 1
        assert body["users"][0]["tier"] == "pro"
        mock_list.assert_called_once_with(
            page=1,
            page_size=20,
            search_email=None,
            filter_tier="pro",
            filter_status=None,
        )

        # Step 3: GET /api/admin/users/{username} → returns detail
        detail = _sample_user_detail("user-1")
        with patch("app.routers.admin.get_user_detail", return_value=detail):
            with patch(
                "app.routers.admin.admin_audit.get_audit_entries_for_user",
                return_value=[],
            ):
                resp = client.get("/api/admin/users/user-1")
        assert resp.status_code == 200
        body = resp.json()
        assert body["profile"]["cognito_username"] == "user-1"
        assert body["profile"]["email"] == "alice@example.com"
        assert len(body["usage_history"]) == 2

        # Step 4: POST /api/admin/users/{username}/disable → success
        with patch(
            "app.routers.admin.disable_user",
            return_value=UserActionResult(success=True, message="User disabled successfully"),
        ):
            resp = client.post("/api/admin/users/user-1/disable")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert "disabled" in body["message"].lower()

        # Step 5: POST /api/admin/users/{username}/enable → success
        with patch(
            "app.routers.admin.enable_user",
            return_value=UserActionResult(success=True, message="User enabled successfully"),
        ):
            resp = client.post("/api/admin/users/user-1/enable")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert "enabled" in body["message"].lower()


# ---------------------------------------------------------------------------
# Test: Tier Change with Audit
# Validates: Requirements 6.1
# ---------------------------------------------------------------------------


class TestTierChangeWithAudit:
    """Test tier change endpoint and verify audit was called."""

    def test_tier_change_with_audit_verification(self):
        """POST /api/admin/users/{username}/change-tier succeeds and audit is recorded."""
        client = _client()

        updated_user = _sample_user("user-1", "alice@example.com", "business")
        result = TierChangeResult(
            success=True,
            message="Tier changed from pro to business",
            updated_user=updated_user,
            warning=None,
        )

        with patch("app.routers.admin.change_tier", return_value=result) as mock_change:
            resp = client.post(
                "/api/admin/users/user-1/change-tier",
                json={"tier": "business"},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["updated_user"]["tier"] == "business"
        assert "pro" in body["message"].lower() or "business" in body["message"].lower()
        # Verify the service was called with correct args (including admin user id)
        mock_change.assert_called_once_with("user-1", "business", "admin-001")

    def test_tier_change_with_stripe_warning(self):
        """Tier change for subscribed user includes Stripe warning."""
        client = _client()

        updated_user = _sample_user("user-1", "alice@example.com", "free")
        result = TierChangeResult(
            success=True,
            message="Tier changed from pro to free",
            updated_user=updated_user,
            warning="User has an active Stripe subscription. This change does not modify the underlying subscription.",
        )

        with patch("app.routers.admin.change_tier", return_value=result):
            resp = client.post(
                "/api/admin/users/user-1/change-tier",
                json={"tier": "free"},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["warning"] is not None
        assert "stripe" in body["warning"].lower() or "subscription" in body["warning"].lower()


# ---------------------------------------------------------------------------
# Test: Usage Analytics
# Validates: Requirements 10.1
# ---------------------------------------------------------------------------


class TestUsageAnalytics:
    """Test usage analytics endpoints with date range filtering."""

    def test_usage_monthly_data(self):
        """GET /api/admin/usage → returns monthly data and tier distribution."""
        client = _client()

        from dataclasses import dataclass

        from app.services.admin_analytics import (
            MonthSummary,
            MonthlyUsageData,
            TierDistribution,
            TierStats,
            UsageTotals,
        )

        mock_usage = MonthlyUsageData(
            months=[
                MonthSummary(
                    month="2024-06",
                    total_sessions=50,
                    total_minutes=1200,
                    unique_active_users=15,
                ),
                MonthSummary(
                    month="2024-05",
                    total_sessions=40,
                    total_minutes=900,
                    unique_active_users=12,
                ),
            ],
            totals=UsageTotals(
                total_sessions=90,
                total_minutes=2100,
                unique_active_users=20,
            ),
        )

        mock_tier_dist = TierDistribution(
            free=TierStats(count=10, percentage=50.0),
            pro=TierStats(count=7, percentage=35.0),
            business=TierStats(count=3, percentage=15.0),
        )

        with patch("app.routers.admin.get_monthly_usage", return_value=mock_usage) as mock_fn:
            with patch("app.routers.admin.get_tier_distribution", return_value=mock_tier_dist):
                resp = client.get("/api/admin/usage")

        assert resp.status_code == 200
        body = resp.json()
        assert "months" in body
        assert "totals" in body
        assert "tier_distribution" in body
        assert len(body["months"]) == 2
        assert body["totals"]["total_sessions"] == 90
        assert body["totals"]["total_minutes"] == 2100
        assert body["tier_distribution"]["free"]["count"] == 10

    def test_usage_with_date_range_filter(self):
        """GET /api/admin/usage with start_month/end_month passes params to service."""
        client = _client()

        from app.services.admin_analytics import (
            MonthSummary,
            MonthlyUsageData,
            TierDistribution,
            TierStats,
            UsageTotals,
        )

        mock_usage = MonthlyUsageData(
            months=[
                MonthSummary(
                    month="2024-05",
                    total_sessions=40,
                    total_minutes=900,
                    unique_active_users=12,
                ),
            ],
            totals=UsageTotals(
                total_sessions=40,
                total_minutes=900,
                unique_active_users=12,
            ),
        )

        mock_tier_dist = TierDistribution(
            free=TierStats(count=5, percentage=50.0),
            pro=TierStats(count=3, percentage=30.0),
            business=TierStats(count=2, percentage=20.0),
        )

        with patch("app.routers.admin.get_monthly_usage", return_value=mock_usage) as mock_fn:
            with patch("app.routers.admin.get_tier_distribution", return_value=mock_tier_dist):
                resp = client.get(
                    "/api/admin/usage",
                    params={"start_month": "2024-05", "end_month": "2024-05"},
                )

        assert resp.status_code == 200
        mock_fn.assert_called_once_with(start_month="2024-05", end_month="2024-05")
        body = resp.json()
        assert len(body["months"]) == 1
        assert body["months"][0]["month"] == "2024-05"

    def test_usage_top_users(self):
        """GET /api/admin/usage/top-users → returns top users list."""
        client = _client()

        from app.services.admin_analytics import TopUserRow

        mock_top_users = [
            TopUserRow(email="poweruser@x.com", tier="business", sessions_used=20, minutes_used=500),
            TopUserRow(email="active@x.com", tier="pro", sessions_used=15, minutes_used=300),
        ]

        with patch("app.routers.admin.get_top_users", return_value=mock_top_users):
            resp = client.get("/api/admin/usage/top-users")

        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 2
        assert body[0]["email"] == "poweruser@x.com"
        assert body[0]["minutes_used"] == 500
        assert body[1]["tier"] == "pro"


# ---------------------------------------------------------------------------
# Test: Revenue Endpoint
# Validates: Requirements 12.1
# ---------------------------------------------------------------------------


class TestRevenueEndpoint:
    """Test revenue endpoint with mocked Stripe."""

    def test_revenue_returns_metrics(self):
        """GET /api/admin/revenue → returns revenue metrics from mocked Stripe."""
        client = _client()

        from app.services.admin_revenue import RevenueMetrics, StripeTransaction

        mock_metrics = RevenueMetrics(
            mrr_usd=2500.00,
            active_subscriptions=50,
            churned_subscriptions=3,
            recent_transactions=[
                StripeTransaction(
                    date="2024-06-01T10:00:00+00:00",
                    user_email="customer@x.com",
                    amount_cents=1999,
                    currency="usd",
                    transaction_type="payment",
                ),
                StripeTransaction(
                    date="2024-05-28T14:30:00+00:00",
                    user_email="refunded@x.com",
                    amount_cents=999,
                    currency="usd",
                    transaction_type="refund",
                ),
            ],
            stripe_data_available=True,
            warning=None,
        )

        with patch("app.routers.admin.get_revenue_metrics", return_value=mock_metrics):
            resp = client.get("/api/admin/revenue")

        assert resp.status_code == 200
        body = resp.json()
        assert body["mrr_usd"] == 2500.00
        assert body["active_subscriptions"] == 50
        assert body["churned_subscriptions"] == 3
        assert body["stripe_data_available"] is True
        assert body["warning"] is None
        assert len(body["recent_transactions"]) == 2
        assert body["recent_transactions"][0]["transaction_type"] == "payment"
        assert body["recent_transactions"][1]["transaction_type"] == "refund"

    def test_revenue_stripe_unavailable(self):
        """GET /api/admin/revenue with Stripe unavailable returns degraded response."""
        client = _client()

        from app.services.admin_revenue import RevenueMetrics

        mock_metrics = RevenueMetrics(
            mrr_usd=0.0,
            active_subscriptions=0,
            churned_subscriptions=0,
            recent_transactions=[],
            stripe_data_available=False,
            warning="Stripe API unavailable: connection timeout",
        )

        with patch("app.routers.admin.get_revenue_metrics", return_value=mock_metrics):
            resp = client.get("/api/admin/revenue")

        assert resp.status_code == 200
        body = resp.json()
        assert body["stripe_data_available"] is False
        assert body["warning"] is not None
        assert "unavailable" in body["warning"].lower()


# ---------------------------------------------------------------------------
# Test: System Health with Partial Failures
# Validates: Requirements 13.1
# ---------------------------------------------------------------------------


class TestSystemHealthPartialFailure:
    """Test system health endpoint with partial service failures."""

    def test_system_health_all_services_healthy(self):
        """GET /api/admin/system → returns full health data when all services respond."""
        client = _client()

        from app.services.admin_health import (
            CloudWatchAlarm,
            CostEstimate,
            EcsStatus,
            SystemHealth,
        )

        mock_health = SystemHealth(
            ecs=EcsStatus(
                running_count=2,
                desired_count=2,
                pending_count=0,
                health_status="healthy",
            ),
            alarms=[
                CloudWatchAlarm(
                    alarm_name="HighCPU",
                    state="OK",
                    reason="Threshold not exceeded",
                ),
                CloudWatchAlarm(
                    alarm_name="ErrorRate",
                    state="ALARM",
                    reason="Error rate above 5%",
                ),
            ],
            cost_estimate=CostEstimate(
                current_month_usd=45.67,
                data_timestamp="2024-06-15T10:00:00+00:00",
            ),
            warnings=[],
        )

        with patch("app.routers.admin.get_system_health", return_value=mock_health):
            resp = client.get("/api/admin/system")

        assert resp.status_code == 200
        body = resp.json()
        assert body["ecs"]["running_count"] == 2
        assert body["ecs"]["health_status"] == "healthy"
        assert len(body["alarms"]) == 2
        assert body["alarms"][1]["state"] == "ALARM"
        assert body["cost_estimate"]["current_month_usd"] == 45.67
        assert body["warnings"] == []

    def test_system_health_partial_service_failure(self):
        """GET /api/admin/system with one service failing → returns partial data + warning."""
        client = _client()

        from app.services.admin_health import (
            CloudWatchAlarm,
            EcsStatus,
            SystemHealth,
        )

        # ECS unreachable, CloudWatch works, Cost Explorer fails
        mock_health = SystemHealth(
            ecs=EcsStatus(
                running_count=0,
                desired_count=0,
                pending_count=0,
                health_status="unreachable",
            ),
            alarms=[
                CloudWatchAlarm(
                    alarm_name="HighCPU",
                    state="OK",
                    reason="Threshold not exceeded",
                ),
            ],
            cost_estimate=None,
            warnings=[
                "ECS service could not be queried: connection timeout",
                "Cost Explorer could not be queried: access denied",
            ],
        )

        with patch("app.routers.admin.get_system_health", return_value=mock_health):
            resp = client.get("/api/admin/system")

        assert resp.status_code == 200
        body = resp.json()
        # ECS reports unreachable but endpoint still returns 200
        assert body["ecs"]["health_status"] == "unreachable"
        # CloudWatch data is still present
        assert len(body["alarms"]) == 1
        assert body["alarms"][0]["state"] == "OK"
        # Cost estimate is None due to failure
        assert body["cost_estimate"] is None
        # Warnings identify failed services
        assert len(body["warnings"]) == 2
        assert "ECS" in body["warnings"][0]
        assert "Cost Explorer" in body["warnings"][1]
