# Cost guardrails. AWS Budgets data is not real-time; notifications can lag
# behind actual usage shown by individual service metrics.

resource "aws_budgets_budget" "monthly_cost_guard" {
  name         = "${var.project_name}-${var.environment}-monthly-cost-guard"
  budget_type  = "COST"
  limit_amount = tostring(var.monthly_budget_limit_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  # Early warning: alert when AWS *forecasts* spend will exceed 80% of the
  # limit, so there is time to react before the cap is hit.
  dynamic "notification" {
    for_each = var.budget_notification_email != "" ? [1] : []

    content {
      comparison_operator        = "GREATER_THAN"
      threshold                  = var.budget_forecast_alert_threshold_pct
      threshold_type             = "PERCENTAGE"
      notification_type          = "FORECASTED"
      subscriber_email_addresses = [var.budget_notification_email]
    }
  }

  # Hard trip: alert when *actual* spend reaches 100% of the limit.
  dynamic "notification" {
    for_each = var.budget_notification_email != "" ? [1] : []

    content {
      comparison_operator        = "GREATER_THAN"
      threshold                  = 100
      threshold_type             = "PERCENTAGE"
      notification_type          = "ACTUAL"
      subscriber_email_addresses = [var.budget_notification_email]
    }
  }
}
