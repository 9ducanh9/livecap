"""Unit tests for admin mutation and audit endpoints.

Tests the service-level mutation functions (disable_user, enable_user,
reset_password, change_tier) with mocked Cognito and DynamoDB calls, plus
router-level integration tests via FastAPI TestClient.

Validates: Requirements 4.1, 4.2, 4.4, 5.1, 5.3, 5.5, 6.1, 6.3, 6.6, 7.1, 7.5
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.routers.admin import router
from app.services.admin_users import (
    TierChangeResult,
    UserActionResult,
    UserRecord,
    change_tier,
    delete_user,
    disable_user,
    enable_user,
    reset_password,
)
from app.services.auth import AuthenticatedUser, require_admin_user


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _mock_settings():
    """Return a mock Settings object with test defaults."""
    settings = MagicMock()
    settings.aws_region = "us-east-1"
    settings.cognito_user_pool_id = "us-east-1_TestPool"
    return settings


def _cognito_not_found_error():
    """Build a ClientError simulating UserNotFoundException."""
    return ClientError(
        {"Error": {"Code": "UserNotFoundException", "Message": "User not found"}},
        "AdminDisableUser",
    )


def _client(with_admin_override: bool = True) -> TestClient:
    """Create a test client for the admin router."""
    app = FastAPI()
    app.include_router(router)
    if with_admin_override:
        app.dependency_overrides[require_admin_user] = lambda: AuthenticatedUser(
            "admin-1", "admin-1", "admin@example.com"
        )
    return TestClient(app)


# ---------------------------------------------------------------------------
# Service-level tests: disable_user
# ---------------------------------------------------------------------------


class TestDisableUser:
    """Tests for disable_user service function."""

    @patch("app.services.admin_users.admin_audit")
    @patch("app.services.admin_users.boto3")
    @patch("app.services.admin_users.get_settings")
    def test_disable_user_success(self, mock_get_settings, mock_boto3, mock_audit):
        """Validates Req 4.1: AdminDisableUser + audit → returns success."""
        mock_get_settings.return_value = _mock_settings()
        mock_cognito = MagicMock()
        mock_boto3.client.return_value = mock_cognito

        result = disable_user("testuser", "admin-1")

        assert isinstance(result, UserActionResult)
        assert result.success is True
        assert "disabled" in result.message.lower()
        mock_cognito.admin_disable_user.assert_called_once_with(
            UserPoolId="us-east-1_TestPool",
            Username="testuser",
        )
        mock_audit.record_action.assert_called_once_with(
            admin_user_id="admin-1",
            target_user_id="testuser",
            action_type="disable",
            previous_value="enabled",
            new_value="disabled",
        )

    @patch("app.services.admin_users.admin_audit")
    @patch("app.services.admin_users.boto3")
    @patch("app.services.admin_users.get_settings")
    def test_disable_user_not_found(self, mock_get_settings, mock_boto3, mock_audit):
        """Validates Req 4.4: UserNotFoundException → raises 404."""
        mock_get_settings.return_value = _mock_settings()
        mock_cognito = MagicMock()
        mock_cognito.admin_disable_user.side_effect = _cognito_not_found_error()
        mock_boto3.client.return_value = mock_cognito

        with pytest.raises(HTTPException) as exc_info:
            disable_user("nonexistent", "admin-1")

        assert exc_info.value.status_code == 404
        mock_audit.record_action.assert_not_called()


# ---------------------------------------------------------------------------
# Service-level tests: delete_user
# ---------------------------------------------------------------------------


def _admin_get_user_response(email: str = "target@example.com") -> dict:
    return {"UserAttributes": [{"Name": "email", "Value": email}]}


class TestDeleteUser:
    """Tests for delete_user service function."""

    @patch("app.services.admin_users.admin_audit")
    @patch("app.services.admin_users.boto3")
    @patch("app.services.admin_users.get_settings")
    def test_delete_user_success(self, mock_get_settings, mock_boto3, mock_audit):
        """AdminGetUser (for email) + AdminDeleteUser + audit -> success,
        and the usage-table PROFILE/MONTH rows get best-effort cleaned up."""
        mock_get_settings.return_value = _mock_settings()
        mock_cognito = MagicMock()
        mock_cognito.admin_get_user.return_value = _admin_get_user_response()
        mock_boto3.client.return_value = mock_cognito
        mock_usage_table = MagicMock()
        mock_boto3.resource.return_value.Table.return_value = mock_usage_table

        result = delete_user("testuser", "admin-1")

        assert isinstance(result, UserActionResult)
        assert result.success is True
        assert "target@example.com" in result.message
        mock_cognito.admin_delete_user.assert_called_once_with(
            UserPoolId="us-east-1_TestPool",
            Username="testuser",
        )
        mock_usage_table.delete_item.assert_any_call(
            Key={"pk": "USER#testuser", "sk": "PROFILE"}
        )
        mock_audit.record_action.assert_called_once_with(
            admin_user_id="admin-1",
            target_user_id="testuser",
            action_type="delete",
            previous_value="target@example.com",
            new_value="deleted",
        )

    @patch("app.services.admin_users.admin_audit")
    @patch("app.services.admin_users.boto3")
    @patch("app.services.admin_users.get_settings")
    def test_delete_user_already_gone_still_cleans_up(
        self, mock_get_settings, mock_boto3, mock_audit
    ):
        """AdminGetUser raising UserNotFoundException means Cognito already
        has nothing to delete, not an error: still runs the DynamoDB cleanup
        and audit (idempotent), skipping AdminDeleteUser rather than 404ing
        and leaving orphaned usage-table rows -- the exact bug hit live: a
        ghost admin-panel row (Cognito gone, DynamoDB rows orphaned) that a
        404-and-stop delete could never actually clear."""
        mock_get_settings.return_value = _mock_settings()
        mock_cognito = MagicMock()
        mock_cognito.admin_get_user.side_effect = ClientError(
            {"Error": {"Code": "UserNotFoundException", "Message": "User not found"}},
            "AdminGetUser",
        )
        mock_boto3.client.return_value = mock_cognito
        mock_usage_table = MagicMock()
        mock_boto3.resource.return_value.Table.return_value = mock_usage_table

        result = delete_user("orphaned-user", "admin-1")

        assert isinstance(result, UserActionResult)
        assert result.success is True
        mock_cognito.admin_delete_user.assert_not_called()
        mock_usage_table.delete_item.assert_any_call(
            Key={"pk": "USER#orphaned-user", "sk": "PROFILE"}
        )
        mock_audit.record_action.assert_called_once_with(
            admin_user_id="admin-1",
            target_user_id="orphaned-user",
            action_type="delete",
            previous_value="orphaned-user",
            new_value="deleted",
        )

    @patch("app.services.admin_users.admin_audit")
    @patch("app.services.admin_users.boto3")
    @patch("app.services.admin_users.get_settings")
    def test_delete_user_audit_failure_still_deleted(self, mock_get_settings, mock_boto3, mock_audit):
        """Deletion can't be rolled back: if audit fails afterward, the user
        is still gone and the caller gets a 500 (matching reset_password's
        convention), not a silent rollback that can't actually happen."""
        mock_get_settings.return_value = _mock_settings()
        mock_cognito = MagicMock()
        mock_cognito.admin_get_user.return_value = _admin_get_user_response()
        mock_boto3.client.return_value = mock_cognito
        mock_audit.record_action.side_effect = RuntimeError("dynamo down")

        with pytest.raises(HTTPException) as exc_info:
            delete_user("testuser", "admin-1")

        assert exc_info.value.status_code == 500
        mock_cognito.admin_delete_user.assert_called_once()


