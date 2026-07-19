# Stripe subscription billing for the Pro/Business tiers (see
# backend/app/services/stripe_billing.py and docs in COLLAB_LOG.md).
#
# Off by default. Two secrets (the Stripe secret key and the webhook signing
# secret) are stored in Secrets Manager rather than plaintext task-definition
# environment variables, since unlike everything else in ecs.tf's environment
# block, these are real credentials. Price IDs are not secret, so they stay
# as plain environment variables.
#
# The two Stripe Price IDs referenced by stripe_price_id_pro/business must
# already exist in the connected Stripe account with a `livecap_tier`
# metadata key ("pro"/"business") on the Price — that mapping is how
# stripe_billing.py resolves a webhook's Price back to a LiveCap tier without
# hardcoding IDs in application code.

variable "enable_stripe_billing" {
  description = "Enable Stripe subscription billing endpoints (checkout, portal, webhook)."
  type        = bool
  default     = false
}

variable "stripe_secret_key" {
  description = "Stripe secret API key (sk_...). Sensitive — set via a local .tfvars file that is never committed."
  type        = string
  default     = ""
  sensitive   = true
}

variable "stripe_webhook_secret" {
  description = "Stripe webhook signing secret (whsec_...) for the /api/billing/webhook endpoint. Sensitive."
  type        = string
  default     = ""
  sensitive   = true
}

variable "stripe_price_id_pro" {
  description = "Stripe Price ID for the Pro tier subscription (not secret)."
  type        = string
  default     = ""
}

variable "stripe_price_id_business" {
  description = "Stripe Price ID for the Business tier subscription (not secret)."
  type        = string
  default     = ""
}

locals {
  frontend_base_url = var.custom_domain != "" ? "https://${var.custom_domain}" : "https://${aws_cloudfront_distribution.frontend.domain_name}"

  stripe_secrets_configured = var.enable_stripe_billing && trimspace(var.stripe_secret_key) != "" && trimspace(var.stripe_webhook_secret) != ""
}

resource "aws_secretsmanager_secret" "stripe_secret_key" {
  count = local.stripe_secrets_configured ? 1 : 0

  name = "${var.project_name}-stripe-secret-key-${var.environment}"
  tags = merge(var.tags, {
    Name        = "${var.project_name}-stripe-secret-key-${var.environment}"
    Environment = var.environment
  })
}

resource "aws_secretsmanager_secret_version" "stripe_secret_key" {
  count = local.stripe_secrets_configured ? 1 : 0

  secret_id     = aws_secretsmanager_secret.stripe_secret_key[0].id
  secret_string = var.stripe_secret_key
}

resource "aws_secretsmanager_secret" "stripe_webhook_secret" {
  count = local.stripe_secrets_configured ? 1 : 0

  name = "${var.project_name}-stripe-webhook-secret-${var.environment}"
  tags = merge(var.tags, {
    Name        = "${var.project_name}-stripe-webhook-secret-${var.environment}"
    Environment = var.environment
  })
}

resource "aws_secretsmanager_secret_version" "stripe_webhook_secret" {
  count = local.stripe_secrets_configured ? 1 : 0

  secret_id     = aws_secretsmanager_secret.stripe_webhook_secret[0].id
  secret_string = var.stripe_webhook_secret
}

# The ECS *execution* role (not the task role) needs this — it's what
# resolves `secrets` entries in the container definition at task launch.
resource "aws_iam_role_policy" "stripe_secrets_access" {
  count = local.stripe_secrets_configured ? 1 : 0

  name = "${var.project_name}-stripe-secrets-access"
  role = aws_iam_role.ecs_task_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = ["secretsmanager:GetSecretValue"]
        Resource = [
          aws_secretsmanager_secret.stripe_secret_key[0].arn,
          aws_secretsmanager_secret.stripe_webhook_secret[0].arn,
        ]
      }
    ]
  })
}
