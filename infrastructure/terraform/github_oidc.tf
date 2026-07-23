# GitHub Actions uses short-lived AWS credentials through OIDC. The trust
# policy is intentionally limited to this repository's deployment branches;
# pull requests, tags, forks, and other repositories cannot assume the role.

locals {
  github_repository = "9ducanh9/livecap"
  github_oidc_subjects = [
    "repo:${local.github_repository}:ref:refs/heads/main",
    "repo:${local.github_repository}:ref:refs/heads/Update",
  ]

  terraform_state_bucket_arn = "arn:${data.aws_partition.current.partition}:s3:::livecap-terraform-state-dev-${data.aws_caller_identity.current.account_id}"
  terraform_state_key        = "livecap/main/terraform.tfstate"
}

resource "aws_iam_openid_connect_provider" "github_actions" {
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]

  tags = merge(var.tags, {
    Name = "${var.project_name}-github-actions-oidc"
  })
}

data "aws_iam_policy_document" "github_actions_assume_role" {
  statement {
    sid     = "GitHubActionsFromLiveCapBranches"
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github_actions.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = local.github_oidc_subjects
    }
  }
}

resource "aws_iam_role" "github_actions_plan" {
  name                 = "${var.project_name}-github-actions-plan-${var.environment}"
  description          = "GitHub Actions build and Terraform plan role for LiveCap"
  assume_role_policy   = data.aws_iam_policy_document.github_actions_assume_role.json
  max_session_duration = 3600

  tags = merge(var.tags, {
    Name        = "${var.project_name}-github-actions-plan-${var.environment}"
    Environment = var.environment
  })
}

# Terraform refreshes many AWS resource types while producing a plan. AWS's
# managed ReadOnlyAccess policy supplies metadata reads only; all required
# data-plane and write permissions are scoped explicitly below.
resource "aws_iam_role_policy_attachment" "github_actions_read_only" {
  role       = aws_iam_role.github_actions_plan.name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/ReadOnlyAccess"
}

data "aws_iam_policy_document" "github_actions_build_and_plan" {
  statement {
    sid       = "ECRLogin"
    effect    = "Allow"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  statement {
    sid    = "PushLiveCapBackendImages"
    effect = "Allow"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:BatchGetImage",
      "ecr:CompleteLayerUpload",
      "ecr:GetDownloadUrlForLayer",
      "ecr:InitiateLayerUpload",
      "ecr:PutImage",
      "ecr:UploadLayerPart",
    ]
    resources = [aws_ecr_repository.backend.arn]
  }

  statement {
    sid       = "ListTerraformStatePrefix"
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = [local.terraform_state_bucket_arn]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values = [
        local.terraform_state_key,
        "${local.terraform_state_key}.tflock",
      ]
    }
  }

  statement {
    sid     = "ReadTerraformState"
    effect  = "Allow"
    actions = ["s3:GetObject"]
    resources = [
      "${local.terraform_state_bucket_arn}/${local.terraform_state_key}",
      "${local.terraform_state_bucket_arn}/${local.terraform_state_key}.tflock",
    ]
  }

  statement {
    sid    = "LockTerraformStateDuringPlan"
    effect = "Allow"
    actions = [
      "s3:DeleteObject",
      "s3:PutObject",
    ]
    resources = [
      "${local.terraform_state_bucket_arn}/${local.terraform_state_key}.tflock",
    ]
  }

  statement {
    sid     = "ReadLiveCapStripeSecretVersionsForRefresh"
    effect  = "Allow"
    actions = ["secretsmanager:GetSecretValue"]
    resources = [
      "arn:${data.aws_partition.current.partition}:secretsmanager:${var.aws_region}:${data.aws_caller_identity.current.account_id}:secret:${var.project_name}-stripe-secret-key-${var.environment}-*",
      "arn:${data.aws_partition.current.partition}:secretsmanager:${var.aws_region}:${data.aws_caller_identity.current.account_id}:secret:${var.project_name}-stripe-webhook-secret-${var.environment}-*",
    ]
  }
}

resource "aws_iam_role_policy" "github_actions_build_and_plan" {
  name   = "${var.project_name}-github-actions-build-plan-${var.environment}"
  role   = aws_iam_role.github_actions_plan.id
  policy = data.aws_iam_policy_document.github_actions_build_and_plan.json
}