# ---------------------------------------------------------------------------
# Service-level tests: enable_user
# ---------------------------------------------------------------------------


class TestEnableUser:
    """Tests for enable_user service function."""

    @patch("app.services.admin_users.admin_audit")
    @patch("app.services.admin_users.boto3")
    @patch("app.services.admin_users.get_settings")
    def test_enable_user_success(self, mock_get_settings, mock_boto3, mock_audit):
        """Validates Req 4.2: AdminEnableUser + audit → returns success."""
        mock_get_settings.return_value = _mock_settings()
        mock_cognito = MagicMock()
        mock_boto3.client.return_value = mock_cognito

        result = enable_user("testuser", "admin-1")

        assert isinstance(result, UserActionResult)
        assert result.success is True
        assert "enabled" in result.message.lower()
        mock_cognito.admin_enable_user.assert_called_once_with(
            UserPoolId="us-east-1_TestPool",
            Username="testuser",
        )
        mock_audit.record_action.assert_called_once_with(
            admin_user_id="admin-1",
            target_user_id="testuser",
            action_type="enable",
            previous_value="disabled",
            new_value="enabled",
        )


# ---------------------------------------------------------------------------
# Service-level tests: reset_password
# ---------------------------------------------------------------------------


class TestResetPassword:
    """Tests for reset_password service function."""

    @patch("app.services.admin_users.admin_audit")
    @patch("app.services.admin_users.boto3")
    @patch("app.services.admin_users.get_settings")
    def test_reset_password_success(self, mock_get_settings, mock_boto3, mock_audit):
        """Validates Req 5.1: Cognito reset → returns success."""
        mock_get_settings.return_value = _mock_settings()
        mock_cognito = MagicMock()
        mock_boto3.client.return_value = mock_cognito

        result = reset_password("nativeuser", "admin-1")

        assert isinstance(result, UserActionResult)
        assert result.success is True
        assert "reset" in result.message.lower() or "sent" in result.message.lower()
        mock_cognito.admin_reset_user_password.assert_called_once()

    def test_reset_password_federated_rejected(self):
        """Validates Req 5.5: federated username → returns success=False message."""
        result = reset_password("Google_xyz123", "admin-1")

        assert isinstance(result, UserActionResult)
        assert result.success is False
        assert "federated" in result.message.lower() or "not applicable" in result.message.lower()


