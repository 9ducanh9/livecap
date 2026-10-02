resource "aws_cloudwatch_log_group" "benchmark" {
  name              = "/ecs/${local.prefix}-backend"
  retention_in_days = var.log_retention_days
}
resource "aws_iam_role" "benchmark" {
  for_each = toset(["execution", "task"])
  name     = "${local.prefix}-${each.key}"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Action = "sts:AssumeRole", Principal = { Service = "ecs-tasks.amazonaws.com" } }]
  })
}
resource "aws_iam_role_policy" "benchmark_execution" {
  name = "${local.prefix}-execution"
  role = aws_iam_role.benchmark["execution"].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["ecr:GetAuthorizationToken"], Resource = "*" },
      { Effect = "Allow", Action = ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer", "ecr:BatchCheckLayerAvailability"], Resource = aws_ecr_repository.benchmark.arn },
      { Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"], Resource = "${aws_cloudwatch_log_group.benchmark.arn}:*" }
    ]
  })
}
resource "aws_iam_role_policy" "benchmark_task" {
  name = "${local.prefix}-task"
  role = aws_iam_role.benchmark["task"].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["transcribe:StartStreamTranscription", "transcribe:StartStreamTranscriptionWebSocket", "translate:TranslateText"], Resource = "*" },
      { Effect = "Allow", Action = ["cognito-idp:GetUser"], Resource = "*" },
      { Effect = "Allow", Action = ["cognito-idp:AdminListGroupsForUser"], Resource = aws_cognito_user_pool.benchmark.arn },
      { Effect = "Allow", Action = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:DeleteItem", "dynamodb:Scan", "dynamodb:Query"], Resource = [for t in aws_dynamodb_table.benchmark : t.arn] },
      { Effect = "Allow", Action = ["s3:ListBucket"], Resource = aws_s3_bucket.benchmark.arn },
      { Effect = "Allow", Action = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"], Resource = "${aws_s3_bucket.benchmark.arn}/*" },
      { Effect = "Allow", Action = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents", "logs:DescribeLogStreams"], Resource = [aws_cloudwatch_log_group.benchmark.arn, "${aws_cloudwatch_log_group.benchmark.arn}:*"] }
    ]
  })
}
resource "aws_ecs_cluster" "benchmark" {
  name = "${local.prefix}-cluster"
  setting {
    name  = "containerInsights"
    value = "disabled"
  }
}
locals {
  runtime_env = {
    AWS_REGION                        = var.aws_region
    S3_BUCKET                         = aws_s3_bucket.benchmark.id
    SESSION_TIMEOUT                   = "1800"
    SESSION_TTL_SECONDS               = "3600"
    MAX_CONCURRENT_SESSIONS           = "4"
    MAX_SESSIONS_PER_IP               = tostring(var.max_sessions_per_ip)
    SESSION_STORE_BACKEND             = "dynamodb"
    SESSION_TABLE_NAME                = aws_dynamodb_table.benchmark["sessions"].name
    USAGE_TABLE_NAME                  = aws_dynamodb_table.benchmark["usage"].name
    ENABLE_USAGE_QUOTA                = "true"
    TRANSCRIPT_HISTORY_TABLE_NAME     = aws_dynamodb_table.benchmark["transcript-history"].name
    TRANSCRIPT_HISTORY_RETENTION_DAYS = "3"
    ROOM_TABLE_NAME                   = aws_dynamodb_table.benchmark["room-events"].name
    ADMIN_AUDIT_TABLE_NAME            = aws_dynamodb_table.benchmark["admin-audit"].name
    ENABLE_AUTH                       = "true"
    COGNITO_USER_POOL_ID              = aws_cognito_user_pool.benchmark.id
    CLOUDWATCH_LOG_GROUP              = aws_cloudwatch_log_group.benchmark.name
    CLOUDWATCH_LOG_STREAM             = "benchmark-application"
    ECS_CLUSTER_NAME                  = aws_ecs_cluster.benchmark.name
    ECS_SERVICE_NAME                  = "${local.prefix}-service"
    ALLOWED_ORIGIN                    = "http://localhost:5173"
    FRONTEND_BASE_URL                 = "http://localhost:5173"
    TRANSCRIBE_LANGUAGE_CODE          = "vi-VN"
    BILINGUAL_DUAL_STREAM             = "true"
    AUDIO_PIPELINE_DEBUG              = "false"
    ENABLE_IDLE_SCALE_DOWN            = "false"
    ENABLE_MEETING_SUMMARY            = "false"
    ENABLE_STRIPE_BILLING             = "false"
    ENABLE_TTS                        = "false"
    ENABLE_TEXT_ANALYSIS              = "false"
    ENABLE_XRAY                       = "false"
    ENABLE_SHARED_ROOMS               = "false"
    ENABLE_ROOM_SCREEN_SHARE          = "false"
    TRANSCRIBE_VOCABULARY_NAME_EN     = ""
    TRANSCRIBE_VOCABULARY_NAME_VI     = ""
  }
}
resource "aws_ecs_task_definition" "benchmark" {
  family                   = "${local.prefix}-backend"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "512"
  memory                   = "1024"
  execution_role_arn       = aws_iam_role.benchmark["execution"].arn
  task_role_arn            = aws_iam_role.benchmark["task"].arn
  runtime_platform {
    cpu_architecture        = "X86_64"
    operating_system_family = "LINUX"
  }
  container_definitions = jsonencode([{
    name      = "${local.prefix}-backend"
    image     = "${aws_ecr_repository.benchmark.repository_url}:${var.image_git_sha}-amd64"
    essential = true
    # Uvicorn HTTP access records contain peer IPs; omit them in benchmark telemetry.
    command      = ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
    portMappings = [{ containerPort = 8000, protocol = "tcp" }]
    environment  = [for k, v in local.runtime_env : { name = k, value = v }]
    secrets      = []
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.benchmark.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "benchmark-ecs"
        "mode"                  = "non-blocking"
        "max-buffer-size"       = "25m"
      }
    }
    healthCheck = {
      command     = ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health', timeout=4)"]
      interval    = 30
      timeout     = 5
      retries     = 3
      startPeriod = 60
    }
    stopTimeout = 30
  }])
  depends_on = [terraform_data.benchmark_guard]
}
resource "aws_ecs_service" "benchmark" {
  name             = "${local.prefix}-service"
  cluster          = aws_ecs_cluster.benchmark.id
  task_definition  = aws_ecs_task_definition.benchmark.arn
  desired_count    = 1
  launch_type      = "FARGATE"
  platform_version = "1.4.0"
  network_configuration {
    subnets          = var.shared_private_subnet_ids
    security_groups  = [aws_security_group.benchmark_tasks.id]
    assign_public_ip = false
  }
  load_balancer {
    target_group_arn = aws_lb_target_group.benchmark.arn
    container_name   = "${local.prefix}-backend"
    container_port   = 8000
  }
  health_check_grace_period_seconds  = 60
  deployment_maximum_percent         = 200
  deployment_minimum_healthy_percent = 100
  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }
  depends_on = [aws_lb_listener.benchmark, aws_iam_role_policy.benchmark_execution, aws_iam_role_policy.benchmark_task]
}
resource "aws_appautoscaling_target" "benchmark" {
  min_capacity       = 1
  max_capacity       = 1
  resource_id        = "service/${aws_ecs_cluster.benchmark.name}/${aws_ecs_service.benchmark.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}
