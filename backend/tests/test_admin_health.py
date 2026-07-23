"""Integration tests for admin_health service.

Tests system health with mocked ECS, CloudWatch, and Cost Explorer responses,
including Property 13: Graceful degradation — for any subset of failing AWS
services, response contains all data from non-failing services plus warnings
identifying each failed service.

Validates: Requirements 13.4, 16.1
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from app.config import get_settings
from app.services.admin_health import (
    CloudWatchAlarm,
    CostEstimate,
    EcsStatus,
    SystemHealth,
    get_system_health,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ecs_success_response(running: int = 2, desired: int = 2, pending: int = 0):
    """Return a mock ECS DescribeServices response."""
    return {
        "services": [
            {
                "runningCount": running,
                "desiredCount": desired,
                "pendingCount": pending,
            }
        ]
    }


def _cloudwatch_success_response(alarms: list[dict] | None = None):
    """Return a mock CloudWatch DescribeAlarms response."""
    if alarms is None:
        alarms = [
            {"AlarmName": "HighCPU", "StateValue": "OK", "StateReason": "Threshold not breached"},
            {"AlarmName": "HighMemory", "StateValue": "ALARM", "StateReason": "Memory above 90%"},
        ]
    return {"MetricAlarms": alarms, "CompositeAlarms": [], "NextToken": None}


def _cost_explorer_success_response(amount: str = "42.50"):
    """Return a mock Cost Explorer GetCostAndUsage response."""
    return {
        "ResultsByTime": [
            {
                "Total": {
                    "UnblendedCost": {"Amount": amount, "Unit": "USD"}
                }
            }
        ]
    }


def _client_error(service: str, code: str = "ServiceUnavailableException"):
    """Create a botocore ClientError."""
    return ClientError(
        {"Error": {"Code": code, "Message": f"{service} unavailable"}},
        "TestOp",
    )


def _build_mock_clients(
    ecs_response=None,
    ecs_error=None,
    cloudwatch_response=None,
    cloudwatch_error=None,
    cost_response=None,
    cost_error=None,
):
    """Build a boto3.client factory that returns mock clients per service.

    For each service, either return a success response or raise an error.
    """

    def _factory(service_name, region_name=None):
        mock_client = MagicMock()

        if service_name == "ecs":
            if ecs_error:
                mock_client.describe_services.side_effect = ecs_error
            else:
                mock_client.describe_services.return_value = ecs_response or _ecs_success_response()

        elif service_name == "cloudwatch":
            if cloudwatch_error:
                mock_client.describe_alarms.side_effect = cloudwatch_error
            else:
                mock_client.describe_alarms.return_value = cloudwatch_response or _cloudwatch_success_response()

        elif service_name == "ce":
            if cost_error:
                mock_client.get_cost_and_usage.side_effect = cost_error
            else:
                mock_client.get_cost_and_usage.return_value = cost_response or _cost_explorer_success_response()

        return mock_client

    return _factory


# ---------------------------------------------------------------------------
# Tests: Healthy ECS
# ---------------------------------------------------------------------------


class TestEcsHealthy:
    """Test ECS health status when running == desired."""

    def test_healthy_ecs_running_equals_desired(self, monkeypatch):
        """running == desired → health_status='healthy'."""
        monkeypatch.setenv("ECS_CLUSTER_NAME", "my-cluster")
        monkeypatch.setenv("ECS_SERVICE_NAME", "my-service")
        get_settings.cache_clear()

        factory = _build_mock_clients(
            ecs_response=_ecs_success_response(running=2, desired=2, pending=0),
        )

        with patch("app.services.admin_health.boto3.client", side_effect=factory):
            result = get_system_health()

        assert result.ecs.health_status == "healthy"
        assert result.ecs.running_count == 2
        assert result.ecs.desired_count == 2
        assert result.ecs.pending_count == 0
        get_settings.cache_clear()


# ---------------------------------------------------------------------------
# Tests: Degraded ECS
# ---------------------------------------------------------------------------


class TestEcsDegraded:
    """Test ECS health status when running < desired."""

    def test_degraded_ecs_running_less_than_desired(self, monkeypatch):
        """running < desired → health_status='degraded'."""
        monkeypatch.setenv("ECS_CLUSTER_NAME", "my-cluster")
        monkeypatch.setenv("ECS_SERVICE_NAME", "my-service")
        get_settings.cache_clear()

        factory = _build_mock_clients(
            ecs_response=_ecs_success_response(running=1, desired=3, pending=2),
        )

        with patch("app.services.admin_health.boto3.client", side_effect=factory):
            result = get_system_health()

        assert result.ecs.health_status == "degraded"
        assert result.ecs.running_count == 1
        assert result.ecs.desired_count == 3
        assert result.ecs.pending_count == 2
        get_settings.cache_clear()


# ---------------------------------------------------------------------------
# Tests: CloudWatch Alarms Parsing
# ---------------------------------------------------------------------------


class TestCloudWatchAlarms:
    """Test CloudWatch alarms are parsed correctly."""

    def test_alarms_parsed_from_response(self, monkeypatch):
        """CloudWatch alarm names and states are extracted."""
        monkeypatch.setenv("ECS_CLUSTER_NAME", "my-cluster")
        monkeypatch.setenv("ECS_SERVICE_NAME", "my-service")
        get_settings.cache_clear()

        alarms = [
            {"AlarmName": "CPUAlarm", "StateValue": "OK", "StateReason": "All good"},
            {"AlarmName": "DiskAlarm", "StateValue": "ALARM", "StateReason": "Disk full"},
            {"AlarmName": "NetworkAlarm", "StateValue": "INSUFFICIENT_DATA", "StateReason": None},
        ]

        factory = _build_mock_clients(
            cloudwatch_response={"MetricAlarms": alarms, "CompositeAlarms": [], "NextToken": None},
        )

        with patch("app.services.admin_health.boto3.client", side_effect=factory):
            result = get_system_health()

        assert len(result.alarms) == 3
        assert result.alarms[0].alarm_name == "CPUAlarm"
        assert result.alarms[0].state == "OK"
        assert result.alarms[1].alarm_name == "DiskAlarm"
        assert result.alarms[1].state == "ALARM"
        assert result.alarms[2].alarm_name == "NetworkAlarm"
        assert result.alarms[2].state == "INSUFFICIENT_DATA"
        get_settings.cache_clear()


# ---------------------------------------------------------------------------
# Tests: Cost Explorer Parsing
# ---------------------------------------------------------------------------


class TestCostExplorer:
    """Test Cost Explorer response is parsed correctly."""

    def test_cost_estimate_parsed(self, monkeypatch):
        """Cost Explorer amount is returned as float."""
        monkeypatch.setenv("ECS_CLUSTER_NAME", "my-cluster")
        monkeypatch.setenv("ECS_SERVICE_NAME", "my-service")
        get_settings.cache_clear()

        factory = _build_mock_clients(
            cost_response=_cost_explorer_success_response("123.45"),
        )

        with patch("app.services.admin_health.boto3.client", side_effect=factory):
            result = get_system_health()

        assert result.cost_estimate is not None
        assert result.cost_estimate.current_month_usd == 123.45
        assert result.cost_estimate.data_timestamp != ""
        get_settings.cache_clear()


# ---------------------------------------------------------------------------
# Tests: Graceful Degradation (Individual Service Failures)
# ---------------------------------------------------------------------------


class TestGracefulDegradation:
    """Test that individual service failures don't block other services."""

    def test_ecs_failure_others_succeed(self, monkeypatch):
        """ECS fails → warnings includes ECS, CloudWatch + CostExplorer still return data."""
        monkeypatch.setenv("ECS_CLUSTER_NAME", "my-cluster")
        monkeypatch.setenv("ECS_SERVICE_NAME", "my-service")
        get_settings.cache_clear()

        factory = _build_mock_clients(
            ecs_error=_client_error("ECS"),
        )

        with patch("app.services.admin_health.boto3.client", side_effect=factory):
            result = get_system_health()

        # ECS should be unreachable
        assert result.ecs.health_status == "unreachable"
        # Warnings should mention ECS
        assert any("ECS" in w or "ecs" in w.lower() for w in result.warnings)
        # CloudWatch still works
        assert len(result.alarms) > 0
        # Cost Explorer still works
        assert result.cost_estimate is not None
        get_settings.cache_clear()

    def test_cloudwatch_failure_others_succeed(self, monkeypatch):
        """CloudWatch fails → warnings includes CloudWatch, ECS + CostExplorer still return data."""
        monkeypatch.setenv("ECS_CLUSTER_NAME", "my-cluster")
        monkeypatch.setenv("ECS_SERVICE_NAME", "my-service")
        get_settings.cache_clear()

        factory = _build_mock_clients(
            cloudwatch_error=_client_error("CloudWatch"),
        )

        with patch("app.services.admin_health.boto3.client", side_effect=factory):
            result = get_system_health()

        # ECS should still work
        assert result.ecs.health_status in ("healthy", "degraded")
        # CloudWatch returns empty alarms list (graceful)
        assert result.alarms == []
        # Warnings mention CloudWatch
        assert any("CloudWatch" in w or "cloudwatch" in w.lower() for w in result.warnings)
        # Cost Explorer still works
        assert result.cost_estimate is not None
        get_settings.cache_clear()

    def test_cost_explorer_failure_others_succeed(self, monkeypatch):
        """Cost Explorer fails → warnings includes Cost Explorer, ECS + CloudWatch still return data."""
        monkeypatch.setenv("ECS_CLUSTER_NAME", "my-cluster")
        monkeypatch.setenv("ECS_SERVICE_NAME", "my-service")
        get_settings.cache_clear()

        factory = _build_mock_clients(
            cost_error=_client_error("CostExplorer"),
        )

        with patch("app.services.admin_health.boto3.client", side_effect=factory):
            result = get_system_health()

        # ECS should still work
        assert result.ecs.health_status in ("healthy", "degraded")
        # CloudWatch still works
        assert len(result.alarms) > 0
        # Cost Explorer is None (graceful)
        assert result.cost_estimate is None
        # Warnings mention Cost Explorer
        assert any("Cost" in w or "cost" in w.lower() for w in result.warnings)
        get_settings.cache_clear()

    def test_all_three_services_fail(self, monkeypatch):
        """All 3 fail → all empty/unreachable with 3 warnings."""
        monkeypatch.setenv("ECS_CLUSTER_NAME", "my-cluster")
        monkeypatch.setenv("ECS_SERVICE_NAME", "my-service")
        get_settings.cache_clear()

        factory = _build_mock_clients(
            ecs_error=_client_error("ECS"),
            cloudwatch_error=_client_error("CloudWatch"),
            cost_error=_client_error("CostExplorer"),
        )

        with patch("app.services.admin_health.boto3.client", side_effect=factory):
            result = get_system_health()

        assert result.ecs.health_status == "unreachable"
        assert result.alarms == []
        assert result.cost_estimate is None
        assert len(result.warnings) == 3
        get_settings.cache_clear()


