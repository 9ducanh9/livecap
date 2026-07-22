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
        }
      ],
      var.enable_usage_quota ? [
        {
          Effect   = "Allow"
          Action   = ["dynamodb:Scan"]
          Resource = aws_dynamodb_table.usage[0].arn
        }
      ] : []
    )
  })
}

output "admin_group_name" {
  description = "Cognito group name that grants /admin dashboard access."
  value       = try(aws_cognito_user_group.admin[0].name, null)
}
