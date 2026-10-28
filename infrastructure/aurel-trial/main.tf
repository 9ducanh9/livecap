terraform {
  required_version = ">= 1.13"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.0"
    }

  }
}
provider "aws" {
  region              = "ap-southeast-1"
  allowed_account_ids = ["050916357263"]
  default_tags {
    tags = { Project = "LiveCap", Environment = "aurel-trial", ManagedBy = "Terraform" }
  }
}
variable "certificate_arn" {
  type = string
}
variable "image" {
  type = string
}
variable "desired_count" {
  type    = number
  default = 0
}
variable "google_client_id" {
  type    = string
  default = ""
}
variable "deepseek_api_key" {
  type      = string
  sensitive = true
  default   = ""
}
variable "livekit_url" { type = string }
variable "livekit_api_key" {
  type = string
  sensitive = true
}
variable "livekit_api_secret" {
  type = string
  sensitive = true
}
resource "aws_secretsmanager_secret" "livekit" {
  name = "livecap-aurel-trial-livekit"
}
resource "aws_secretsmanager_secret_version" "livekit" {
  secret_id = aws_secretsmanager_secret.livekit.id
  secret_string = jsonencode({ key = var.livekit_api_key, secret = var.livekit_api_secret })
}
resource "aws_iam_role_policy" "livekit" {
  role = aws_iam_role.execution.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect = "Allow", Action = ["secretsmanager:GetSecretValue"],
    Resource = aws_secretsmanager_secret.livekit.arn
  }] })
}
resource "aws_secretsmanager_secret" "deepseek" {
  name = "livecap-aurel-trial-deepseek"
}
resource "aws_secretsmanager_secret_version" "deepseek" {
  secret_id     = aws_secretsmanager_secret.deepseek.id
  secret_string = var.deepseek_api_key
}
resource "aws_iam_role_policy" "deepseek" {
  role = aws_iam_role.execution.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect = "Allow", Action = ["secretsmanager:GetSecretValue"],
    Resource = aws_secretsmanager_secret.deepseek.arn
  }] })
}
variable "google_client_secret" {
  type      = string
  default   = ""
  sensitive = true
}
locals {
  name     = "livecap-aurel-trial"
  frontend = "https://livecap-aurel.vercel.app"
  trust    = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = { Service = "ecs-tasks.amazonaws.com" }, Action = "sts:AssumeRole" }] })
}
data "aws_vpc" "default" {
  default = true
}
data "aws_subnets" "public" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
  filter {

    name   = "default-for-az"
    values = ["true"]
  }
}
resource "aws_ecr_repository" "backend" {
  name                 = local.name
  image_tag_mutability = "IMMUTABLE"
  image_scanning_configuration {
    scan_on_push = true
  }
  force_delete = true
}
resource "aws_s3_bucket" "transcripts" {
  bucket        = "${local.name}-transcripts-050916357263"
  force_destroy = false
}
resource "aws_s3_bucket_public_access_block" "transcripts" {
  bucket                  = aws_s3_bucket.transcripts.id
  block_public_acls       = true
  ignore_public_acls      = true
  block_public_policy     = true
  restrict_public_buckets = true
}
resource "aws_s3_bucket_server_side_encryption_configuration" "transcripts" {
  bucket = aws_s3_bucket.transcripts.id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}
