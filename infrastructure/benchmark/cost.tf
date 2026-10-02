resource "aws_sns_topic" "benchmark" {
  name = "${local.prefix}-cost-alerts"
}
resource "aws_sns_topic_subscription" "benchmark_email" {
  count     = nonsensitive(var.benchmark_alert_email != "") ? 1 : 0
  topic_arn = aws_sns_topic.benchmark.arn
  protocol  = "email"
  endpoint  = var.benchmark_alert_email
}
resource "aws_sns_topic_policy" "benchmark" {
  arn = aws_sns_topic.benchmark.arn
  policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "budgets.amazonaws.com" }, Action = "sns:Publish", Resource = aws_sns_topic.benchmark.arn, Condition = { StringEquals = { "aws:SourceAccount" = var.expected_account_id } } }]
  })
}
resource "aws_budgets_budget" "benchmark" {
  name         = "${local.prefix}-monthly"
  budget_type  = "COST"
  limit_amount = tostring(var.monthly_budget_limit_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"
  cost_filter {
    name   = "TagKeyValue"
    values = ["user:Environment$benchmark"]
  }
  notification {
    comparison_operator       = "GREATER_THAN"
    threshold                 = 80
    threshold_type            = "PERCENTAGE"
    notification_type         = "FORECASTED"
    subscriber_sns_topic_arns = [aws_sns_topic.benchmark.arn]
  }
  notification {
    comparison_operator       = "GREATER_THAN"
    threshold                 = 100
    threshold_type            = "PERCENTAGE"
    notification_type         = "ACTUAL"
    subscriber_sns_topic_arns = [aws_sns_topic.benchmark.arn]
  }
  depends_on = [aws_sns_topic_policy.benchmark]
}
