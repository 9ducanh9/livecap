# ECS Cluster, Task Definition, and Service

# ECS Cluster
resource "aws_ecs_cluster" "main" {
  name = "${var.project_name}-cluster-${var.environment}"

  setting {
    name  = "containerInsights"
    value = "disabled"
  }

  tags = merge(
    var.tags,
    {
      Name        = "${var.project_name}-cluster-${var.environment}"
      Environment = var.environment
    }
  )
}

# ECS Task Definition
resource "aws_ecs_task_definition" "backend" {
  family                   = "${var.project_name}-backend-${var.environment}"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.ecs_task_cpu
  memory                   = var.ecs_task_memory
  execution_role_arn       = aws_iam_role.ecs_task_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([
    {
      name      = "${var.project_name}-backend"
      image     = "${aws_ecr_repository.backend.repository_url}:${var.backend_image_tag}"
      essential = true

      portMappings = [
        {
          containerPort = var.container_port
          protocol      = "tcp"
        }
      ]

      environment = [
        {
          name  = "AWS_REGION"
          value = var.aws_region
        },
        {
          name  = "S3_BUCKET"
          value = aws_s3_bucket.transcript.id
        },
        {
          name  = "DOWNLOAD_LINK_EXPIRATION"
          value = tostring(var.download_link_expiration_seconds)
        },
        {
          name  = "SESSION_TIMEOUT"
          value = tostring(var.session_timeout_seconds)
        },
        {
          name  = "MAX_SPEAKERS"
          value = tostring(var.max_speakers)
        },
        {
          name  = "MAX_CONCURRENT_SESSIONS"
          value = tostring(var.max_concurrent_sessions)
        },
        {
          name  = "MAX_SESSIONS_PER_IP"
          value = tostring(var.max_sessions_per_ip)
        },
        {
          name  = "TRANSCRIBE_LANGUAGE_CODE"
          value = "vi-VN"
        },
        {
          name  = "BILINGUAL_DUAL_STREAM"
          value = "true"
        },
        {
          name  = "AUDIO_PIPELINE_DEBUG"
          value = "false"
        },
        {
          name  = "ALLOWED_ORIGIN"
          value = local.frontend_allowed_origin
        },
        {
          name  = "CLOUDWATCH_LOG_GROUP"
          value = aws_cloudwatch_log_group.backend.name
        },
        {
          name  = "ENABLE_IDLE_SCALE_DOWN"
          value = tostring(var.enable_idle_scale_down)
        },
        {
          name  = "IDLE_SCALE_DOWN_GRACE_SECONDS"
          value = tostring(var.idle_scale_down_grace_seconds)
        },
        {
          name  = "ECS_CLUSTER_NAME"
          value = aws_ecs_cluster.main.name
        },
        {
          name  = "ECS_SERVICE_NAME"
          value = "${var.project_name}-backend-service-${var.environment}"
        }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.backend.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "ecs"
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
    }
  ])

  tags = merge(
    var.tags,
    {
      Name        = "${var.project_name}-backend-task-${var.environment}"
      Environment = var.environment
    }
  )

  # Freeze the blue task revision during migration. The target service owns all
  # new application and image changes.
  lifecycle {
    ignore_changes = [
      container_definitions,
      cpu,
      memory,
      execution_role_arn,
      task_role_arn,
    ]
  }
}

# ECS Service
resource "aws_ecs_service" "backend" {
  name            = "${var.project_name}-backend-service-${var.environment}"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.backend.arn
  desired_count   = var.backend_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = local.ecs_subnet_ids
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = local.assign_public_ip
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.backend.arn
    container_name   = "${var.project_name}-backend"
    container_port   = var.container_port
  }

  health_check_grace_period_seconds = 60

  deployment_maximum_percent         = 200
  deployment_minimum_healthy_percent = 100

  # Keep the blue service on its current revision and desired count throughout
  # the rollback window.
  lifecycle {
    ignore_changes = [
      desired_count,
      task_definition,
    ]
  }

  tags = merge(
    var.tags,
    {
      Name        = "${var.project_name}-backend-service-${var.environment}"
      Environment = var.environment
    }
  )

  # Depend on HTTPS listener if certificate provided, otherwise HTTP dev listener
  depends_on = [
    aws_lb_listener.https,
    aws_lb_listener.http_dev
  ]
}

