"""Unit tests for backend/app/services/admin_users.py — list_users function.

Tests cover:
- Basic listing with mocked Cognito and DynamoDB
- Pagination edge cases (empty set, single page, last page partial)
- Email search (case-insensitive substring)
- Tier and status filters
- Combined filters (tier + status + email simultaneously)
- Graceful degradation when Cognito or DynamoDB is unreachable

Requirements: 2.1, 2.2, 3.1, 3.2, 3.3, 8.5, 16.1
"""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from app.services.admin_users import (
    PaginatedUserList,
    list_users,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_cognito_user(
    username: str,
    email: str,
    enabled: bool = True,
    created: datetime.datetime | None = None,
    sub: str | None = None,
) -> dict:
    """Build a mock Cognito user dict."""
    attrs = [{"Name": "email", "Value": email}]
    if sub:
        attrs.append({"Name": "sub", "Value": sub})
    return {
        "Username": username,
        "Enabled": enabled,
        "UserCreateDate": created or datetime.datetime(2024, 1, 1, 0, 0, 0),
        "UserLastModifiedDate": datetime.datetime(2024, 6, 1, 0, 0, 0),
        "Attributes": attrs,
    }


def _make_usage_item(user_id: str, tier: str = "free", sessions: int = 0, minutes: int = 0) -> dict:
    """Build mock DynamoDB usage table items for a user (profile + month)."""
    return {
        "profile": {"pk": f"USER#{user_id}", "sk": "PROFILE", "tier": tier},
        "month": {"pk": f"USER#{user_id}", "sessions_used": sessions, "minutes_used": minutes},
    }


def _setup_mocks(mock_settings, mock_boto3, cognito_users, usage_by_user):
    """Wire up settings and boto3 mocks for list_users tests."""
    settings = MagicMock()
    settings.aws_region = "us-east-1"
    settings.cognito_user_pool_id = "us-east-1_testPool"
    mock_settings.return_value = settings

    # Cognito client mock
    cognito_client = MagicMock()
    cognito_client.list_users.return_value = {
        "Users": cognito_users,
    }
    mock_boto3.client.return_value = cognito_client

    # DynamoDB resource mock (usage table scan)
    usage_table = MagicMock()

    # Build scan response items from usage_by_user dict
    items = []
    for user_id, bucket in usage_by_user.items():
        if bucket.get("profile"):
            items.append(bucket["profile"])
        if bucket.get("month"):
            items.append(bucket["month"])

    usage_table.scan.return_value = {"Items": items}
    dynamodb_resource = MagicMock()
    dynamodb_resource.Table.return_value = usage_table
    mock_boto3.resource.return_value = dynamodb_resource

    return settings, cognito_client, usage_table


# ---------------------------------------------------------------------------
# Test: Basic listing
# ---------------------------------------------------------------------------


class TestListUsersBasic:
    """Test list_users with valid mocked Cognito and DynamoDB responses."""

    @patch("app.services.admin_users.boto3")
    @patch("app.services.admin_users.get_settings")
    def test_basic_listing_returns_paginated_result(self, mock_settings, mock_boto3):
        cognito_users = [
            _make_cognito_user("user1", "alice@example.com", sub="sub-1"),
            _make_cognito_user("user2", "bob@example.com", sub="sub-2"),
        ]
        usage_data = {
            "sub-1": _make_usage_item("sub-1", tier="pro", sessions=5, minutes=120),
            "sub-2": _make_usage_item("sub-2", tier="free", sessions=2, minutes=30),
        }
        _setup_mocks(mock_settings, mock_boto3, cognito_users, usage_data)

        result = list_users(page=1, page_size=20)

        assert isinstance(result, PaginatedUserList)
        assert len(result.users) == 2
        assert result.page == 1
        assert result.page_size == 20
        assert result.total_pages == 1
        assert result.total_users == 2
        assert result.stats.total_users == 2
        assert result.stats.pro_count == 1
        assert result.stats.free_count == 1


# ---------------------------------------------------------------------------
# Test: Pagination edge cases
# ---------------------------------------------------------------------------


class TestListUsersPagination:
    """Test pagination edge cases: empty set, single page, last page partial."""

    @patch("app.services.admin_users.boto3")
    @patch("app.services.admin_users.get_settings")
    def test_empty_user_set(self, mock_settings, mock_boto3):
        """Empty set → page=1, total_pages=1, users=[]."""
        _setup_mocks(mock_settings, mock_boto3, [], {})

        result = list_users(page=1, page_size=20)

        assert result.users == []
        assert result.page == 1
        assert result.total_pages == 1
        assert result.total_users == 0

    @patch("app.services.admin_users.boto3")
    @patch("app.services.admin_users.get_settings")
    def test_single_page_of_results(self, mock_settings, mock_boto3):
        """5 users with page_size=20 → 1 page with 5 users."""
        cognito_users = [
            _make_cognito_user(f"user{i}", f"user{i}@example.com", sub=f"sub-{i}")
            for i in range(5)
        ]
        usage_data = {
            f"sub-{i}": _make_usage_item(f"sub-{i}", tier="free")
            for i in range(5)
        }
        _setup_mocks(mock_settings, mock_boto3, cognito_users, usage_data)

        result = list_users(page=1, page_size=20)

        assert len(result.users) == 5
        assert result.total_pages == 1
        assert result.total_users == 5

    @patch("app.services.admin_users.boto3")
    @patch("app.services.admin_users.get_settings")
    def test_multi_page_last_page_partial(self, mock_settings, mock_boto3):
        """25 users with page_size=10 → 3 pages, page 3 has 5 users."""
        cognito_users = [
            _make_cognito_user(f"user{i:02d}", f"user{i:02d}@example.com", sub=f"sub-{i}")
            for i in range(25)
        ]
        usage_data = {
            f"sub-{i}": _make_usage_item(f"sub-{i}", tier="free")
            for i in range(25)
        }
        _setup_mocks(mock_settings, mock_boto3, cognito_users, usage_data)

        # Page 1
        result_p1 = list_users(page=1, page_size=10)
        assert len(result_p1.users) == 10
        assert result_p1.total_pages == 3
        assert result_p1.total_users == 25

        # Page 3 (last page, partial)
        result_p3 = list_users(page=3, page_size=10)
        assert len(result_p3.users) == 5
        assert result_p3.page == 3
        assert result_p3.total_pages == 3


# ---------------------------------------------------------------------------
# Test: Email search (case-insensitive)
# ---------------------------------------------------------------------------


class TestListUsersEmailSearch:
    """Test email search filtering (case-insensitive substring match)."""

    @patch("app.services.admin_users.boto3")
    @patch("app.services.admin_users.get_settings")
    def test_case_insensitive_email_search(self, mock_settings, mock_boto3):
        """Searching 'ADMIN' matches 'admin@example.com'."""
        cognito_users = [
            _make_cognito_user("user1", "admin@example.com", sub="sub-1"),
            _make_cognito_user("user2", "bob@example.com", sub="sub-2"),
            _make_cognito_user("user3", "Admin_User@test.com", sub="sub-3"),
        ]
        usage_data = {
            f"sub-{i}": _make_usage_item(f"sub-{i}", tier="free")
            for i in range(1, 4)
        }
        _setup_mocks(mock_settings, mock_boto3, cognito_users, usage_data)

        result = list_users(search_email="ADMIN")

        assert result.total_users == 2
        emails = [u.email for u in result.users]
        assert "admin@example.com" in emails
        assert "Admin_User@test.com" in emails
        assert "bob@example.com" not in emails


# ---------------------------------------------------------------------------
# Test: Tier filter
# ---------------------------------------------------------------------------


class TestListUsersTierFilter:
    """Test tier filter returns only users with matching tier."""

    @patch("app.services.admin_users.boto3")
    @patch("app.services.admin_users.get_settings")
    def test_tier_filter_pro(self, mock_settings, mock_boto3):
        """filter_tier='pro' returns only pro users."""
        cognito_users = [
            _make_cognito_user("user1", "pro_user@test.com", sub="sub-1"),
            _make_cognito_user("user2", "free_user@test.com", sub="sub-2"),
            _make_cognito_user("user3", "business_user@test.com", sub="sub-3"),
        ]
        usage_data = {
            "sub-1": _make_usage_item("sub-1", tier="pro"),
            "sub-2": _make_usage_item("sub-2", tier="free"),
            "sub-3": _make_usage_item("sub-3", tier="business"),
        }
        _setup_mocks(mock_settings, mock_boto3, cognito_users, usage_data)

        result = list_users(filter_tier="pro")

        assert result.total_users == 1
        assert result.users[0].tier == "pro"
        assert result.users[0].email == "pro_user@test.com"
        assert result.stats.pro_count == 1
        assert result.stats.free_count == 0


# ---------------------------------------------------------------------------
# Test: Status filter
# ---------------------------------------------------------------------------


class TestListUsersStatusFilter:
    """Test status filter returns only users with matching status."""

    @patch("app.services.admin_users.boto3")
    @patch("app.services.admin_users.get_settings")
    def test_status_filter_disabled(self, mock_settings, mock_boto3):
        """filter_status='disabled' returns only disabled users."""
        cognito_users = [
            _make_cognito_user("user1", "active@test.com", enabled=True, sub="sub-1"),
            _make_cognito_user("user2", "banned@test.com", enabled=False, sub="sub-2"),
            _make_cognito_user("user3", "also_active@test.com", enabled=True, sub="sub-3"),
        ]
        usage_data = {
            f"sub-{i}": _make_usage_item(f"sub-{i}", tier="free")
            for i in range(1, 4)
        }
        _setup_mocks(mock_settings, mock_boto3, cognito_users, usage_data)

        result = list_users(filter_status="disabled")

        assert result.total_users == 1
        assert result.users[0].email == "banned@test.com"
        assert result.users[0].status == "disabled"


# ---------------------------------------------------------------------------
# Test: Combined filters
# ---------------------------------------------------------------------------


class TestListUsersCombinedFilters:
    """Test combined filters (tier + status + email simultaneously)."""

    @patch("app.services.admin_users.boto3")
    @patch("app.services.admin_users.get_settings")
    def test_combined_filters(self, mock_settings, mock_boto3):
        """tier=pro + status=enabled + email='test' filters correctly."""
        cognito_users = [
            _make_cognito_user("u1", "test_pro_active@x.com", enabled=True, sub="sub-1"),
            _make_cognito_user("u2", "test_pro_disabled@x.com", enabled=False, sub="sub-2"),
            _make_cognito_user("u3", "test_free_active@x.com", enabled=True, sub="sub-3"),
            _make_cognito_user("u4", "other_pro_active@x.com", enabled=True, sub="sub-4"),
            _make_cognito_user("u5", "test_pro_active2@x.com", enabled=True, sub="sub-5"),
        ]
        usage_data = {
            "sub-1": _make_usage_item("sub-1", tier="pro"),
            "sub-2": _make_usage_item("sub-2", tier="pro"),
            "sub-3": _make_usage_item("sub-3", tier="free"),
            "sub-4": _make_usage_item("sub-4", tier="pro"),
            "sub-5": _make_usage_item("sub-5", tier="pro"),
        }
        _setup_mocks(mock_settings, mock_boto3, cognito_users, usage_data)

        result = list_users(filter_tier="pro", filter_status="enabled", search_email="test")

        # Only users with tier=pro AND status=enabled AND "test" in email
        assert result.total_users == 2
        emails = sorted([u.email for u in result.users])
        assert emails == ["test_pro_active2@x.com", "test_pro_active@x.com"]


# ---------------------------------------------------------------------------
# Test: Graceful degradation — Cognito fails
# ---------------------------------------------------------------------------


class TestListUsersCognitoFailure:
    """Test graceful degradation when Cognito is unreachable."""

    @patch("app.services.admin_users.boto3")
    @patch("app.services.admin_users.get_settings")
    def test_cognito_failure_returns_dynamodb_only_data(self, mock_settings, mock_boto3):
        """When Cognito fails, returns partial data from DynamoDB."""
        settings = MagicMock()
        settings.aws_region = "us-east-1"
        settings.cognito_user_pool_id = "us-east-1_testPool"
        mock_settings.return_value = settings

        # Cognito client raises exception
        cognito_client = MagicMock()
        cognito_client.list_users.side_effect = ClientError(
            {"Error": {"Code": "InternalErrorException", "Message": "Service down"}},
            "ListUsers",
        )
        mock_boto3.client.return_value = cognito_client

        # DynamoDB has some user data
        usage_table = MagicMock()
        usage_table.scan.return_value = {
            "Items": [
                {"pk": "USER#dynamo-user-1", "sk": "PROFILE", "tier": "pro", "email": "dynamo@test.com"},
            ]
        }
        dynamodb_resource = MagicMock()
        dynamodb_resource.Table.return_value = usage_table
        mock_boto3.resource.return_value = dynamodb_resource

        # Should NOT raise — returns DynamoDB-only data
        result = list_users()

        assert isinstance(result, PaginatedUserList)
        # DynamoDB user should appear (defensive fallback path in _merge_user_data)
        assert result.total_users >= 1


# ---------------------------------------------------------------------------
# Test: Graceful degradation — DynamoDB fails
# ---------------------------------------------------------------------------


class TestListUsersDynamoDBFailure:
    """Test graceful degradation when DynamoDB is unreachable."""

    @patch("app.services.admin_users.boto3")
    @patch("app.services.admin_users.get_settings")
    def test_dynamodb_failure_returns_cognito_data_with_default_tier(self, mock_settings, mock_boto3):
        """When DynamoDB fails, returns Cognito data with default tier."""
        settings = MagicMock()
        settings.aws_region = "us-east-1"
        settings.cognito_user_pool_id = "us-east-1_testPool"
        mock_settings.return_value = settings

        # Cognito succeeds
        cognito_client = MagicMock()
        cognito_client.list_users.return_value = {
            "Users": [
                _make_cognito_user("user1", "alice@test.com", sub="sub-1"),
                _make_cognito_user("user2", "bob@test.com", sub="sub-2"),
            ]
        }
        mock_boto3.client.return_value = cognito_client

        # DynamoDB fails
        usage_table = MagicMock()
        usage_table.scan.side_effect = ClientError(
            {"Error": {"Code": "ServiceUnavailableException", "Message": "DynamoDB down"}},
            "Scan",
        )
        dynamodb_resource = MagicMock()
        dynamodb_resource.Table.return_value = usage_table
        mock_boto3.resource.return_value = dynamodb_resource

        # Should NOT raise — returns Cognito data with defaults
        result = list_users()

        assert isinstance(result, PaginatedUserList)
        assert result.total_users == 2
        # All users should have default tier since DynamoDB failed
        for user in result.users:
            assert user.tier == "free"  # DEFAULT_TIER
            assert user.sessions_used == 0
            assert user.minutes_used == 0
