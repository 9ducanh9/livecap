# CloudWatch Log Groups for Backend Application Logs

resource "aws_cloudwatch_log_group" "backend" {
  name              = "/ecs/${var.project_name}-backend-${var.environment}"
  retention_in_days = var.log_retention_days

  tags = merge(
    var.tags,
    {
      Name        = "${var.project_name}-backend-logs-${var.environment}"
      Environment = var.environment
    }
  )
}

# Watchtower application log group. The backend's logging_service creates this
# group at runtime via watchtower (create_log_group=True), which leaves it with
# no retention policy (AWS default: never expire). Managing it here applies an
# explicit retention policy and closes the documented "Known Boundary".
#
# This group usually already exists in the account, so import it before the
# first apply to avoid a "log group already exists" error:
#
#   terraform import aws_cloudwatch_log_group.watchtower livecap
#
# If the deployed task now logs to aws_cloudwatch_log_group.backend instead and
# this group is stale, prefer deleting it during clean-up rather than retaining
# it. Set manage_watchtower_log_group = false to skip managing it entirely.
resource "aws_cloudwatch_log_group" "watchtower" {
  count = var.manage_watchtower_log_group ? 1 : 0

  name              = var.watchtower_log_group_name
  retention_in_days = var.log_retention_days

  tags = merge(
    var.tags,
    {
      Name        = "${var.project_name}-watchtower-logs-${var.environment}"
      Environment = var.environment
    }
  )
}

# Legacy placeholder log group. ALB access logs are not enabled by this
# resource; real ALB access logging requires an S3 bucket configuration.
resource "aws_cloudwatch_log_group" "alb" {
  name              = "/aws/alb/${var.project_name}-${var.environment}"
  retention_in_days = var.log_retention_days

  tags = merge(
    var.tags,
    {
      Name        = "${var.project_name}-alb-logs-${var.environment}"
      Environment = var.environment
    }
  )
}
