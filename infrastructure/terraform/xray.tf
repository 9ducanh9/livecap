# Optional AWS X-Ray tracing (C4).
#
# Off by default. When enabled it adds an X-Ray daemon sidecar to the backend
# task, grants the task role permission to publish traces, and sets ENABLE_XRAY
# so the app configures the SDK (see backend/app/tracing.py). The app traces
# HTTP routes + AWS SDK calls; the WebSocket route is intentionally not traced.
#
# NOTE (verify before enabling): X-Ray tracing has not been validated against a
# live daemon here. Enable in a non-critical environment first and confirm
# traces appear in the X-Ray console. Consider pinning the daemon image by
# digest for supply-chain parity with the app image.

variable "enable_xray" {
  description = "Enable AWS X-Ray tracing: X-Ray daemon sidecar + task-role publish permission + ENABLE_XRAY on the app."
  type        = bool
  default     = true
}

locals {
  xray_sidecar_containers = var.enable_xray ? [{
    name      = "xray-daemon"
    image     = "public.ecr.aws/xray/aws-xray-daemon:latest"
    essential = false

    portMappings = [{
      containerPort = 2000
      protocol      = "udp"
    }]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.backend.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "xray"
      }
    }
  }] : []
}

resource "aws_iam_role_policy" "xray_access" {
  count = var.enable_xray ? 1 : 0

  name = "${var.project_name}-xray-access"
  role = aws_iam_role.ecs_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "xray:PutTraceSegments",
          "xray:PutTelemetryRecords"
        ]
        Resource = "*"
      }
    ]
  })
}
