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

variable "backend_image_tag" {
  description = "Immutable Git SHA tag, optionally with an architecture suffix, already pushed to ECR for the target Fargate task."
  type        = string

  validation {
    condition     = can(regex("^[0-9a-f]{7,40}(-amd64)?$", var.backend_image_tag))
    error_message = "backend_image_tag must be a lowercase Git SHA with an optional -amd64 suffix."
  }
}

variable "route_backend_to_target" {
  description = "Route CloudFront /api/* and /ws/* traffic to the target ALB. Keep false for the first blue/green apply."
  type        = bool
  default     = false
}

variable "target_backend_desired_count" {
  description = "Initial target service task count. Use 1 for migration validation, then return to 0 after wake/idle checks."
  type        = number
  default     = 0

  validation {
    condition     = contains([0, 1], var.target_backend_desired_count)
    error_message = "target_backend_desired_count must be 0 or 1."
  }
}

variable "legacy_backend_min_capacity" {
  description = "Minimum capacity for the legacy service during the rollback window."
  type        = number
  default     = 1
}

variable "legacy_backend_max_capacity" {
  description = "Maximum capacity for the legacy service during migration. Keep at 1 for the in-memory session registry."
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

variable "budget_forecast_alert_threshold_pct" {
  description = "Percentage of the monthly budget at which a FORECASTED alert fires (early warning before the 100% ACTUAL alert)."
  type        = number
  default     = 80
}

# --- Operational alarms (CloudWatch -> SNS) --------------------------------

variable "enable_alarms" {
  description = "Create CloudWatch alarms (ALB 5XX/latency, ECS CPU/memory, target health) and an SNS alerts topic."
  type        = bool
  default     = true
}

variable "alert_notification_email" {
  description = "Email subscribed to the CloudWatch alerts SNS topic. Leave empty to create the topic without a subscription (add subscribers later)."
  type        = string
  default     = ""
}

variable "alarm_alb_5xx_threshold" {
  description = "Alarm when ALB target 5XX responses in a 5-minute window exceed this count."
  type        = number
  default     = 5
}

variable "alarm_alb_target_latency_seconds" {
  description = "Alarm when average ALB target response time (seconds) exceeds this over the evaluation window."
  type        = number
  default     = 2
}

variable "alarm_cpu_utilization_pct" {
  description = "Alarm when ECS service average CPU utilization (%) exceeds this."
  type        = number
  default     = 85
}

variable "alarm_memory_utilization_pct" {
  description = "Alarm when ECS service average memory utilization (%) exceeds this."
  type        = number
  default     = 85
}

variable "enable_demo_scheduled_scaling" {
  description = "Enable demo-safe scheduled scaling for the ECS service."
  type        = bool
  default     = false
}

variable "enable_legacy_scheduled_scaling" {
  description = "Keep scheduled scaling on the legacy rollback service during migration."
  type        = bool
  default     = false
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

variable "target_enable_idle_scale_down" {
  description = "Enable idle scale-down for the private target service. Local/dev .env safety remains disabled."
  type        = bool
  default     = false
}

variable "idle_scale_down_grace_seconds" {
  description = "Seconds to wait after the last active session ends before the backend requests ECS scale-to-zero."
  type        = number
  default     = 300
}

variable "enable_wake_endpoint" {
  description = "Create an AWS_IAM Lambda Function URL exposed through the signed CloudFront /api/wake origin."
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
  description = "Optional ACM certificate ARN for the legacy rollback ALB. Leave empty to keep its current HTTP origin during migration."
  type        = string
  default     = ""

  validation {
    condition     = var.alb_ssl_certificate_arn == "" || can(regex("^arn:aws:acm:", var.alb_ssl_certificate_arn))
    error_message = "The alb_ssl_certificate_arn must be a valid ACM certificate ARN or empty string."
  }
}

variable "backend_domain_name" {
  description = "Legacy backend domain covered by alb_ssl_certificate_arn. Required only when legacy ALB TLS is enabled."
  type        = string
  default     = ""
}

variable "target_backend_domain_name" {
  description = "DNS name covered by target_alb_ssl_certificate_arn and pointed at the target ALB during blue/green migration."
  type        = string
  default     = ""
}

variable "target_alb_ssl_certificate_arn" {
  description = "ACM certificate ARN for the target ALB HTTPS listener in ap-southeast-1."
  type        = string
  default     = ""

  validation {
    condition     = var.target_alb_ssl_certificate_arn == "" || can(regex("^arn:aws:acm:ap-southeast-1:", var.target_alb_ssl_certificate_arn))
    error_message = "target_alb_ssl_certificate_arn must be an ap-southeast-1 ACM certificate ARN or empty."
  }
}

variable "custom_domain" {
  description = "Custom domain name for CloudFront distribution (optional)"
  type        = string
  default     = ""
}

# VPC Configuration
variable "legacy_availability_zones" {
  description = "Availability Zones retained by the legacy ALB/ECS rollback stack."
  type        = list(string)
  default     = ["ap-southeast-1a", "ap-southeast-1b"]

  validation {
    condition     = length(var.legacy_availability_zones) >= 2
    error_message = "legacy_availability_zones must contain at least two AZs because the ALB requires two Availability Zones."
  }
}

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

variable "target_vpc_cidr" {
  description = "CIDR for the dedicated LiveCap target VPC."
  type        = string
  default     = "10.20.0.0/16"
}

variable "target_public_subnets" {
  description = "Two public subnets used by the target ALB and NAT gateway."
  type = map(object({
    availability_zone = string
    cidr_block        = string
  }))
  default = {
    a = {
      availability_zone = "ap-southeast-1a"
      cidr_block        = "10.20.0.0/24"
    }
    b = {
      availability_zone = "ap-southeast-1b"
      cidr_block        = "10.20.1.0/24"
    }
  }
}

variable "target_private_subnets" {
  description = "Two private subnets used by target Fargate tasks."
  type = map(object({
    availability_zone = string
    cidr_block        = string
  }))
  default = {
    a = {
      availability_zone = "ap-southeast-1a"
      cidr_block        = "10.20.10.0/24"
    }
    b = {
      availability_zone = "ap-southeast-1b"
      cidr_block        = "10.20.11.0/24"
    }
  }
}

variable "target_nat_gateway_subnet_key" {
  description = "Public subnet key that hosts the single cost-optimized NAT gateway."
  type        = string
  default     = "a"

  validation {
    condition     = contains(keys(var.target_public_subnets), var.target_nat_gateway_subnet_key)
    error_message = "target_nat_gateway_subnet_key must match a key in target_public_subnets."
  }
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
  default     = "IMMUTABLE"
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

variable "manage_watchtower_log_group" {
  description = "Manage the watchtower application log group in Terraform so it gets an explicit retention policy. Import the existing group before the first apply."
  type        = bool
  default     = true
}

variable "watchtower_log_group_name" {
  description = "Name of the watchtower application log group created by the backend logging_service. Must match CLOUDWATCH_LOG_GROUP used by the running task."
  type        = string
  default     = "livecap"
}

variable "enable_meeting_summary" {
  description = "Enable the Amazon Bedrock end-of-session meeting summary. Adds a bedrock:InvokeModel IAM policy and passes the feature flag to the task."
  type        = bool
  default     = false
}

variable "bedrock_model_id" {
  description = "Amazon Bedrock model ID used for meeting summaries (Anthropic Claude messages API)."
  type        = string
  default     = "anthropic.claude-3-haiku-20240307-v1:0"
}

variable "bedrock_region" {
  description = "Region for Amazon Bedrock calls. Leave empty to use aws_region. Set this when the model is not available in aws_region (e.g. ap-southeast-1)."
  type        = string
  default     = ""
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
  description = "Create blocking AWS WAFv2 Web ACLs for CloudFront and ALB."
  type        = bool
  default     = false
}

variable "waf_rate_limit" {
  description = "Request rate limit per 5-minute window for WAF rate-based BLOCK rules."
  type        = number
  default     = 2000
}

variable "origin_verify_secret" {
  description = "Secret CloudFront origin header required by the ALB WAF. Set through untracked tfvars when enable_waf is true."
  type        = string
  sensitive   = true
  default     = ""

  validation {
    condition     = var.origin_verify_secret == "" || length(var.origin_verify_secret) >= 32
    error_message = "origin_verify_secret must be empty or at least 32 characters."
  }
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
