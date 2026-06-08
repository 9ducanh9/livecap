# Variables for LiveCap Infrastructure

variable "aws_region" {
  description = "AWS region for resource deployment"
  type        = string
  default     = "us-east-1"
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
  default     = 30
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

variable "ecs_desired_count" {
  description = "Desired number of ECS tasks to run"
  type        = number
  default     = 1
}

variable "ecs_min_capacity" {
  description = "Minimum number of ECS tasks for autoscaling"
  type        = number
  default     = 1
}

variable "ecs_max_capacity" {
  description = "Maximum number of ECS tasks for autoscaling"
  type        = number
  default     = 4
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
  default     = 7
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
