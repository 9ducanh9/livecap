# Durable LiveCap Rooms metadata and finalized-caption archive.
#
# The viewer WebSocket fan-out remains process-local in this preview batch, but
# room metadata and finalized captions survive ECS scale-to-zero. No raw audio
# or partial captions are stored.

variable "room_live_ttl_seconds" {
  description = "Seconds a newly created room accepts live captions before it is automatically ended."
  type        = number
  default     = 14400

  validation {
    condition     = var.room_live_ttl_seconds >= 300
    error_message = "room_live_ttl_seconds must be at least 300 seconds."
  }
}

variable "room_retention_days" {
  description = "Days finalized room captions remain available through the room code, link, or QR after the meeting ends."
  type        = number
  default     = 14

  validation {
    condition     = var.room_retention_days >= 1
    error_message = "room_retention_days must be at least 1 day."
  }
}

variable "room_max_segments" {
  description = "Maximum finalized caption segments retained per room."
  type        = number
  default     = 500

  validation {
    condition     = var.room_max_segments >= 10
    error_message = "room_max_segments must be at least 10."
  }
}

locals {
  room_events_table_name = "${var.project_name}-room-events-${var.environment}"
}

resource "aws_dynamodb_table" "room_events" {
  count = var.preview_enable_shared_rooms ? 1 : 0

  name         = local.room_events_table_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "room_code"
  range_key    = "record_key"

  attribute {
    name = "room_code"
    type = "S"
  }

  attribute {
    name = "record_key"
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
    Name        = local.room_events_table_name
    Environment = var.environment
    Purpose     = "Finalized LiveCap room captions"
  })
}

resource "aws_iam_role_policy" "room_events_access" {
  count = var.preview_enable_shared_rooms ? 1 : 0

  name = "${var.project_name}-room-events-access-${var.environment}"
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
        Resource = aws_dynamodb_table.room_events[0].arn
      }
    ]
  })
}

output "room_events_table_name" {
  description = "DynamoDB table containing room metadata and finalized captions for the isolated Rooms preview."
  value       = try(aws_dynamodb_table.room_events[0].name, null)
}
