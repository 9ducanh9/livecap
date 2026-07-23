# Admin dashboard: a Cognito "admin" group plus the minimal extra task-role IAM
# GET /api/admin/overview needs (list every Cognito user, scan the usage table,
# and check ECS service health). Gated on enable_cognito_auth — an admin
# dashboard has nothing to show without accounts enabled, so there is no
# separate flag; membership in the "admin" group (not a flag) is what gates
# the API route itself (see backend/app/services/auth.py::require_admin_user).

resource "aws_cognito_user_group" "admin" {
  count = var.enable_cognito_auth ? 1 : 0

  name         = "admin"
  user_pool_id = aws_cognito_user_pool.livecap[0].id
  description  = "Members can access /admin (all-user usage, revenue estimate, system health). Add with: aws cognito-idp admin-add-user-to-group."
}

resource "aws_iam_role_policy" "admin_dashboard_access" {
  count = var.enable_cognito_auth ? 1 : 0

  name = "${var.project_name}-admin-dashboard-${var.environment}"
  role = aws_iam_role.ecs_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat(
      [
        {
          Effect = "Allow"
          Action = [
            "cognito-idp:AdminListGroupsForUser",
            "cognito-idp:ListUsers",
          ]
          Resource = aws_cognito_user_pool.livecap[0].arn
        },
        {
          Effect = "Allow"
          Action = ["ecs:DescribeServices"]
          Resource = concat(
            [aws_ecs_service.target_backend.id],
            var.enable_preview_backend ? [aws_ecs_service.preview_backend[0].id] : [],
          )
        },
        {
          # DescribeAlarms is a list operation with no per-alarm request
          # target, so it does not support resource-level scoping.
          Effect   = "Allow"
          Action   = ["cloudwatch:DescribeAlarms"]
          Resource = "*"
        },
        {
          # Cost Explorer does not support resource-level IAM permissions;
          # AWS requires calls in us-east-1 regardless of deployment region.
          Effect   = "Allow"
          Action   = ["ce:GetCostAndUsage"]
          Resource = "*"
        }
      ],
      var.enable_usage_quota ? [
        {
          Effect   = "Allow"
          Action   = ["dynamodb:Scan"]
          Resource = aws_dynamodb_table.usage[0].arn
        }
      ] : [],
      # Admin audit table: PutItem for recording actions, Query for reading entries
      [
        {
          Effect = "Allow"
          Action = [
            "dynamodb:PutItem",
            "dynamodb:Query",
          ]
          Resource = aws_dynamodb_table.admin_audit[0].arn
        }
      ]
    )
  })
}

output "admin_group_name" {
  description = "Cognito group name that grants /admin dashboard access."
  value       = try(aws_cognito_user_group.admin[0].name, null)
}

# --- Admin Audit DynamoDB Table ---
# Stores audit log entries for admin mutating actions (disable, enable,
# reset_password, change_tier). PK: TARGET#{username}, SK: TS#{timestamp}#{uuid}.
# TTL expires entries after 365 days. Gated on enable_cognito_auth.

locals {
  admin_audit_table_name = "${var.project_name}-admin-audit-${var.environment}"
}

resource "aws_dynamodb_table" "admin_audit" {
  count = var.enable_cognito_auth ? 1 : 0

  name         = local.admin_audit_table_name
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
    attribute_name = "ttl"
    enabled        = true
  }

  point_in_time_recovery {
    enabled = false
  }

  tags = merge(var.tags, {
    Name    = local.admin_audit_table_name
    Feature = "admin-panel"
  })
}

output "admin_audit_table_name" {
  description = "DynamoDB table for admin action audit logging."
  value       = try(aws_dynamodb_table.admin_audit[0].name, null)
}
