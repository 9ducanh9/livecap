# Optional product accounts and owner-scoped transcript history (C5).
#
# The entire feature is off by default. When enabled, Cognito performs browser
# sign-in through its Hosted UI and the backend validates access tokens with
# cognito-idp:GetUser. Transcript bodies remain in the private S3 bucket; this
# DynamoDB table only stores the owning user and S3 object metadata.

variable "enable_cognito_auth" {
  description = "Enable Cognito sign-in and per-user transcript history. Requires an explicit reviewed apply and frontend Cognito build configuration."
  type        = bool
  default     = false
}

variable "cognito_callback_urls" {
  description = "Allowed OAuth callback URLs for the browser SPA. Include the production /app URL before enabling."
  type        = list(string)
  default     = ["http://localhost:5173/app"]
}

variable "cognito_logout_urls" {
  description = "Allowed Cognito Hosted UI sign-out return URLs."
  type        = list(string)
  default     = ["http://localhost:5173/app"]
}

variable "cognito_domain_prefix" {
  description = "Optional globally unique Cognito Hosted UI domain prefix. Set before enabling browser sign-in."
  type        = string
  default     = ""
}

variable "transcript_history_retention_days" {
  description = "How long per-user transcript history metadata remains. Keep aligned with transcript S3 lifecycle retention."
  type        = number
  default     = 14
}

locals {
  transcript_history_table_name = "${var.project_name}-transcript-history-${var.environment}"
}

resource "aws_cognito_user_pool" "livecap" {
  count = var.enable_cognito_auth ? 1 : 0

  name                     = "${var.project_name}-users-${var.environment}"
  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]

  password_policy {
    minimum_length    = 12
    require_lowercase = true
    require_numbers   = true
    require_symbols   = true
    require_uppercase = true
  }

  verification_message_template {
    default_email_option = "CONFIRM_WITH_CODE"
  }

  tags = merge(var.tags, {
    Name        = "${var.project_name}-users-${var.environment}"
    Environment = var.environment
  })
}

resource "aws_cognito_user_pool_client" "web" {
  count = var.enable_cognito_auth ? 1 : 0

  name                                 = "${var.project_name}-web-${var.environment}"
  user_pool_id                         = aws_cognito_user_pool.livecap[0].id
  generate_secret                      = false
  prevent_user_existence_errors        = "ENABLED"
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["openid", "email", "profile"]
  callback_urls                        = var.cognito_callback_urls
  logout_urls                          = var.cognito_logout_urls
  supported_identity_providers         = ["COGNITO"]

  lifecycle {
    precondition {
      condition     = trimspace(var.cognito_domain_prefix) != ""
      error_message = "cognito_domain_prefix is required when enable_cognito_auth is true so the browser can use Cognito Hosted UI."
    }
  }
}

resource "aws_cognito_user_pool_domain" "hosted_ui" {
  count = var.enable_cognito_auth && trimspace(var.cognito_domain_prefix) != "" ? 1 : 0

  domain       = var.cognito_domain_prefix
  user_pool_id = aws_cognito_user_pool.livecap[0].id
}

resource "aws_dynamodb_table" "transcript_history" {
  count = var.enable_cognito_auth ? 1 : 0

  name         = local.transcript_history_table_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "user_id"
  range_key    = "history_id"

  attribute {
    name = "user_id"
    type = "S"
  }

  attribute {
    name = "history_id"
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
    Name        = local.transcript_history_table_name
    Environment = var.environment
  })
}

resource "aws_iam_role_policy" "cognito_history_access" {
  count = var.enable_cognito_auth ? 1 : 0

  name = "${var.project_name}-cognito-history-${var.environment}"
  role = aws_iam_role.ecs_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["cognito-idp:GetUser"]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:GetItem",
          "dynamodb:Query"
        ]
        Resource = aws_dynamodb_table.transcript_history[0].arn
      }
    ]
  })
}

output "cognito_user_pool_id" {
  description = "Cognito User Pool ID when account features are enabled. Supply it to the frontend build as VITE_COGNITO_USER_POOL_ID."
  value       = try(aws_cognito_user_pool.livecap[0].id, null)
}

output "cognito_web_client_id" {
  description = "Public browser client ID when account features are enabled."
  value       = try(aws_cognito_user_pool_client.web[0].id, null)
}

output "transcript_history_table_name" {
  description = "DynamoDB table containing owner-scoped export metadata when account features are enabled."
  value       = try(aws_dynamodb_table.transcript_history[0].name, null)
}
