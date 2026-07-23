"""Unit tests for backend/app/services/admin_users.py — get_user_detail."""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.services.admin_users import (
    MonthlyUsage,
    TranscriptSessionSummary,
    UserDetail,
    get_user_detail,
    _detect_identity_provider,
    _get_last_n_months,
)


# ---------------------------------------------------------------------------
# Helper: identity provider detection
# ---------------------------------------------------------------------------


class TestDetectIdentityProvider:
    def test_native_uuid_username(self):
        assert _detect_identity_provider("abc123-def456") == "native"

    def test_native_email_username(self):
        assert _detect_identity_provider("user@example.com") == "native"

    def test_google_federated(self):
        assert _detect_identity_provider("Google_12345") == "Google"

    def test_facebook_federated(self):
        assert _detect_identity_provider("Facebook_67890") == "Facebook"

    def test_unknown_prefix(self):
        # An underscore-containing username with unknown prefix is "native"
        assert _detect_identity_provider("SomeOther_12345") == "native"


# ---------------------------------------------------------------------------
# Helper: last N months
# ---------------------------------------------------------------------------


class TestGetLastNMonths:
    def test_returns_correct_count(self):
        months = _get_last_n_months(3)
        assert len(months) <= 3
        assert len(months) >= 1  # At least current month

    def test_most_recent_first(self):
        months = _get_last_n_months(3)
        # First month should be >= all others (most recent)
        assert months[0] >= months[-1]


# ---------------------------------------------------------------------------
# get_user_detail — success path
# ---------------------------------------------------------------------------


class TestGetUserDetailSuccess:
    """Test get_user_detail with mocked Cognito and DynamoDB."""

    @patch("app.services.admin_users.boto3")
    @patch("app.services.admin_users.get_settings")
    def test_returns_user_detail(self, mock_settings, mock_boto3):
        # Setup settings
        settings = MagicMock()
        settings.aws_region = "us-east-1"
        settings.cognito_user_pool_id = "us-east-1_testPool"
        mock_settings.return_value = settings

        # Setup Cognito mock
        cognito_client = MagicMock()
        cognito_client.admin_get_user.return_value = {
            "Username": "testuser123",
            "Enabled": True,
            "UserCreateDate": datetime.datetime(2024, 1, 15, 10, 0, 0),
            "UserAttributes": [
                {"Name": "email", "Value": "test@example.com"},
                {"Name": "sub", "Value": "sub-123"},
            ],
        }

        # Setup DynamoDB resource mock (usage table)
        usage_table = MagicMock()
        usage_table.get_item.side_effect = [
            # PROFILE item
            {"Item": {"tier": "pro", "subscription_status": "active"}},
            # Month 1 (current)
            {"Item": {"sessions_used": 5, "minutes_used": 120}},
            # Month 2
            {"Item": {"sessions_used": 3, "minutes_used": 90}},
            # Month 3
            {"Item": {"sessions_used": 2, "minutes_used": 45}},
        ]
        dynamodb_resource = MagicMock()
        dynamodb_resource.Table.return_value = usage_table

        # Setup DynamoDB client mock (transcript history)
        dynamodb_client = MagicMock()
        dynamodb_client.query.return_value = {
            "Items": [
                {
                    "session_id": {"S": "sess-001"},
                    "created_at": {"S": "2024-06-01T10:00:00+00:00"},
                    "segment_count": {"N": "15"},
                    "duration_seconds": {"N": "300"},
                },
                {
                    "session_id": {"S": "sess-002"},
                    "created_at": {"S": "2024-05-28T14:30:00+00:00"},
                    "segment_count": {"N": "8"},
                },
            ],
        }

        # Wire up boto3 mocks
        def client_side_effect(service, **kwargs):
            if service == "cognito-idp":
                return cognito_client
            if service == "dynamodb":
                return dynamodb_client
            return MagicMock()

        mock_boto3.client.side_effect = client_side_effect
        mock_boto3.resource.return_value = dynamodb_resource

        # Call function
        result = get_user_detail("testuser123")

        # Assertions
        assert isinstance(result, UserDetail)
        assert result.profile.email == "test@example.com"
        assert result.profile.tier == "pro"
        assert result.profile.status == "enabled"
        assert result.profile.identity_provider == "native"
        assert result.has_stripe_subscription is True
        assert len(result.usage_history) >= 1
        assert result.usage_history[0].sessions_used == 5
        assert result.usage_history[0].minutes_used == 120
        assert len(result.transcript_sessions) == 2
        assert result.transcript_sessions[0].session_id == "sess-001"
        assert result.transcript_sessions[0].duration_seconds == 300
        assert result.transcript_sessions[1].duration_seconds is None
        assert result.audit_log == []  # Phase 2


# ---------------------------------------------------------------------------
# get_user_detail — user not found
# ---------------------------------------------------------------------------


class TestGetUserDetailNotFound:
    """Test 404 when Cognito user doesn't exist."""

    @patch("app.services.admin_users.boto3")
    @patch("app.services.admin_users.get_settings")
    def test_raises_404_on_user_not_found(self, mock_settings, mock_boto3):
        settings = MagicMock()
        settings.aws_region = "us-east-1"
        settings.cognito_user_pool_id = "us-east-1_testPool"
        mock_settings.return_value = settings

        from botocore.exceptions import ClientError

        cognito_client = MagicMock()
        cognito_client.admin_get_user.side_effect = ClientError(
            {"Error": {"Code": "UserNotFoundException", "Message": "User does not exist."}},
            "AdminGetUser",
        )
        mock_boto3.client.return_value = cognito_client

        with pytest.raises(HTTPException) as exc_info:
            get_user_detail("nonexistent_user")

        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.detail.lower()