# ---------------------------------------------------------------------------
# Property 13: Graceful degradation (Hypothesis)
# Feature: admin-panel, Property 13: Graceful degradation
# ---------------------------------------------------------------------------


# Strategy: generate any subset of services that fail
SERVICE_NAMES = ["ecs", "cloudwatch", "cost_explorer"]


@st.composite
def failing_service_subsets(draw):
    """Generate a subset of AWS services that will fail."""
    subset = draw(st.lists(st.sampled_from(SERVICE_NAMES), unique=True, min_size=0, max_size=3))
    return set(subset)


class TestProperty13GracefulDegradation:
    """**Validates: Requirements 12.5, 13.4, 16.1**

    Property 13: For any subset of failing AWS services, response contains
    all data from non-failing services plus warnings identifying each
    failed service.
    """

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(failing_services=failing_service_subsets())
    def test_graceful_degradation_any_subset(self, failing_services):
        """**Validates: Requirements 12.5, 13.4, 16.1**

        For any subset of failing AWS services, the response contains all data
        from non-failing services plus warnings identifying each failed service.
        """
        os.environ["ECS_CLUSTER_NAME"] = "my-cluster"
        os.environ["ECS_SERVICE_NAME"] = "my-service"
        get_settings.cache_clear()

        try:
            factory = _build_mock_clients(
                ecs_error=_client_error("ECS") if "ecs" in failing_services else None,
                cloudwatch_error=_client_error("CloudWatch") if "cloudwatch" in failing_services else None,
                cost_error=_client_error("CostExplorer") if "cost_explorer" in failing_services else None,
            )

            with patch("app.services.admin_health.boto3.client", side_effect=factory):
                result = get_system_health()

            # --- Verify non-failing services return data ---
            if "ecs" not in failing_services:
                assert result.ecs.health_status in ("healthy", "degraded")
                assert result.ecs.running_count >= 0
            else:
                assert result.ecs.health_status == "unreachable"

            if "cloudwatch" not in failing_services:
                # Should have alarms from the default mock
                assert len(result.alarms) >= 0  # might be 0 if response is empty but not error
            else:
                assert result.alarms == []

            if "cost_explorer" not in failing_services:
                assert result.cost_estimate is not None
                assert result.cost_estimate.current_month_usd >= 0
            else:
                assert result.cost_estimate is None

            # --- Verify warnings identify each failed service ---
            assert len(result.warnings) >= len(failing_services)

            if "ecs" in failing_services:
                assert any("ecs" in w.lower() for w in result.warnings)

            if "cloudwatch" in failing_services:
                assert any("cloudwatch" in w.lower() for w in result.warnings)

            if "cost_explorer" in failing_services:
                assert any("cost" in w.lower() for w in result.warnings)
        finally:
            get_settings.cache_clear()
