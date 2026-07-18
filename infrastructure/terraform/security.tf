# Security baseline: VPC Flow Logs, GuardDuty, Security Hub.
#
# These resources establish the detection and compliance layer required by
# enterprise deployments and the AWS Well-Architected Security pillar. All are
# gated by variables so existing environments are unaffected until explicitly
# opted in.

# =============================================================================
# VPC Flow Logs — network traffic visibility
# =============================================================================
# Captures REJECT and ALL traffic metadata for the target VPC. Stored in a
# dedicated CloudWatch log group with configurable retention. Essential for
# security incident investigation and compliance audits.

resource "aws_cloudwatch_log_group" "vpc_flow_logs" {
  count = var.enable_vpc_flow_logs ? 1 : 0

  name              = "/aws/vpc/flow-logs/${var.project_name}-${var.environment}"
  retention_in_days = var.vpc_flow_logs_retention_days

  tags = merge(var.tags, {
    Name        = "${var.project_name}-vpc-flow-logs-${var.environment}"
    Environment = var.environment
  })
}

resource "aws_iam_role" "vpc_flow_logs" {
  count = var.enable_vpc_flow_logs ? 1 : 0

  name = "${var.project_name}-vpc-flow-logs-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "vpc-flow-logs.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = merge(var.tags, {
    Name        = "${var.project_name}-vpc-flow-logs-${var.environment}"
    Environment = var.environment
  })
}

resource "aws_iam_role_policy" "vpc_flow_logs" {
  count = var.enable_vpc_flow_logs ? 1 : 0

  name = "${var.project_name}-vpc-flow-logs-publish"
  role = aws_iam_role.vpc_flow_logs[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents",
          "logs:DescribeLogGroups",
          "logs:DescribeLogStreams"
        ]
        Resource = [
          aws_cloudwatch_log_group.vpc_flow_logs[0].arn,
          "${aws_cloudwatch_log_group.vpc_flow_logs[0].arn}:*"
        ]
      }
    ]
  })
}

resource "aws_flow_log" "target_vpc" {
  count = var.enable_vpc_flow_logs ? 1 : 0

  vpc_id                   = aws_vpc.target.id
  traffic_type             = var.vpc_flow_logs_traffic_type
  iam_role_arn             = aws_iam_role.vpc_flow_logs[0].arn
  log_destination          = aws_cloudwatch_log_group.vpc_flow_logs[0].arn
  log_destination_type     = "cloud-watch-logs"
  max_aggregation_interval = 60

  tags = merge(var.tags, {
    Name        = "${var.project_name}-target-vpc-flow-log-${var.environment}"
    Environment = var.environment
  })
}

# =============================================================================
# Amazon GuardDuty — threat detection
# =============================================================================
# Enables intelligent threat detection that monitors for malicious activity and
# unauthorized behaviour. Findings publish to EventBridge (and optionally SNS).
# Cost: ~$4/GB of CloudTrail events + ~$1/GB of VPC Flow Logs analysed.

resource "aws_guardduty_detector" "main" {
  count = var.enable_guardduty ? 1 : 0

  enable                       = true
  finding_publishing_frequency = "FIFTEEN_MINUTES"

  datasources {
    s3_logs {
      enable = true
    }
  }

  tags = merge(var.tags, {
    Name        = "${var.project_name}-guardduty-${var.environment}"
    Environment = var.environment
  })
}

# Route GuardDuty HIGH/CRITICAL findings to the existing alerts SNS topic.
resource "aws_cloudwatch_event_rule" "guardduty_findings" {
  count = var.enable_guardduty && var.enable_alarms ? 1 : 0

  name        = "${var.project_name}-guardduty-findings-${var.environment}"
  description = "Route GuardDuty HIGH and CRITICAL findings to SNS."

  event_pattern = jsonencode({
    source      = ["aws.guardduty"]
    detail-type = ["GuardDuty Finding"]
    detail = {
      severity = [{ numeric = [">=", 7] }]
    }
  })

  tags = var.tags
}

resource "aws_cloudwatch_event_target" "guardduty_to_sns" {
  count = var.enable_guardduty && var.enable_alarms ? 1 : 0

  rule      = aws_cloudwatch_event_rule.guardduty_findings[0].name
  target_id = "${var.project_name}-guardduty-sns"
  arn       = aws_sns_topic.alerts[0].arn
}

# Allow EventBridge to publish to the SNS topic.
resource "aws_sns_topic_policy" "alerts_eventbridge" {
  count = var.enable_guardduty && var.enable_alarms ? 1 : 0

  arn = aws_sns_topic.alerts[0].arn

  policy = jsonencode({
    Version = "2012-10-17"
    Id      = "AllowEventBridgePublish"
    Statement = [
      {
        Sid       = "AllowEventBridgeToPublish"
        Effect    = "Allow"
        Principal = { Service = "events.amazonaws.com" }
        Action    = "sns:Publish"
        Resource  = aws_sns_topic.alerts[0].arn
      }
    ]
  })
}

# =============================================================================
# AWS Security Hub — compliance and posture management
# =============================================================================
# Aggregates findings from GuardDuty, Inspector, and Config. Enables the AWS
# Foundational Security Best Practices standard for continuous compliance checks.

resource "aws_securityhub_account" "main" {
  count = var.enable_security_hub ? 1 : 0

  enable_default_standards = false

  depends_on = [aws_guardduty_detector.main]
}

resource "aws_securityhub_standards_subscription" "aws_foundational" {
  count = var.enable_security_hub ? 1 : 0

  standards_arn = "arn:aws:securityhub:${var.aws_region}::standards/aws-foundational-security-best-practices/v/1.0.0"

  depends_on = [aws_securityhub_account.main]
}

resource "aws_securityhub_standards_subscription" "cis_aws" {
  count = var.enable_security_hub && var.enable_cis_benchmark ? 1 : 0

  standards_arn = "arn:aws:securityhub:::ruleset/cis-aws-foundations-benchmark/v/1.4.0"

  depends_on = [aws_securityhub_account.main]
}