resource "aws_s3_bucket_lifecycle_configuration" "transcripts" {
  bucket = aws_s3_bucket.transcripts.id
  rule {
    id     = "expire-trial-transcripts"
    status = "Enabled"
    filter {

    }
    expiration {
      days = 1
    }

  }
}
resource "aws_dynamodb_table" "usage" {
  name         = "${local.name}-usage"
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
}
resource "aws_dynamodb_table" "history" {
  name         = "${local.name}-history"
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
}
resource "aws_cognito_user_pool" "users" {
  name                     = local.name
  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]
  password_policy {
    minimum_length    = 12
    require_lowercase = true
    require_uppercase = true
    require_numbers   = true
    require_symbols   = true

  }
}
resource "aws_cognito_user_pool_client" "web" {
  name                                 = local.name
  user_pool_id                         = aws_cognito_user_pool.users.id
  generate_secret                      = false
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["openid", "email", "profile", "aws.cognito.signin.user.admin"]
  supported_identity_providers         = var.google_client_id == "" ? ["COGNITO"] : ["COGNITO", "Google"]
  callback_urls                        = ["${local.frontend}/app", "http://localhost:5173/app"]
  logout_urls                          = ["${local.frontend}/app", "http://localhost:5173/app"]
  explicit_auth_flows                  = ["ALLOW_USER_PASSWORD_AUTH", "ALLOW_USER_SRP_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"]
  prevent_user_existence_errors        = "ENABLED"
  depends_on                           = [aws_cognito_identity_provider.google]
}
resource "aws_cognito_identity_provider" "google" {
  count         = var.google_client_id == "" ? 0 : 1
  user_pool_id  = aws_cognito_user_pool.users.id
  provider_name = "Google"
  provider_type = "Google"
  provider_details = {
    client_id        = var.google_client_id
    client_secret    = var.google_client_secret
    authorize_scopes = "openid email profile"
  }
  attribute_mapping = {
    email    = "email"
    username = "sub"
  }
}
resource "aws_cognito_user_pool_domain" "login" {
  domain       = "livecap-aurel-trial-050916357263"
  user_pool_id = aws_cognito_user_pool.users.id
}
resource "aws_cloudwatch_log_group" "backend" {
  name              = "/livecap/aurel-trial"
  retention_in_days = 3
}
resource "aws_iam_role" "execution" {
  name               = "${local.name}-execution"
  assume_role_policy = local.trust
}
resource "aws_iam_role_policy" "execution" {
  role = aws_iam_role.execution.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = ["ecr:GetAuthorizationToken"], Resource = "*" },
    { Effect = "Allow", Action = ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer", "ecr:BatchCheckLayerAvailability"], Resource = aws_ecr_repository.backend.arn },
    { Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"], Resource = "${aws_cloudwatch_log_group.backend.arn}:*"
    }
  ] })
}
resource "aws_iam_role" "task" {
  name               = "${local.name}-task"
  assume_role_policy = local.trust
}
resource "aws_iam_role_policy" "task" {
  role = aws_iam_role.task.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = ["transcribe:StartStreamTranscription", "transcribe:StartStreamTranscriptionWebSocket", "translate:TranslateText"], Resource = "*" },
    { Effect = "Allow", Action = ["cognito-idp:GetUser", "cognito-idp:AdminListGroupsForUser"], Resource = aws_cognito_user_pool.users.arn },
    { Effect = "Allow", Action = ["s3:ListBucket"], Resource = aws_s3_bucket.transcripts.arn },
    { Effect = "Allow", Action = ["s3:PutObject", "s3:GetObject", "s3:DeleteObject"], Resource = "${aws_s3_bucket.transcripts.arn}/*" },
    { Effect = "Allow", Action = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:Query", "dynamodb:DeleteItem"], Resource = [aws_dynamodb_table.usage.arn, aws_dynamodb_table.history.arn, aws_dynamodb_table.rooms.arn] },
    { Effect = "Allow", Action = ["ivs:CreateStage"], Resource = "*", Condition = { StringEquals = { "aws:RequestTag/app" = "livecap" } } },
    { Effect = "Allow", Action = ["ivs:TagResource"], Resource = "arn:aws:ivs:us-east-1:050916357263:stage/*" },
    { Effect = "Allow", Action = ["ivs:CreateParticipantToken", "ivs:DeleteStage"], Resource = "arn:aws:ivs:us-east-1:050916357263:stage/*", Condition = { StringEquals = { "aws:ResourceTag/app" = "livecap" } } },
    { Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents", "logs:DescribeLogStreams"], Resource = "${aws_cloudwatch_log_group.backend.arn}:*" },
    { Effect = "Allow", Action = ["logs:DescribeLogGroups"], Resource = "*"
    }
  ] })
}
resource "aws_security_group" "alb" {
  name   = "${local.name}-alb"
  vpc_id = data.aws_vpc.default.id
  ingress {
    protocol    = "tcp"
    from_port   = 443
    to_port     = 443
    cidr_blocks = ["0.0.0.0/0"]
  }
  egress {
    protocol        = "tcp"
    from_port       = 8000
    to_port         = 8000
    security_groups = [aws_security_group.task.id]
  }
}
resource "aws_security_group" "task" {
  name   = "${local.name}-task"
  vpc_id = data.aws_vpc.default.id
  egress {
    protocol    = "-1"
    from_port   = 0
    to_port     = 0
    cidr_blocks = ["0.0.0.0/0"]
  }
}
resource "aws_security_group_rule" "backend" {
  type                     = "ingress"
  protocol                 = "tcp"
  from_port                = 8000
  to_port                  = 8000
  security_group_id        = aws_security_group.task.id
  source_security_group_id = aws_security_group.alb.id
}
resource "aws_lb" "backend" {
  name               = local.name
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = data.aws_subnets.public.ids
  idle_timeout       = 300
}
resource "aws_lb_target_group" "backend" {
  name                 = local.name
  port                 = 8000
  protocol             = "HTTP"
  target_type          = "ip"
  vpc_id               = data.aws_vpc.default.id
  deregistration_delay = 10
  health_check {
    path    = "/api/health"
    matcher = "200"
  }
}
resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.backend.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = var.certificate_arn
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.backend.arn
  }
}
resource "aws_ecs_cluster" "backend" {
  name = local.name
}
resource "aws_dynamodb_table" "rooms" {
  name = "livecap-aurel-trial-rooms"
  billing_mode = "PAY_PER_REQUEST"
  hash_key = "room_code"
  range_key = "record_key"
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
    enabled = true
  }
}
resource "aws_ecs_task_definition" "backend" {
  depends_on = [aws_secretsmanager_secret_version.deepseek, aws_iam_role_policy.deepseek, aws_secretsmanager_secret_version.livekit, aws_iam_role_policy.livekit]
  family                   = local.name
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "512"
  memory                   = "1024"
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn
  container_definitions = jsonencode([{
    name         = "backend", image = var.image, essential = true,
    portMappings = [{ containerPort = 8000, protocol = "tcp" }],
    environment = [for k, v in {
      AWS_REGION                        = "ap-southeast-1", S3_BUCKET = aws_s3_bucket.transcripts.id,
      ALLOWED_ORIGIN                    = local.frontend, FRONTEND_BASE_URL = local.frontend,
      ENABLE_AUTH                       = "true", COGNITO_USER_POOL_ID = aws_cognito_user_pool.users.id,
      TRANSCRIPT_HISTORY_TABLE_NAME     = aws_dynamodb_table.history.name,
      TRANSCRIPT_HISTORY_RETENTION_DAYS = "1", USAGE_TABLE_NAME = aws_dynamodb_table.usage.name,
      CLOUDWATCH_LOG_GROUP              = aws_cloudwatch_log_group.backend.name,
      SESSION_TIMEOUT                   = "300", MAX_CONCURRENT_SESSIONS = "2", MAX_SESSIONS_PER_IP = "1",
      BILINGUAL_DUAL_STREAM             = "true", ENABLE_IDLE_SCALE_DOWN = "false",
      ENABLE_SHARED_ROOMS               = "true", ENABLE_ROOM_SCREEN_SHARE = "true",
      ROOM_TABLE_NAME = aws_dynamodb_table.rooms.name, ROOM_RETENTION_DAYS = "1",
      IVS_REALTIME_REGION = "us-east-1", IVS_PARTICIPANT_TOKEN_SECONDS = "300",
      ROOM_MEDIA_PROVIDER = "livekit", LIVEKIT_URL = var.livekit_url,
      ENABLE_MEETING_SUMMARY            = "true", ENABLE_STRIPE_BILLING = "false"
    } : { name = k, value = v }],
    secrets = [
      { name = "DEEPSEEK_API_KEY", valueFrom = aws_secretsmanager_secret.deepseek.arn },
      { name = "LIVEKIT_API_KEY", valueFrom = "${aws_secretsmanager_secret.livekit.arn}:key::" },
      { name = "LIVEKIT_API_SECRET", valueFrom = "${aws_secretsmanager_secret.livekit.arn}:secret::" }
    ],
    logConfiguration = { logDriver = "awslogs", options = { "awslogs-group" = aws_cloudwatch_log_group.backend.name, "awslogs-region" = "ap-southeast-1", "awslogs-stream-prefix" = "ecs" }
    }
  }])
}
resource "aws_ecs_service" "backend" {
  name                              = local.name
  cluster                           = aws_ecs_cluster.backend.id
  task_definition                   = aws_ecs_task_definition.backend.arn
  desired_count                     = var.desired_count
  launch_type                       = "FARGATE"
  platform_version                  = "LATEST"
  health_check_grace_period_seconds = 60
  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }
  network_configuration {
    subnets          = data.aws_subnets.public.ids
    security_groups  = [aws_security_group.task.id]
    assign_public_ip = true

  }
  load_balancer {
    target_group_arn = aws_lb_target_group.backend.arn
    container_name   = "backend"
    container_port   = 8000
  }
  depends_on = [aws_lb_listener.https, aws_iam_role_policy.execution, aws_iam_role_policy.task]
}
output "repository" {
  value = aws_ecr_repository.backend.repository_url
}
output "alb_dns" {
  value = aws_lb.backend.dns_name
}
output "cognito_client_id" {
  value = aws_cognito_user_pool_client.web.id
}
output "cognito_pool_id" {
  value = aws_cognito_user_pool.users.id
}
output "cognito_domain" {
  value = "https://${aws_cognito_user_pool_domain.login.domain}.auth.ap-southeast-1.amazoncognito.com"
}
output "transcript_bucket" {
  value = aws_s3_bucket.transcripts.id
}