# ---------------------------------------------------------------------------
# Service-level tests: change_tier
# ---------------------------------------------------------------------------


class TestChangeTier:
    """Tests for change_tier service function."""

    @patch("app.services.admin_users.admin_audit")
    @patch("app.services.admin_users.boto3")
    @patch("app.services.admin_users.get_settings")
    def test_change_tier_valid(self, mock_get_settings, mock_boto3, mock_audit):
        """Validates Req 6.1: DynamoDB update + audit → returns TierChangeResult."""
        mock_get_settings.return_value = _mock_settings()

        # Mock DynamoDB resource and table
        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            "Item": {"tier": "free", "email": "test@example.com", "subscription_status": None}
        }
        mock_table.update_item.return_value = {}
        mock_dynamodb = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        mock_boto3.resource.return_value = mock_dynamodb

        result = change_tier("testuser", "pro", "admin-1")

        assert isinstance(result, TierChangeResult)
        assert result.success is True
        assert "pro" in result.message.lower()
        assert result.updated_user is not None
        assert result.updated_user.tier == "pro"
        mock_audit.record_action.assert_called_once_with(
            admin_user_id="admin-1",
            target_user_id="testuser",
            action_type="change_tier",
            previous_value="free",
            new_value="pro",
        )

    def test_change_tier_invalid(self):
        """Validates Req 6.3: invalid tier → raises HTTPException(422)."""
        with pytest.raises(HTTPException) as exc_info:
            change_tier("testuser", "platinum", "admin-1")

        assert exc_info.value.status_code == 422
        assert "invalid" in exc_info.value.detail.lower() or "platinum" in exc_info.value.detail.lower()

    @patch("app.services.admin_users.admin_audit")
    @patch("app.services.admin_users.boto3")
    @patch("app.services.admin_users.get_settings")
    def test_change_tier_stripe_warning(self, mock_get_settings, mock_boto3, mock_audit):
        """Validates Req 6.6: active subscription → warning in result."""
        mock_get_settings.return_value = _mock_settings()

        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            "Item": {
                "tier": "pro",
                "email": "test@example.com",
                "subscription_status": "active",
            }
        }
        mock_table.update_item.return_value = {}
        mock_dynamodb = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        mock_boto3.resource.return_value = mock_dynamodb

        result = change_tier("testuser", "business", "admin-1")

        assert isinstance(result, TierChangeResult)
        assert result.success is True
        assert result.warning is not None
        assert "stripe" in result.warning.lower()


# ---------------------------------------------------------------------------
# Service-level tests: audit log creation and rollback
# ---------------------------------------------------------------------------


