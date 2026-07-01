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