# ---------------------------------------------------------------------------
# get_user_detail — Cognito error (non-404)
# ---------------------------------------------------------------------------


class TestGetUserDetailCognitoError:
    """Test 502 when Cognito has an unexpected error."""

    @patch("app.services.admin_users.boto3")
    @patch("app.services.admin_users.get_settings")
    def test_raises_502_on_cognito_error(self, mock_settings, mock_boto3):
        settings = MagicMock()
        settings.aws_region = "us-east-1"
        settings.cognito_user_pool_id = "us-east-1_testPool"
        mock_settings.return_value = settings

        from botocore.exceptions import ClientError

        cognito_client = MagicMock()
        cognito_client.admin_get_user.side_effect = ClientError(
            {"Error": {"Code": "InternalErrorException", "Message": "Internal error."}},
            "AdminGetUser",
        )
        mock_boto3.client.return_value = cognito_client

        with pytest.raises(HTTPException) as exc_info:
            get_user_detail("someuser")

        assert exc_info.value.status_code == 502


# ---------------------------------------------------------------------------
# get_user_detail — graceful degradation
# ---------------------------------------------------------------------------


class TestGetUserDetailGracefulDegradation:
    """Test graceful degradation when DynamoDB is unreachable."""

    @patch("app.services.admin_users.boto3")
    @patch("app.services.admin_users.get_settings")
    def test_returns_partial_data_when_dynamodb_fails(self, mock_settings, mock_boto3):
        settings = MagicMock()
        settings.aws_region = "us-east-1"
        settings.cognito_user_pool_id = "us-east-1_testPool"
        mock_settings.return_value = settings

        # Cognito succeeds
        cognito_client = MagicMock()
        cognito_client.admin_get_user.return_value = {
            "Username": "testuser",
            "Enabled": True,
            "UserCreateDate": datetime.datetime(2024, 3, 1, 8, 0, 0),
            "UserAttributes": [
                {"Name": "email", "Value": "user@test.com"},
            ],
        }

        # DynamoDB resource fails
        from botocore.exceptions import ClientError

        usage_table = MagicMock()
        usage_table.get_item.side_effect = ClientError(
            {"Error": {"Code": "ServiceUnavailableException", "Message": "DynamoDB down"}},
            "GetItem",
        )
        dynamodb_resource = MagicMock()
        dynamodb_resource.Table.return_value = usage_table

        # DynamoDB client fails (transcript history)
        dynamodb_client = MagicMock()
        dynamodb_client.query.side_effect = ClientError(
            {"Error": {"Code": "ServiceUnavailableException", "Message": "DynamoDB down"}},
            "Query",
        )

        def client_side_effect(service, **kwargs):
            if service == "cognito-idp":
                return cognito_client
            if service == "dynamodb":
                return dynamodb_client
            return MagicMock()

        mock_boto3.client.side_effect = client_side_effect
        mock_boto3.resource.return_value = dynamodb_resource

        # Should NOT raise — graceful degradation
        result = get_user_detail("testuser")

        assert result.profile.email == "user@test.com"
        assert result.profile.tier == "free"  # default
        assert result.has_stripe_subscription is False
        # Usage history should have entries (with zeros due to fallback)
        assert len(result.usage_history) >= 1
        for usage in result.usage_history:
            assert usage.sessions_used == 0
            assert usage.minutes_used == 0
        # No transcript sessions (DynamoDB failed)
        assert result.transcript_sessions == []


# ---------------------------------------------------------------------------
# get_user_detail — federated user (Google)
# ---------------------------------------------------------------------------


class TestGetUserDetailFederated:
    """Test identity provider detection for federated users."""

    @patch("app.services.admin_users.boto3")
    @patch("app.services.admin_users.get_settings")
    def test_detects_google_provider(self, mock_settings, mock_boto3):
        settings = MagicMock()
        settings.aws_region = "us-east-1"
        settings.cognito_user_pool_id = "us-east-1_testPool"
        mock_settings.return_value = settings

        cognito_client = MagicMock()
        cognito_client.admin_get_user.return_value = {
            "Username": "Google_abc123",
            "Enabled": True,
            "UserCreateDate": datetime.datetime(2024, 2, 1),
            "UserAttributes": [
                {"Name": "email", "Value": "guser@gmail.com"},
            ],
        }

        usage_table = MagicMock()
        usage_table.get_item.return_value = {}  # No profile/usage items
        dynamodb_resource = MagicMock()
        dynamodb_resource.Table.return_value = usage_table

        dynamodb_client = MagicMock()
        dynamodb_client.query.return_value = {"Items": []}

        def client_side_effect(service, **kwargs):
            if service == "cognito-idp":
                return cognito_client
            if service == "dynamodb":
                return dynamodb_client
            return MagicMock()

        mock_boto3.client.side_effect = client_side_effect
        mock_boto3.resource.return_value = dynamodb_resource

        result = get_user_detail("Google_abc123")

        assert result.profile.identity_provider == "Google"
        assert result.profile.email == "guser@gmail.com"
