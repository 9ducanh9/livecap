# IAM Roles and Policies for ECS

# ECS Task Execution Role (for ECR and CloudWatch)
resource "aws_iam_role" "ecs_task_execution" {
  name = "${var.project_name}-ecs-task-execution-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = merge(
    var.tags,
    {
      Name        = "${var.project_name}-ecs-task-execution-${var.environment}"
      Environment = var.environment
    }
  )
}

# Attach AWS managed policy for ECS task execution
resource "aws_iam_role_policy_attachment" "ecs_task_execution_policy" {
  role       = aws_iam_role.ecs_task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# ECS Task Role (for application-level AWS service access)
resource "aws_iam_role" "ecs_task" {
  name = "${var.project_name}-ecs-task-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = merge(
    var.tags,
    {
      Name        = "${var.project_name}-ecs-task-${var.environment}"
      Environment = var.environment
    }
  )
}

# Policy for Transcript Bucket access (read/write)
resource "aws_iam_role_policy" "transcript_bucket_access" {
  name = "${var.project_name}-transcript-bucket-access"
  role = aws_iam_role.ecs_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:GetObject",
          "s3:DeleteObject",
          "s3:ListBucket"
        ]
        Resource = [
          aws_s3_bucket.transcript.arn,
          "${aws_s3_bucket.transcript.arn}/*"
        ]
      }
    ]
  })
}

# Policy for Amazon Transcribe Streaming
resource "aws_iam_role_policy" "transcribe_access" {
  name = "${var.project_name}-transcribe-access"
  role = aws_iam_role.ecs_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "transcribe:StartStreamTranscription",
          "transcribe:StartStreamTranscriptionWebSocket"
        ]
        Resource = "*"
      }
    ]
  })
}

# Policy for Amazon Translate
resource "aws_iam_role_policy" "translate_access" {
  name = "${var.project_name}-translate-access"
  role = aws_iam_role.ecs_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "translate:TranslateText"
        ]
        Resource = "*"
      }
    ]
  })
}

# Policy for the optional Amazon Bedrock meeting-summary feature. Only created
# when enable_meeting_summary is true, keeping the task role least-privilege by
# default. Scoped to foundation models (InvokeModel only).
resource "aws_iam_role_policy" "bedrock_access" {
  count = var.enable_meeting_summary ? 1 : 0

  name = "${var.project_name}-bedrock-access"
  role = aws_iam_role.ecs_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel"
        ]
        Resource = [
          "arn:aws:bedrock:*::foundation-model/*"
        ]
      }
    ]
  })
}

# Policy for the optional text-to-speech feature (A2, Amazon Polly). Only
# created when enable_tts is true.
resource "aws_iam_role_policy" "polly_access" {
  count = var.enable_tts ? 1 : 0

  name = "${var.project_name}-polly-access"
  role = aws_iam_role.ecs_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["polly:SynthesizeSpeech"]
        Resource = "*"
      }
    ]
  })
}

# Policy for the optional text-analysis feature (A3, Amazon Comprehend). Only
# created when enable_text_analysis is true.
resource "aws_iam_role_policy" "comprehend_access" {
  count = var.enable_text_analysis ? 1 : 0

  name = "${var.project_name}-comprehend-access"
  role = aws_iam_role.ecs_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "comprehend:DetectSentiment",
          "comprehend:DetectKeyPhrases"
        ]
        Resource = "*"
      }
    ]
  })
}

# Policy for optional backend idle scale-to-zero.
resource "aws_iam_role_policy" "ecs_idle_scale_down_access" {
  name = "${var.project_name}-ecs-idle-scale-down-access"
  role = aws_iam_role.ecs_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ecs:UpdateService"
        ]
        Resource = concat(
          [aws_ecs_service.target_backend.id],
          var.enable_preview_backend ? [aws_ecs_service.preview_backend[0].id] : [],
        )
      }
    ]
  })
}

# Policy for CloudWatch Logs (application logging)
resource "aws_iam_role_policy" "cloudwatch_logs_access" {
  name = "${var.project_name}-cloudwatch-logs-access"
  role = aws_iam_role.ecs_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents",
          "logs:DescribeLogStreams"
        ]
        Resource = [
          aws_cloudwatch_log_group.backend.arn,
          "${aws_cloudwatch_log_group.backend.arn}:*"
        ]
      }
    ]
  })
}

# Note: Frontend_Bucket access is explicitly NOT granted to task role
# to enforce bucket isolation per security requirements
