# GitHub Actions uses short-lived AWS credentials through OIDC. The trust
# policy is intentionally limited to this repository's deployment branches;
# pull requests, tags, forks, and other repositories cannot assume the role.

locals {
  github_repository = "9ducanh9/livecap"
  github_oidc_subjects = [
    "repo:${local.github_repository}:ref:refs/heads/main",
  ]

  terraform_state_bucket_arn = "arn:${data.aws_partition.current.partition}:s3:::livecap-terraform-state-dev-${data.aws_caller_identity.current.account_id}"
  terraform_state_key        = "livecap/main/terraform.tfstate"

  github_deploy_service_arns = [
    "arn:${data.aws_partition.current.partition}:ecs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:service/${var.project_name}-cluster-${var.environment}/${var.project_name}-target-service-${var.environment}",
  ]
  github_deploy_task_role_arns = [
    "arn:${data.aws_partition.current.partition}:iam::${data.aws_caller_identity.current.account_id}:role/${var.project_name}-ecs-task-${var.environment}",
    "arn:${data.aws_partition.current.partition}:iam::${data.aws_caller_identity.current.account_id}:role/${var.project_name}-ecs-task-execution-${var.environment}",
  ]
  github_frontend_bucket_arn       = "arn:${data.aws_partition.current.partition}:s3:::${var.project_name}-frontend-${var.environment}-${data.aws_caller_identity.current.account_id}"
  github_frontend_distribution_arn = "arn:${data.aws_partition.current.partition}:cloudfront::${data.aws_caller_identity.current.account_id}:distribution/E39ADG0ES17RP1"
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
    sid     = "ReadLiveCapSecretVersionsForRefresh"
    effect  = "Allow"
    actions = ["secretsmanager:GetSecretValue"]
    resources = [
      "arn:${data.aws_partition.current.partition}:secretsmanager:${var.aws_region}:${data.aws_caller_identity.current.account_id}:secret:${var.project_name}-stripe-secret-key-${var.environment}-*",
      "arn:${data.aws_partition.current.partition}:secretsmanager:${var.aws_region}:${data.aws_caller_identity.current.account_id}:secret:${var.project_name}-stripe-webhook-secret-${var.environment}-*",
      "arn:${data.aws_partition.current.partition}:secretsmanager:${var.aws_region}:${data.aws_caller_identity.current.account_id}:secret:${var.project_name}-deepseek-api-key-${var.environment}-*",
    ]
  }
}

resource "aws_iam_role_policy" "github_actions_build_and_plan" {
  name   = "${var.project_name}-github-actions-build-plan-${var.environment}"
  role   = aws_iam_role.github_actions_plan.id
  policy = data.aws_iam_policy_document.github_actions_build_and_plan.json
}

# Application delivery is deliberately separate from the plan role. It can
# release an immutable image and static frontend, but cannot create, modify, or
# delete general infrastructure resources.
resource "aws_iam_role" "github_actions_deploy" {
  name                 = "${var.project_name}-github-actions-deploy-${var.environment}"
  description          = "GitHub Actions application delivery role for LiveCap"
  assume_role_policy   = data.aws_iam_policy_document.github_actions_assume_role.json
  max_session_duration = 3600

  tags = merge(var.tags, {
    Name        = "${var.project_name}-github-actions-deploy-${var.environment}"
    Environment = var.environment
  })
}

resource "aws_iam_role_policy_attachment" "github_actions_deploy_read_only" {
  role       = aws_iam_role.github_actions_deploy.name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/ReadOnlyAccess"
}

data "aws_iam_policy_document" "github_actions_deploy" {
  source_policy_documents = [data.aws_iam_policy_document.github_actions_build_and_plan.json]

  statement {
    sid       = "UpdateTerraformStateAfterDelivery"
    effect    = "Allow"
    actions   = ["s3:PutObject"]
    resources = ["${local.terraform_state_bucket_arn}/${local.terraform_state_key}"]
  }

  statement {
    sid    = "RegisterLiveCapTaskDefinitions"
    effect = "Allow"
    actions = [
      "ecs:DeregisterTaskDefinition",
      "ecs:DescribeTaskDefinition",
      "ecs:RegisterTaskDefinition",
      "ecs:TagResource",
    ]
    resources = ["*"]
  }

  statement {
    sid       = "UpdateLiveCapServices"
    effect    = "Allow"
    actions   = ["ecs:UpdateService"]
    resources = local.github_deploy_service_arns
  }

  statement {
    sid       = "PassOnlyLiveCapTaskRoles"
    effect    = "Allow"
    actions   = ["iam:PassRole"]
    resources = local.github_deploy_task_role_arns

    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["ecs-tasks.amazonaws.com"]
    }
  }

  statement {
    sid       = "DeployFrontendObjects"
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = [local.github_frontend_bucket_arn]
  }

  statement {
    sid    = "DeployFrontendAssets"
    effect = "Allow"
    actions = [
      "s3:DeleteObject",
      "s3:GetObject",
      "s3:PutObject",
    ]
    resources = ["${local.github_frontend_bucket_arn}/*"]
  }

  statement {
    sid       = "InvalidateLiveCapFrontend"
    effect    = "Allow"
    actions   = ["cloudfront:CreateInvalidation", "cloudfront:GetInvalidation"]
    resources = [local.github_frontend_distribution_arn]
  }
}

resource "aws_iam_role_policy" "github_actions_deploy" {
  name   = "${var.project_name}-github-actions-deploy-${var.environment}"
  role   = aws_iam_role.github_actions_deploy.id
  policy = data.aws_iam_policy_document.github_actions_deploy.json
}