class TestAuditLogging:
    """Tests for audit log creation and rollback behavior."""

    @patch("app.services.admin_users.admin_audit")
    @patch("app.services.admin_users.boto3")
    @patch("app.services.admin_users.get_settings")
    def test_audit_log_creation(self, mock_get_settings, mock_boto3, mock_audit):
        """Validates Req 7.1: record_action called with correct args after disable."""
        mock_get_settings.return_value = _mock_settings()
        mock_cognito = MagicMock()
        mock_boto3.client.return_value = mock_cognito

        disable_user("testuser", "admin-42")

        mock_audit.record_action.assert_called_once_with(
            admin_user_id="admin-42",
            target_user_id="testuser",
            action_type="disable",
            previous_value="enabled",
            new_value="disabled",
        )

    @patch("app.services.admin_users.admin_audit")
    @patch("app.services.admin_users.boto3")
    @patch("app.services.admin_users.get_settings")
    def test_audit_failure_rollback_disable(self, mock_get_settings, mock_boto3, mock_audit):
        """Validates Req 7.5: audit failure → re-enable called + HTTPException(500)."""
        mock_get_settings.return_value = _mock_settings()
        mock_cognito = MagicMock()
        mock_boto3.client.return_value = mock_cognito
        mock_audit.record_action.side_effect = RuntimeError("DynamoDB write failed")

        with pytest.raises(HTTPException) as exc_info:
            disable_user("testuser", "admin-1")

        assert exc_info.value.status_code == 500
        # Verify rollback: admin_enable_user was called to re-enable
        mock_cognito.admin_enable_user.assert_called_once_with(
            UserPoolId="us-east-1_TestPool",
            Username="testuser",
        )

    @patch("app.services.admin_users.admin_audit")
    @patch("app.services.admin_users.boto3")
    @patch("app.services.admin_users.get_settings")
    def test_audit_failure_rollback_tier(self, mock_get_settings, mock_boto3, mock_audit):
        """Validates Req 7.5: audit failure on tier change → tier reverted + HTTPException(500)."""
        mock_get_settings.return_value = _mock_settings()

        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            "Item": {"tier": "free", "email": "test@example.com", "subscription_status": None}
        }
        mock_table.update_item.return_value = {}
        mock_dynamodb = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        mock_boto3.resource.return_value = mock_dynamodb
        mock_audit.record_action.side_effect = RuntimeError("DynamoDB write failed")

        with pytest.raises(HTTPException) as exc_info:
            change_tier("testuser", "pro", "admin-1")

        assert exc_info.value.status_code == 500
        # Verify rollback: update_item was called twice (once for tier change, once for revert)
        assert mock_table.update_item.call_count == 2


# ---------------------------------------------------------------------------
# Router-level tests
# ---------------------------------------------------------------------------


class TestMutationRouterEndpoints:
    """Router-level tests using TestClient + dependency overrides."""

    @patch("app.services.admin_users.admin_audit")
    @patch("app.services.admin_users.boto3")
    @patch("app.services.admin_users.get_settings")
    def test_post_disable_returns_200(self, mock_get_settings, mock_boto3, mock_audit):
        """POST /api/admin/users/{username}/disable returns 200 on success."""
        mock_get_settings.return_value = _mock_settings()
        mock_cognito = MagicMock()
        mock_boto3.client.return_value = mock_cognito

        client = _client()
        resp = client.post("/api/admin/users/testuser/disable")

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True

    @patch("app.services.admin_users.admin_audit")
    @patch("app.services.admin_users.boto3")
    @patch("app.services.admin_users.get_settings")
    def test_post_change_tier_returns_200(self, mock_get_settings, mock_boto3, mock_audit):
        """POST /api/admin/users/{username}/change-tier returns 200 on success."""
        mock_get_settings.return_value = _mock_settings()

        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            "Item": {"tier": "free", "email": "test@example.com", "subscription_status": None}
        }
        mock_table.update_item.return_value = {}
        mock_dynamodb = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        mock_boto3.resource.return_value = mock_dynamodb

        client = _client()
        resp = client.post(
            "/api/admin/users/testuser/change-tier",
            json={"tier": "pro"},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["updated_user"]["tier"] == "pro"

    def test_post_change_tier_invalid_returns_422(self):
        """POST /api/admin/users/{username}/change-tier with invalid tier returns 422."""
        client = _client()
        resp = client.post(
            "/api/admin/users/testuser/change-tier",
            json={"tier": "platinum"},
        )

        assert resp.status_code == 422

    def test_mutation_endpoints_require_auth(self):
        """All mutation endpoints return 401 without admin auth."""
        client = _client(with_admin_override=False)

        endpoints = [
            "/api/admin/users/testuser/disable",
            "/api/admin/users/testuser/enable",
            "/api/admin/users/testuser/reset-password",
            "/api/admin/users/testuser/change-tier",
        ]

        for endpoint in endpoints:
            resp = client.post(endpoint, json={"tier": "pro"})
            assert resp.status_code == 401, f"{endpoint} should require auth, got {resp.status_code}"
