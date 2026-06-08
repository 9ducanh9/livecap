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

# Optional: CloudWatch Log Group for ALB access logs
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
