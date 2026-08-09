# DeepSeek API key for the optional meeting-summary feature (see
# backend/app/services/summarization.py). Real credential, so it goes into
# Secrets Manager like the Stripe secrets in stripe_billing.tf, rather than a
# plaintext task-definition environment variable.

locals {
  deepseek_secret_configured = var.enable_meeting_summary && trimspace(var.deepseek_api_key) != ""
}

resource "aws_secretsmanager_secret" "deepseek_api_key" {
  count = local.deepseek_secret_configured ? 1 : 0

  name = "${var.project_name}-deepseek-api-key-${var.environment}"
  tags = merge(var.tags, {
    Name        = "${var.project_name}-deepseek-api-key-${var.environment}"
    Environment = var.environment
  })
}

resource "aws_secretsmanager_secret_version" "deepseek_api_key" {
  count = local.deepseek_secret_configured ? 1 : 0

  secret_id     = aws_secretsmanager_secret.deepseek_api_key[0].id
  secret_string = var.deepseek_api_key
}

# The ECS *execution* role (not the task role) needs this -- it's what
# resolves `secrets` entries in the container definition at task launch.
resource "aws_iam_role_policy" "deepseek_secret_access" {
  count = local.deepseek_secret_configured ? 1 : 0

  name = "${var.project_name}-deepseek-secret-access"
  role = aws_iam_role.ecs_task_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["secretsmanager:GetSecretValue"]
        Resource = [aws_secretsmanager_secret.deepseek_api_key[0].arn]
      }
    ]
  })
}
