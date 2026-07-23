"""Property-based tests for admin mutation and audit logic.

Uses Hypothesis to verify universal properties of tier change validation,
Stripe subscription warnings, audit log completeness, and audit failure
rollback behavior.

# Feature: admin-panel
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch, call
import datetime

from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st
from fastapi import HTTPException
import pytest

from app.services.admin_users import (
    VALID_TIERS,
    change_tier,
    disable_user,
    enable_user,
    TierChangeResult,
    UserActionResult,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_settings():
    """Return a mock settings object with required attributes."""
    s = MagicMock()
    s.aws_region = "us-east-1"
    s.cognito_user_pool_id = "us-east-1_test"
    return s


def _mock_usage_table(profile_item=None):
    """Create a mock DynamoDB table that returns the given profile item."""
    table = MagicMock()
    table.get_item.return_value = {"Item": profile_item or {}}
    table.update_item.return_value = {}
    return table


def _mock_dynamodb_resource(table):
    """Create a mock boto3 DynamoDB resource."""
    resource = MagicMock()
    resource.Table.return_value = table
    return resource


# ---------------------------------------------------------------------------
# Feature: admin-panel, Property 5: Tier change validation
# ---------------------------------------------------------------------------


class TestTierChangeValidation:
    """Property 5: Tier change validation.

    For any valid tier value, change_tier updates persisted tier;
    for invalid values, returns error and tier unchanged.

    **Validates: Requirements 6.1, 6.2, 6.3**
    """

    @given(tier=st.sampled_from(["free", "pro", "business"]))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_valid_tier_accepted(self, tier: str):
        """For any valid tier value, change_tier succeeds and updates tier."""
        # Feature: admin-panel, Property 5: Tier change validation
        profile_item = {
            "tier": "free",
            "subscription_status": None,
            "email": "user@test.com",
            "status": "enabled",
            "identity_provider": "native",
            "created_at": "2024-01-01",
            "last_active": "2024-06-01",
            "sessions_used": 0,
            "minutes_used": 0,
        }
        table = _mock_usage_table(profile_item)
        resource = _mock_dynamodb_resource(table)

        with (
            patch("app.services.admin_users.get_settings", return_value=_mock_settings()),
            patch("app.services.admin_users.boto3.resource", return_value=resource),
            patch("app.services.admin_users._record_audit") as mock_audit,
        ):
            result = change_tier("test-user", tier, "admin-001")

        assert result.success is True
        assert tier in result.message
        # DynamoDB update was called
        table.update_item.assert_called_once()
        # Verify the update expression set the correct tier
        call_kwargs = table.update_item.call_args[1]
        assert call_kwargs["ExpressionAttributeValues"][":tier"] == tier

    @given(
        tier=st.text(min_size=1, max_size=20).filter(
            lambda t: t not in {"free", "pro", "business"}
        )
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_invalid_tier_rejected(self, tier: str):
        """For any invalid tier value, change_tier raises HTTPException(422) and does NOT call DynamoDB."""
        # Feature: admin-panel, Property 5: Tier change validation
        table = _mock_usage_table()
        resource = _mock_dynamodb_resource(table)

        with (
            patch("app.services.admin_users.get_settings", return_value=_mock_settings()),
            patch("app.services.admin_users.boto3.resource", return_value=resource),
            patch("app.services.admin_users._record_audit") as mock_audit,
        ):
            with pytest.raises(HTTPException) as exc_info:
                change_tier("test-user", tier, "admin-001")

        assert exc_info.value.status_code == 422
        # DynamoDB update_item should NOT have been called
        table.update_item.assert_not_called()
        # Audit should NOT have been called
        mock_audit.assert_not_called()


# ---------------------------------------------------------------------------
# Feature: admin-panel, Property 6: Stripe subscription warning
# ---------------------------------------------------------------------------


class TestStripeSubscriptionWarning:
    """Property 6: Stripe subscription warning.

    For any user with active Stripe subscription, tier change response
    includes a non-None warning.

    **Validates: Requirements 6.6**
    """

    @given(tier=st.sampled_from(["free", "pro", "business"]))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_stripe_warning_when_subscription_active(self, tier: str):
        """When user has subscription_status='active', response includes warning."""
        # Feature: admin-panel, Property 6: Stripe subscription warning
        profile_item = {
            "tier": "free",
            "subscription_status": "active",
            "email": "stripe-user@test.com",
            "status": "enabled",
            "identity_provider": "native",
            "created_at": "2024-01-01",
            "last_active": "2024-06-01",
            "sessions_used": 5,
            "minutes_used": 120,
        }
        table = _mock_usage_table(profile_item)
        resource = _mock_dynamodb_resource(table)

        with (
            patch("app.services.admin_users.get_settings", return_value=_mock_settings()),
            patch("app.services.admin_users.boto3.resource", return_value=resource),
            patch("app.services.admin_users._record_audit") as mock_audit,
        ):
            result = change_tier("stripe-user", tier, "admin-001")

        assert result.success is True
        assert result.warning is not None
        assert "Stripe" in result.warning

    @given(tier=st.sampled_from(["free", "pro", "business"]))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_no_warning_when_no_active_subscription(self, tier: str):
        """When user has no active subscription, response has no warning."""
        # Feature: admin-panel, Property 6: Stripe subscription warning
        profile_item = {
            "tier": "free",
            "subscription_status": "canceled",
            "email": "nostripe@test.com",
            "status": "enabled",
            "identity_provider": "native",
            "created_at": "2024-01-01",
            "last_active": "",
            "sessions_used": 0,
            "minutes_used": 0,
        }
        table = _mock_usage_table(profile_item)
        resource = _mock_dynamodb_resource(table)

        with (
            patch("app.services.admin_users.get_settings", return_value=_mock_settings()),
            patch("app.services.admin_users.boto3.resource", return_value=resource),
            patch("app.services.admin_users._record_audit") as mock_audit,
        ):
            result = change_tier("nostripe-user", tier, "admin-001")

        assert result.success is True
        assert result.warning is None


# ---------------------------------------------------------------------------
# Feature: admin-panel, Property 7: Audit log completeness
# ---------------------------------------------------------------------------


class TestAuditLogCompleteness:
    """Property 7: Audit log completeness.

    For any successful mutation, an audit entry is persisted with correct
    admin_user_id, target_user_id, action_type, and UTC timestamp.

    **Validates: Requirements 7.1, 7.2**
    """

    @given(action=st.sampled_from(["disable", "enable"]))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_audit_entry_persisted_on_success(self, action: str):
        """After successful mutation, record_action is called with correct args."""
        # Feature: admin-panel, Property 7: Audit log completeness
        admin_id = "admin-user-123"
        target_id = "target-user-456"

        mock_cognito = MagicMock()
        # Both disable and enable succeed without error
        mock_cognito.admin_disable_user.return_value = {}
        mock_cognito.admin_enable_user.return_value = {}

        with (
            patch("app.services.admin_users.get_settings", return_value=_mock_settings()),
            patch("app.services.admin_users.boto3.client", return_value=mock_cognito),
            patch("app.services.admin_users._record_audit") as mock_audit,
        ):
            if action == "disable":
                result = disable_user(target_id, admin_id)
            else:
                result = enable_user(target_id, admin_id)

        assert result.success is True
        # Verify audit was called exactly once
        mock_audit.assert_called_once()
        # _record_audit is called with positional args:
        # _record_audit(admin_user_id, target_user_id, action_type, ...)
        audit_args = mock_audit.call_args[0]
        assert audit_args[0] == admin_id  # admin_user_id
        assert audit_args[1] == target_id  # target_user_id
        assert audit_args[2] == action  # action_type

    @given(tier=st.sampled_from(["free", "pro", "business"]))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_audit_entry_for_tier_change(self, tier: str):
        """After successful tier change, record_action is called with correct args."""
        # Feature: admin-panel, Property 7: Audit log completeness
        admin_id = "admin-user-789"
        target_id = "target-user-abc"

        profile_item = {
            "tier": "free",
            "subscription_status": None,
            "email": "audit@test.com",
            "status": "enabled",
            "identity_provider": "native",
            "created_at": "2024-01-01",
            "last_active": "",
            "sessions_used": 0,
            "minutes_used": 0,
        }
        table = _mock_usage_table(profile_item)
        resource = _mock_dynamodb_resource(table)

        with (
            patch("app.services.admin_users.get_settings", return_value=_mock_settings()),
            patch("app.services.admin_users.boto3.resource", return_value=resource),
            patch("app.services.admin_users._record_audit") as mock_audit,
        ):
            result = change_tier(target_id, tier, admin_id)

        assert result.success is True
        mock_audit.assert_called_once()
        # Check audit arguments
        audit_call = mock_audit.call_args
        # _record_audit is called with positional args
        assert audit_call[0][0] == admin_id  # admin_user_id
        assert audit_call[0][1] == target_id  # target_user_id
        assert audit_call[0][2] == "change_tier"  # action_type
        assert audit_call[0][3] == "free"  # previous_value
        assert audit_call[0][4] == tier  # new_value


# ---------------------------------------------------------------------------
# Feature: admin-panel, Property 8: Audit failure blocks mutation
# ---------------------------------------------------------------------------


class TestAuditFailureBlocksMutation:
    """Property 8: Audit failure blocks mutation.

    When audit write fails, API returns error and user state remains unchanged
    (rollback occurs).

    **Validates: Requirements 7.5**
    """

    def test_audit_failure_on_disable_triggers_rollback(self):
        """When audit fails after disable, user is re-enabled (rollback)."""
        # Feature: admin-panel, Property 8: Audit failure blocks mutation
        admin_id = "admin-001"
        target_id = "user-to-disable"

        mock_cognito = MagicMock()
        mock_cognito.admin_disable_user.return_value = {}
        mock_cognito.admin_enable_user.return_value = {}  # rollback call

        with (
            patch("app.services.admin_users.get_settings", return_value=_mock_settings()),
            patch("app.services.admin_users.boto3.client", return_value=mock_cognito),
            patch(
                "app.services.admin_users._record_audit",
                side_effect=RuntimeError("DynamoDB write failed"),
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                disable_user(target_id, admin_id)

        assert exc_info.value.status_code == 500
        # Verify rollback: admin_enable_user was called to undo the disable
        mock_cognito.admin_enable_user.assert_called_once()

    def test_audit_failure_on_enable_triggers_rollback(self):
        """When audit fails after enable, user is re-disabled (rollback)."""
        # Feature: admin-panel, Property 8: Audit failure blocks mutation
        admin_id = "admin-002"
        target_id = "user-to-enable"

        mock_cognito = MagicMock()
        mock_cognito.admin_enable_user.return_value = {}
        mock_cognito.admin_disable_user.return_value = {}  # rollback call

        with (
            patch("app.services.admin_users.get_settings", return_value=_mock_settings()),
            patch("app.services.admin_users.boto3.client", return_value=mock_cognito),
            patch(
                "app.services.admin_users._record_audit",
                side_effect=RuntimeError("DynamoDB write failed"),
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                enable_user(target_id, admin_id)

        assert exc_info.value.status_code == 500
        # Verify rollback: admin_disable_user was called to undo the enable
        mock_cognito.admin_disable_user.assert_called_once()

    @given(tier=st.sampled_from(["free", "pro", "business"]))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_audit_failure_on_tier_change_triggers_rollback(self, tier: str):
        """When audit fails after tier change, tier is reverted in DynamoDB."""
        # Feature: admin-panel, Property 8: Audit failure blocks mutation
        admin_id = "admin-003"
        target_id = "user-tier-rollback"
        original_tier = "free"

        profile_item = {
            "tier": original_tier,
            "subscription_status": None,
            "email": "rollback@test.com",
            "status": "enabled",
            "identity_provider": "native",
            "created_at": "2024-01-01",
            "last_active": "",
            "sessions_used": 0,
            "minutes_used": 0,
        }
        table = _mock_usage_table(profile_item)
        resource = _mock_dynamodb_resource(table)

        with (
            patch("app.services.admin_users.get_settings", return_value=_mock_settings()),
            patch("app.services.admin_users.boto3.resource", return_value=resource),
            patch(
                "app.services.admin_users._record_audit",
                side_effect=RuntimeError("Audit write failed"),
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                change_tier(target_id, tier, admin_id)

        assert exc_info.value.status_code == 500
        # Verify DynamoDB update was called TWICE: once for the change, once for rollback
        assert table.update_item.call_count == 2
        # The second call (rollback) should revert to original tier
        rollback_call = table.update_item.call_args_list[1]
        rollback_values = rollback_call[1]["ExpressionAttributeValues"]
        assert rollback_values[":tier"] == original_tier