# Legacy autoscaling is constrained to one task during the rollback window.
resource "aws_appautoscaling_target" "ecs_target" {
  max_capacity       = var.legacy_backend_max_capacity
  min_capacity       = var.legacy_backend_min_capacity
  resource_id        = "service/${aws_ecs_cluster.main.name}/${aws_ecs_service.backend.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

resource "aws_appautoscaling_scheduled_action" "ecs_demo_up" {
  count = var.enable_legacy_scheduled_scaling ? 1 : 0

  name               = "${var.project_name}-demo-up-${var.environment}"
  service_namespace  = aws_appautoscaling_target.ecs_target.service_namespace
  resource_id        = aws_appautoscaling_target.ecs_target.resource_id
  scalable_dimension = aws_appautoscaling_target.ecs_target.scalable_dimension
  schedule           = var.demo_scale_up_schedule_expression
  timezone           = var.demo_scaling_timezone

  scalable_target_action {
    min_capacity = 1
    max_capacity = 1
  }
}

resource "aws_appautoscaling_scheduled_action" "ecs_demo_down" {
  count = var.enable_legacy_scheduled_scaling ? 1 : 0

  name               = "${var.project_name}-demo-down-${var.environment}"
  service_namespace  = aws_appautoscaling_target.ecs_target.service_namespace
  resource_id        = aws_appautoscaling_target.ecs_target.resource_id
  scalable_dimension = aws_appautoscaling_target.ecs_target.scalable_dimension
  schedule           = var.demo_scale_down_schedule_expression
  timezone           = var.demo_scaling_timezone

  scalable_target_action {
    min_capacity = 0
    max_capacity = 1
  }
}

# Auto Scaling Policy - CPU
resource "aws_appautoscaling_policy" "ecs_cpu_policy" {
  name               = "${var.project_name}-cpu-autoscaling-${var.environment}"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.ecs_target.resource_id
  scalable_dimension = aws_appautoscaling_target.ecs_target.scalable_dimension
  service_namespace  = aws_appautoscaling_target.ecs_target.service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }

    target_value       = var.autoscaling_target_cpu
    scale_in_cooldown  = 300
    scale_out_cooldown = 60
  }
}

# Auto Scaling Policy - Memory
resource "aws_appautoscaling_policy" "ecs_memory_policy" {
  name               = "${var.project_name}-memory-autoscaling-${var.environment}"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.ecs_target.resource_id
  scalable_dimension = aws_appautoscaling_target.ecs_target.scalable_dimension
  service_namespace  = aws_appautoscaling_target.ecs_target.service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageMemoryUtilization"
    }

    target_value       = var.autoscaling_target_memory
    scale_in_cooldown  = 300
    scale_out_cooldown = 60
  }
}

# Target task definition and service. These resources run in the dedicated
# private subnets while the legacy service remains available for rollback.

resource "aws_ecs_task_definition" "target_backend" {
  family                   = "${var.project_name}-target-backend-${var.environment}"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.ecs_task_cpu
  memory                   = var.ecs_task_memory
  execution_role_arn       = aws_iam_role.ecs_task_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([
    {
      name      = "${var.project_name}-backend"
      image     = "${aws_ecr_repository.backend.repository_url}:${var.backend_image_tag}"
      essential = true

      portMappings = [
        {
          containerPort = var.container_port
          protocol      = "tcp"
        }
      ]

      environment = [
        {
          name  = "AWS_REGION"
          value = var.aws_region
        },
        {
          name  = "S3_BUCKET"
          value = aws_s3_bucket.transcript.id
        },
        {
          name  = "DOWNLOAD_LINK_EXPIRATION"
          value = tostring(var.download_link_expiration_seconds)
        },
        {
          name  = "SESSION_TIMEOUT"
          value = tostring(var.session_timeout_seconds)
        },
        {
          name  = "MAX_SPEAKERS"
          value = tostring(var.max_speakers)
        },
        {
          name  = "MAX_CONCURRENT_SESSIONS"
          value = tostring(var.max_concurrent_sessions)
        },
        {
          name  = "MAX_SESSIONS_PER_IP"
          value = tostring(var.max_sessions_per_ip)
        },
        {
          name  = "TRANSCRIBE_LANGUAGE_CODE"
          value = "vi-VN"
        },
        {
          name  = "BILINGUAL_DUAL_STREAM"
          value = "true"
        },
        {
          name  = "AUDIO_PIPELINE_DEBUG"
          value = "false"
        },
        {
          name  = "ALLOWED_ORIGIN"
          value = local.frontend_allowed_origin
        },
        {
          name  = "CLOUDWATCH_LOG_GROUP"
          value = aws_cloudwatch_log_group.backend.name
        },
        {
          name  = "ENABLE_IDLE_SCALE_DOWN"
          value = tostring(var.target_enable_idle_scale_down)
        },
        {
          name  = "IDLE_SCALE_DOWN_GRACE_SECONDS"
          value = tostring(var.idle_scale_down_grace_seconds)
        },
        {
          name  = "ECS_CLUSTER_NAME"
          value = aws_ecs_cluster.main.name
        },
        {
          name  = "ECS_SERVICE_NAME"
          value = "${var.project_name}-target-service-${var.environment}"
        }
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
    }
  ])

  tags = merge(
    var.tags,
    {
      Name        = "${var.project_name}-target-task-${var.environment}"
      Environment = var.environment
      Migration   = "blue-green-target"
    }
  )
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

  health_check_grace_period_seconds = 60

  deployment_maximum_percent         = 200
  deployment_minimum_healthy_percent = 100

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  lifecycle {
    ignore_changes = [desired_count]
  }

  tags = merge(
    var.tags,
    {
      Name        = "${var.project_name}-target-service-${var.environment}"
      Environment = var.environment
      Migration   = "blue-green-target"
    }
  )

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
