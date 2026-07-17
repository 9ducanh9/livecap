# Shared active-session store (DynamoDB).
#
# Optional (enable_dynamodb_session_store). When enabled, the backend keeps the
# active-session limits in this table instead of process-local memory, so the
# limits hold across tasks. This is the prerequisite for running more than one
# backend task. On-demand billing keeps idle cost near zero; a TTL attribute
# reclaims rows left by crashed tasks.

variable "enable_dynamodb_session_store" {
  description = "Use a shared DynamoDB table for active-session limits instead of process-local memory. Required before running more than one backend task."
  type        = bool
  default     = false
}

variable "session_ttl_seconds" {
  description = "TTL (seconds) for DynamoDB session rows; reclaims rows left by crashed tasks. Keep above the session timeout."
  type        = number
  default     = 3600
}

locals {
  session_table_name = "${var.project_name}-sessions-${var.environment}"
}

resource "aws_dynamodb_table" "sessions" {
  count = var.enable_dynamodb_session_store ? 1 : 0

  name         = local.session_table_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"

  attribute {
    name = "pk"
    type = "S"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  point_in_time_recovery {
    enabled = false
  }

  tags = merge(
    var.tags,
    {
      Name        = local.session_table_name
      Environment = var.environment
    }
  )
}

# Task-role access to the session table (only when enabled).
resource "aws_iam_role_policy" "session_store_access" {
  count = var.enable_dynamodb_session_store ? 1 : 0

  name = "${var.project_name}-session-store-access"
  role = aws_iam_role.ecs_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:DeleteItem",
          "dynamodb:Scan",
          "dynamodb:Query"
        ]
        Resource = [
          aws_dynamodb_table.sessions[0].arn
        ]
      }
    ]
  })
}
