"""System health service for the admin panel.

Queries ECS, CloudWatch, and AWS Cost Explorer to build an operational health
snapshot. Each AWS service call is independent — if one fails, the others
still return data. Failed services are recorded in a warnings list so the
frontend can display partial results with appropriate messaging.

Requirements: 13.1, 13.2, 13.4, 13.5, 13.6, 13.7, 16.1
"""

from __future__ import annotations

import datetime
import logging

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from pydantic import BaseModel

from app.config import get_settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class EcsStatus(BaseModel):
    running_count: int
    desired_count: int
    pending_count: int
    health_status: str  # "healthy" | "degraded" | "unreachable"


class CloudWatchAlarm(BaseModel):
    alarm_name: str
    state: str  # "OK" | "ALARM" | "INSUFFICIENT_DATA"
    reason: str | None


class CostEstimate(BaseModel):
    current_month_usd: float
    data_timestamp: str  # ISO 8601


class SystemHealth(BaseModel):
    ecs: EcsStatus
    alarms: list[CloudWatchAlarm]
    cost_estimate: CostEstimate | None
    warnings: list[str]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _query_ecs_status(region: str, cluster: str, service: str) -> EcsStatus:
    """Query ECS DescribeServices for the configured cluster/service.

    Returns health_status:
      - "healthy" if running_count == desired_count
      - "degraded" if running_count < desired_count
      - "unreachable" should not be returned here (raised as exception instead)
    """
    client = boto3.client("ecs", region_name=region)
    response = client.describe_services(cluster=cluster, services=[service])
    services = response.get("services", [])

    if not services:
        raise ValueError("ECS service not found in response")

    svc = services[0]
    running = svc.get("runningCount", 0)
    desired = svc.get("desiredCount", 0)
    pending = svc.get("pendingCount", 0)

    if running >= desired:
        health = "healthy"
    else:
        health = "degraded"

    return EcsStatus(
        running_count=running,
        desired_count=desired,
        pending_count=pending,
        health_status=health,
    )


def _query_cloudwatch_alarms(region: str) -> list[CloudWatchAlarm]:
    """Query CloudWatch DescribeAlarms to get all alarms with their state."""
    client = boto3.client("cloudwatch", region_name=region)
    alarms: list[CloudWatchAlarm] = []
    next_token: str | None = None

    while True:
        kwargs: dict = {}
        if next_token:
            kwargs["NextToken"] = next_token
        response = client.describe_alarms(**kwargs)

        for alarm in response.get("MetricAlarms", []):
            alarms.append(
                CloudWatchAlarm(
                    alarm_name=alarm.get("AlarmName", ""),
                    state=alarm.get("StateValue", "INSUFFICIENT_DATA"),
                    reason=alarm.get("StateReason"),
                )
            )
        for alarm in response.get("CompositeAlarms", []):
            alarms.append(
                CloudWatchAlarm(
                    alarm_name=alarm.get("AlarmName", ""),
                    state=alarm.get("StateValue", "INSUFFICIENT_DATA"),
                    reason=alarm.get("StateReason"),
                )
            )

        next_token = response.get("NextToken")
        if not next_token:
            break

    return alarms


def _query_cost_estimate() -> CostEstimate:
    """Query AWS Cost Explorer for the current month's cost.

    AWS requires Cost Explorer calls to be made in us-east-1 regardless of
    the deployment region (Requirement 13.7).
    """
    client = boto3.client("ce", region_name="us-east-1")
    now = datetime.datetime.now(datetime.timezone.utc)
    start_of_month = now.strftime("%Y-%m-01")
    # End date is exclusive in Cost Explorer — use tomorrow or end of month
    end_date = (now + datetime.timedelta(days=1)).strftime("%Y-%m-%d")

    response = client.get_cost_and_usage(
        TimePeriod={"Start": start_of_month, "End": end_date},
        Granularity="MONTHLY",
        Metrics=["UnblendedCost"],
    )

    results = response.get("ResultsByTime", [])
    if results:
        amount_str = (
            results[0]
            .get("Total", {})
            .get("UnblendedCost", {})
            .get("Amount", "0")
        )
        amount = float(amount_str)
    else:
        amount = 0.0

    return CostEstimate(
        current_month_usd=round(amount, 2),
        data_timestamp=now.isoformat(),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_system_health() -> SystemHealth:
    """Build the system health snapshot from live AWS state.

    Each service is queried independently. If any call fails, the others
    still return data and the failure is recorded in the warnings list.
    """
    settings = get_settings()
    warnings: list[str] = []

    # --- ECS ---
    ecs: EcsStatus
    cluster = settings.ecs_cluster_name
    service = settings.ecs_service_name

    if not cluster or not service:
        ecs = EcsStatus(
            running_count=0,
            desired_count=0,
            pending_count=0,
            health_status="unreachable",
        )
        warnings.append("ECS cluster/service not configured")
    else:
        try:
            ecs = _query_ecs_status(settings.aws_region, cluster, service)
        except (ClientError, BotoCoreError, ValueError, Exception) as exc:
            logger.warning("ECS DescribeServices failed: %s", exc)
            ecs = EcsStatus(
                running_count=0,
                desired_count=0,
                pending_count=0,
                health_status="unreachable",
            )
            warnings.append(f"ECS service could not be queried: {exc}")

    # --- CloudWatch ---
    alarms: list[CloudWatchAlarm]
    try:
        alarms = _query_cloudwatch_alarms(settings.aws_region)
    except (ClientError, BotoCoreError, Exception) as exc:
        logger.warning("CloudWatch DescribeAlarms failed: %s", exc)
        alarms = []
        warnings.append(f"CloudWatch alarms could not be queried: {exc}")

    # --- Cost Explorer (always us-east-1) ---
    cost_estimate: CostEstimate | None
    try:
        cost_estimate = _query_cost_estimate()
    except (ClientError, BotoCoreError, Exception) as exc:
        logger.warning("Cost Explorer GetCostAndUsage failed: %s", exc)
        cost_estimate = None
        warnings.append(f"Cost Explorer could not be queried: {exc}")

    return SystemHealth(
        ecs=ecs,
        alarms=alarms,
        cost_estimate=cost_estimate,
        warnings=warnings,
    )
