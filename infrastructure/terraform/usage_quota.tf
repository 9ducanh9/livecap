# Per-user monthly usage tracking for B2C quota enforcement.
#
# Tracks sessions and transcription minutes per user per month. The backend
# checks this table before allowing new sessions and after sessions end.
# PAY_PER_REQUEST keeps idle cost near zero; TTL cleans up old monthly records.

variable "enable_usage_quota" {
  description = "Create the usage tracking DynamoDB table and wire it into the ECS task environment."
  type        = bool
  default     = false
}

variable "usage_quota_ttl_days" {
  description = "Days after which old monthly usage records are automatically deleted."
  type        = number
  default     = 90
}

locals {
  usage_table_name = "${var.project_name}-usage-${var.environment}"
}

resource "aws_dynamodb_table" "usage" {
  count = var.enable_usage_quota ? 1 : 0

  name         = local.usage_table_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"
  range_key    = "sk"

  attribute {
    name = "pk"
    type = "S"
  }

  attribute {
    name = "sk"
    type = "S"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  point_in_time_recovery {
    enabled = false
  }

  tags = merge(var.tags, {
    Name        = local.usage_table_name
    Environment = var.environment
  })
}

# Task-role access to the usage table.
resource "aws_iam_role_policy" "usage_quota_access" {
  count = var.enable_usage_quota ? 1 : 0

  name = "${var.project_name}-usage-quota-access"
  role = aws_iam_role.ecs_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:Query"
        ]
        Resource = [
          aws_dynamodb_table.usage[0].arn
        ]
      }
    ]
  })
}

output "usage_table_name" {
  description = "DynamoDB table for per-user monthly usage tracking."
  value       = try(aws_dynamodb_table.usage[0].name, null)
}
