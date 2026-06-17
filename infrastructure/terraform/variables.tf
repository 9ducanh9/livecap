# Variables for LiveCap Infrastructure

variable "aws_region" {
  description = "AWS region for resource deployment"
  type        = string
  default     = "ap-southeast-1"
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "project_name" {
  description = "Project name used for resource naming"
  type        = string
  default     = "livecap"
}

# S3 Configuration
variable "transcript_retention_days" {
  description = "Number of days to retain transcript files in S3 before automatic deletion"
  type        = number
  default     = 14
}

variable "frontend_bucket_name" {
  description = "Name for the S3 bucket hosting frontend static assets (must be globally unique)"
  type        = string
  default     = "" # Will be generated if not provided
}

variable "transcript_bucket_name" {
  description = "Name for the S3 bucket storing transcript exports (must be globally unique)"
  type        = string
  default     = "" # Will be generated if not provided
}

# ECS Configuration
variable "ecs_task_cpu" {
  description = "CPU units for ECS task (256, 512, 1024, 2048, 4096)"
  type        = number
  default     = 512
}

variable "ecs_task_memory" {
  description = "Memory (MiB) for ECS task (512, 1024, 2048, 3072, 4096, etc.)"
  type        = number
  default     = 1024
}

variable "backend_desired_count" {
  description = "Desired number of ECS backend tasks. Use 0 outside active demo/use windows."
  type        = number
  default     = 0
}

variable "backend_min_capacity" {
  description = "Minimum ECS backend tasks for autoscaling. Use 0 for scale-to-zero."
  type        = number
  default     = 0
}

variable "backend_max_capacity" {
  description = "Maximum ECS backend tasks for autoscaling. Keep at 1 while session limits are in-memory."
  type        = number
  default     = 1
}

variable "container_port" {
  description = "Port exposed by the backend container"
  type        = number
  default     = 8000
}

# Application Configuration
variable "session_timeout_seconds" {
  description = "Maximum duration for a transcription session in seconds"
  type        = number
  default     = 1800 # 30 minutes
}

variable "download_link_expiration_seconds" {
  description = "Expiration time for S3 presigned download URLs in seconds"
  type        = number
  default     = 86400 # 24 hours
}

variable "max_speakers" {
  description = "Maximum number of speakers for diarization"
  type        = number
  default     = 5
}

variable "max_concurrent_sessions" {
  description = "Process-local maximum active WebSocket sessions. Keep ECS max capacity at 1 while this is in-memory."
  type        = number
  default     = 4
}

variable "max_sessions_per_ip" {
  description = "Process-local maximum active WebSocket sessions from one client IP."
  type        = number
  default     = 1
}

variable "monthly_budget_limit_usd" {
  description = "Monthly AWS Budget cost threshold in USD."
  type        = number
  default     = 50
}

variable "budget_notification_email" {
  description = "Email address for AWS Budget alerts. Leave empty to skip creating the budget notification."
  type        = string
  default     = ""
}

variable "enable_demo_scheduled_scaling" {
  description = "Enable demo-safe scheduled scaling for the ECS service."
  type        = bool
  default     = true
}

variable "demo_scale_up_schedule_expression" {
  description = "Application Auto Scaling schedule expression for demo hours. Default is 08:00 Asia/Saigon, Monday-Friday."
  type        = string
  default     = "cron(0 8 ? * MON-FRI *)"
}

variable "demo_scale_down_schedule_expression" {
  description = "Application Auto Scaling schedule expression for off hours. Default is 19:00 Asia/Saigon, Monday-Friday."
  type        = string
  default     = "cron(0 19 ? * MON-FRI *)"
}

variable "demo_scaling_timezone" {
  description = "Timezone used by the demo scheduled scaling expressions."
  type        = string
  default     = "Asia/Ho_Chi_Minh"
}

variable "enable_idle_scale_down" {
  description = "Allow the backend process to request ECS desired_count=0 after the last session ends and the grace period expires."
  type        = bool
  default     = false
}

variable "idle_scale_down_grace_seconds" {
  description = "Seconds to wait after the last active session ends before the backend requests ECS scale-to-zero."
  type        = number
  default     = 300
}

variable "enable_wake_endpoint" {
  description = "Create a public Lambda Function URL that wakes the ECS backend from scale-to-zero. Keep disabled until reviewed because it can start paid ECS capacity."
  type        = bool
  default     = false
}

variable "wake_endpoint_timeout_seconds" {
  description = "Lambda timeout for the ECS wake endpoint."
  type        = number
  default     = 15
}

# Health Check Configuration
variable "health_check_path" {
  description = "Path for ALB health checks"
  type        = string
  default     = "/api/health"
}

variable "health_check_interval" {
  description = "Health check interval in seconds"
  type        = number
  default     = 30
}

variable "health_check_timeout" {
  description = "Health check timeout in seconds"
  type        = number
  default     = 5
}

variable "healthy_threshold" {
  description = "Number of consecutive health checks successes required"
  type        = number
  default     = 2
}

variable "unhealthy_threshold" {
  description = "Number of consecutive health check failures required"
  type        = number
  default     = 3
}

# CloudFront Configuration
variable "cloudfront_price_class" {
  description = "CloudFront price class (PriceClass_All, PriceClass_200, PriceClass_100)"
  type        = string
  default     = "PriceClass_100"
}

variable "cloudfront_ssl_certificate_arn" {
  description = "ARN of ACM certificate for CloudFront custom domain. Must be in us-east-1 when custom_domain is set."
  type        = string
  default     = ""

  validation {
    condition     = var.cloudfront_ssl_certificate_arn == "" || can(regex("^arn:aws:acm:", var.cloudfront_ssl_certificate_arn))
    error_message = "The cloudfront_ssl_certificate_arn must be a valid ACM certificate ARN or empty string."
  }
}

variable "alb_ssl_certificate_arn" {
  description = "ARN of ACM certificate for ALB HTTPS listener. Required for production WSS/HTTPS backend traffic. Leave empty only for development HTTP mode."
  type        = string
  default     = ""

  validation {
    condition     = var.alb_ssl_certificate_arn == "" || can(regex("^arn:aws:acm:", var.alb_ssl_certificate_arn))
    error_message = "The alb_ssl_certificate_arn must be a valid ACM certificate ARN or empty string."
  }
}

variable "backend_domain_name" {
  description = "Backend API domain covered by alb_ssl_certificate_arn, for example api.livecap.example.com. Required when alb_ssl_certificate_arn is set."
  type        = string
  default     = ""
}

variable "custom_domain" {
  description = "Custom domain name for CloudFront distribution (optional)"
  type        = string
  default     = ""
}

# VPC Configuration
variable "vpc_id" {
  description = "VPC ID for resource deployment (if not provided, will use default VPC)"
  type        = string
  default     = ""
}

variable "public_subnet_ids" {
  description = "List of public subnet IDs for ALB"
  type        = list(string)
  default     = []
}

variable "private_subnet_ids" {
  description = "List of private subnet IDs for ECS tasks"
  type        = list(string)
  default     = []
}

# Tags
variable "tags" {
  description = "Additional tags to apply to all resources"
  type        = map(string)
  default     = {}
}

# ECR Configuration
variable "ecr_repository_name" {
  description = "Name for the ECR repository"
  type        = string
  default     = "livecap-backend"
}

variable "ecr_image_tag_mutability" {
  description = "Image tag mutability setting for ECR (MUTABLE or IMMUTABLE)"
  type        = string
  default     = "MUTABLE"
}

variable "ecr_scan_on_push" {
  description = "Enable image scanning on push"
  type        = bool
  default     = true
}

# CloudWatch Configuration
variable "log_retention_days" {
  description = "Number of days to retain CloudWatch logs"
  type        = number
  default     = 14
}

variable "enable_cloudwatch_dashboard" {
  description = "Create a CloudWatch dashboard for LiveCap operational observability."
  type        = bool
  default     = true
}

variable "cloudwatch_dashboard_name" {
  description = "Optional CloudWatch dashboard name. If empty, a name is generated from project and environment."
  type        = string
  default     = ""
}

variable "enable_waf" {
  description = "Create AWS WAFv2 Web ACLs for CloudFront and ALB in COUNT mode."
  type        = bool
  default     = true
}

variable "waf_rate_limit" {
  description = "Request rate limit per 5-minute window for WAF rate-based COUNT rules."
  type        = number
  default     = 2000
}

# Autoscaling Configuration
variable "autoscaling_target_cpu" {
  description = "Target CPU utilization percentage for autoscaling"
  type        = number
  default     = 70
}

variable "autoscaling_target_memory" {
  description = "Target memory utilization percentage for autoscaling"
  type        = number
  default     = 80
}
