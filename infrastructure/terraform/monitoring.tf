# Operational alarms and alerting (CloudWatch -> SNS).
#
# Completes the "measurement + alerting" story: an SNS alerts topic plus
# CloudWatch alarms for ALB errors/latency, ECS CPU/memory, and target health.
# All alarms publish to the same topic. Because ECS scales to zero, metrics are
# absent when idle; alarms use treat_missing_data = "notBreaching" so idle
# periods never trigger a false alert.
#
# Dimension references reuse the locals defined in cloudwatch_dashboard.tf
# (local.alb_full_name, local.alb_target_group_name).

resource "aws_sns_topic" "alerts" {
  count = var.enable_alarms ? 1 : 0

  name = "${var.project_name}-alerts-${var.environment}"

  tags = merge(
    var.tags,
    {
      Name        = "${var.project_name}-alerts-${var.environment}"
      Environment = var.environment
    }
  )
}

# Optional email subscription. The subscriber must confirm via the email AWS
# sends before notifications are delivered.
resource "aws_sns_topic_subscription" "alerts_email" {
  count = var.enable_alarms && var.alert_notification_email != "" ? 1 : 0

  topic_arn = aws_sns_topic.alerts[0].arn
  protocol  = "email"
  endpoint  = var.alert_notification_email
}

locals {
  alarm_actions = var.enable_alarms ? [aws_sns_topic.alerts[0].arn] : []
}

# ALB target 5XX responses: backend errors reaching clients.
resource "aws_cloudwatch_metric_alarm" "alb_target_5xx" {
  count = var.enable_alarms ? 1 : 0

  alarm_name          = "${var.project_name}-${var.environment}-alb-target-5xx"
  alarm_description   = "ALB target 5XX responses exceeded the threshold over 5 minutes."
  namespace           = "AWS/ApplicationELB"
  metric_name         = "HTTPCode_Target_5XX_Count"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = var.alarm_alb_5xx_threshold
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    LoadBalancer = local.alb_full_name
  }

  alarm_actions = local.alarm_actions
  ok_actions    = local.alarm_actions
  tags          = var.tags
}

# ELB-level 5XX: the load balancer itself failing (e.g. no healthy targets).
resource "aws_cloudwatch_metric_alarm" "alb_elb_5xx" {
  count = var.enable_alarms ? 1 : 0

  alarm_name          = "${var.project_name}-${var.environment}-alb-elb-5xx"
  alarm_description   = "ALB-generated 5XX responses (e.g. no healthy targets) over 5 minutes."
  namespace           = "AWS/ApplicationELB"
  metric_name         = "HTTPCode_ELB_5XX_Count"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = var.alarm_alb_5xx_threshold
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    LoadBalancer = local.alb_full_name
  }

  alarm_actions = local.alarm_actions
  ok_actions    = local.alarm_actions
  tags          = var.tags
}

# Target latency: slow backend responses.
resource "aws_cloudwatch_metric_alarm" "alb_target_latency" {
  count = var.enable_alarms ? 1 : 0

  alarm_name          = "${var.project_name}-${var.environment}-alb-target-latency"
  alarm_description   = "Average ALB target response time exceeded the threshold."
  namespace           = "AWS/ApplicationELB"
  metric_name         = "TargetResponseTime"
  statistic           = "Average"
  period              = 300
  evaluation_periods  = 2
  threshold           = var.alarm_alb_target_latency_seconds
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    LoadBalancer = local.alb_full_name
  }

  alarm_actions = local.alarm_actions
  ok_actions    = local.alarm_actions
  tags          = var.tags
}

# Unhealthy targets: a running task failing its health check.
resource "aws_cloudwatch_metric_alarm" "alb_unhealthy_hosts" {
  count = var.enable_alarms ? 1 : 0

  alarm_name          = "${var.project_name}-${var.environment}-alb-unhealthy-hosts"
  alarm_description   = "One or more ALB targets are unhealthy."
  namespace           = "AWS/ApplicationELB"
  metric_name         = "UnHealthyHostCount"
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 3
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    TargetGroup  = local.alb_target_group_name
    LoadBalancer = local.alb_full_name
  }

  alarm_actions = local.alarm_actions
  ok_actions    = local.alarm_actions
  tags          = var.tags
}

# ECS service CPU utilization.
resource "aws_cloudwatch_metric_alarm" "ecs_cpu_high" {
  count = var.enable_alarms ? 1 : 0

  alarm_name          = "${var.project_name}-${var.environment}-ecs-cpu-high"
  alarm_description   = "ECS service average CPU utilization is high."
  namespace           = "AWS/ECS"
  metric_name         = "CPUUtilization"
  statistic           = "Average"
  period              = 300
  evaluation_periods  = 2
  threshold           = var.alarm_cpu_utilization_pct
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    ClusterName = aws_ecs_cluster.main.name
    ServiceName = aws_ecs_service.target_backend.name
  }

  alarm_actions = local.alarm_actions
  ok_actions    = local.alarm_actions
  tags          = var.tags
}

# ECS service memory utilization.
resource "aws_cloudwatch_metric_alarm" "ecs_memory_high" {
  count = var.enable_alarms ? 1 : 0

  alarm_name          = "${var.project_name}-${var.environment}-ecs-memory-high"
  alarm_description   = "ECS service average memory utilization is high."
  namespace           = "AWS/ECS"
  metric_name         = "MemoryUtilization"
  statistic           = "Average"
  period              = 300
  evaluation_periods  = 2
  threshold           = var.alarm_memory_utilization_pct
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    ClusterName = aws_ecs_cluster.main.name
    ServiceName = aws_ecs_service.target_backend.name
  }

  alarm_actions = local.alarm_actions
  ok_actions    = local.alarm_actions
  tags          = var.tags
}
