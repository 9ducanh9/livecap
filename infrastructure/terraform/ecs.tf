# ECS cluster, task definition, service, and autoscaling for the dedicated VPC.

resource "aws_ecs_cluster" "main" {
  name = "${var.project_name}-cluster-${var.environment}"

  setting {
    name  = "containerInsights"
    value = var.enable_container_insights ? "enabled" : "disabled"
  }

  tags = merge(var.tags, {
    Name        = "${var.project_name}-cluster-${var.environment}"
    Environment = var.environment
  })
}

resource "aws_ecs_task_definition" "target_backend" {
  family                   = "${var.project_name}-target-backend-${var.environment}"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.ecs_task_cpu
  memory                   = var.ecs_task_memory
  execution_role_arn       = aws_iam_role.ecs_task_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  # CPU architecture. Switch to ARM64 (Graviton, ~20% cheaper) only alongside an
  # arm64 image build; the pushed image arch must match this value.
  runtime_platform {
    cpu_architecture        = var.task_cpu_architecture
    operating_system_family = "LINUX"
  }

  container_definitions = jsonencode([{
    name      = "${var.project_name}-backend"
    image     = "${aws_ecr_repository.backend.repository_url}:${var.backend_image_tag}"
    essential = true

    portMappings = [{
      containerPort = var.container_port
      protocol      = "tcp"
    }]

    environment = [
      { name = "AWS_REGION", value = var.aws_region },
      { name = "S3_BUCKET", value = aws_s3_bucket.transcript.id },
      { name = "DOWNLOAD_LINK_EXPIRATION", value = tostring(var.download_link_expiration_seconds) },
      { name = "SESSION_TIMEOUT", value = tostring(var.session_timeout_seconds) },
      { name = "MAX_CONCURRENT_SESSIONS", value = tostring(var.max_concurrent_sessions) },
      { name = "MAX_SESSIONS_PER_IP", value = tostring(var.max_sessions_per_ip) },
      { name = "TRANSCRIBE_LANGUAGE_CODE", value = "vi-VN" },
      { name = "BILINGUAL_DUAL_STREAM", value = "true" },
      { name = "AUDIO_PIPELINE_DEBUG", value = "false" },
      { name = "ALLOWED_ORIGIN", value = local.frontend_allowed_origin },
      { name = "CLOUDWATCH_LOG_GROUP", value = aws_cloudwatch_log_group.backend.name },
      { name = "ENABLE_IDLE_SCALE_DOWN", value = tostring(var.target_enable_idle_scale_down) },
      { name = "IDLE_SCALE_DOWN_GRACE_SECONDS", value = tostring(var.idle_scale_down_grace_seconds) },
      { name = "ECS_CLUSTER_NAME", value = aws_ecs_cluster.main.name },
      { name = "ECS_SERVICE_NAME", value = "${var.project_name}-target-service-${var.environment}" },
      { name = "ENABLE_MEETING_SUMMARY", value = tostring(var.enable_meeting_summary) },
      { name = "BEDROCK_MODEL_ID", value = var.bedrock_model_id },
      { name = "BEDROCK_REGION", value = var.bedrock_region },
      { name = "SESSION_STORE_BACKEND", value = var.enable_dynamodb_session_store ? "dynamodb" : "memory" },
      { name = "SESSION_TABLE_NAME", value = local.session_table_name },
      { name = "SESSION_TTL_SECONDS", value = tostring(var.session_ttl_seconds) },
      { name = "TRANSCRIBE_VOCABULARY_NAME_EN", value = local.transcribe_vocabulary_name_en },
      { name = "TRANSCRIBE_VOCABULARY_NAME_VI", value = local.transcribe_vocabulary_name_vi },
      { name = "ENABLE_TTS", value = tostring(var.enable_tts) },
      { name = "TTS_VOICE_ID_EN", value = var.tts_voice_id_en },
      { name = "ENABLE_TEXT_ANALYSIS", value = tostring(var.enable_text_analysis) },
    ]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.backend.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "target-ecs"
      }
    }

    healthCheck = {
      command     = ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://localhost:${var.container_port}${var.health_check_path}', timeout=4)\" || exit 1"]
      interval    = 30
      timeout     = 5
      retries     = 3
      startPeriod = 60
    }

    stopTimeout = 30
  }])

  tags = merge(var.tags, {
    Name        = "${var.project_name}-target-task-${var.environment}"
    Environment = var.environment
    Migration   = "blue-green-target"
  })
}

resource "aws_ecs_service" "target_backend" {
  name            = "${var.project_name}-target-service-${var.environment}"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.target_backend.arn
  desired_count   = var.target_backend_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = [for subnet in aws_subnet.target_private : subnet.id]
    security_groups  = [aws_security_group.target_ecs_tasks.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.target_backend.arn
    container_name   = "${var.project_name}-backend"
    container_port   = var.container_port
  }

  health_check_grace_period_seconds  = 60
  deployment_maximum_percent         = 200
  deployment_minimum_healthy_percent = 100

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  lifecycle {
    ignore_changes = [desired_count]
  }

  tags = merge(var.tags, {
    Name        = "${var.project_name}-target-service-${var.environment}"
    Environment = var.environment
    Migration   = "blue-green-target"
  })

  depends_on = [
    aws_lb_listener.target_https,
    aws_lb_listener.target_http_dev,
    aws_nat_gateway.target,
  ]
}

resource "aws_appautoscaling_target" "target_ecs" {
  max_capacity       = var.backend_max_capacity
  min_capacity       = var.backend_min_capacity
  resource_id        = "service/${aws_ecs_cluster.main.name}/${aws_ecs_service.target_backend.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

resource "aws_appautoscaling_scheduled_action" "target_demo_up" {
  count = var.enable_demo_scheduled_scaling ? 1 : 0

  name               = "${var.project_name}-target-demo-up-${var.environment}"
  service_namespace  = aws_appautoscaling_target.target_ecs.service_namespace
  resource_id        = aws_appautoscaling_target.target_ecs.resource_id
  scalable_dimension = aws_appautoscaling_target.target_ecs.scalable_dimension
  schedule           = var.demo_scale_up_schedule_expression
  timezone           = var.demo_scaling_timezone

  scalable_target_action {
    min_capacity = 1
    max_capacity = 1
  }
}

resource "aws_appautoscaling_scheduled_action" "target_demo_down" {
  count = var.enable_demo_scheduled_scaling ? 1 : 0

  name               = "${var.project_name}-target-demo-down-${var.environment}"
  service_namespace  = aws_appautoscaling_target.target_ecs.service_namespace
  resource_id        = aws_appautoscaling_target.target_ecs.resource_id
  scalable_dimension = aws_appautoscaling_target.target_ecs.scalable_dimension
  schedule           = var.demo_scale_down_schedule_expression
  timezone           = var.demo_scaling_timezone

  scalable_target_action {
    min_capacity = 0
    max_capacity = 1
  }
}

resource "aws_appautoscaling_policy" "target_ecs_cpu" {
  name               = "${var.project_name}-target-cpu-${var.environment}"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.target_ecs.resource_id
  scalable_dimension = aws_appautoscaling_target.target_ecs.scalable_dimension
  service_namespace  = aws_appautoscaling_target.target_ecs.service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }

    target_value       = var.autoscaling_target_cpu
    scale_in_cooldown  = 300
    scale_out_cooldown = 60
  }
}

resource "aws_appautoscaling_policy" "target_ecs_memory" {
  name               = "${var.project_name}-target-memory-${var.environment}"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.target_ecs.resource_id
  scalable_dimension = aws_appautoscaling_target.target_ecs.scalable_dimension
  service_namespace  = aws_appautoscaling_target.target_ecs.service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageMemoryUtilization"
    }

    target_value       = var.autoscaling_target_memory
    scale_in_cooldown  = 300
    scale_out_cooldown = 60
  }
}
