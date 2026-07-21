# Output Values

locals {
  backend_host = (
    var.target_alb_ssl_certificate_arn != "" && var.target_backend_domain_name != ""
  ) ? var.target_backend_domain_name : aws_lb.target.dns_name

  backend_base_url  = var.target_alb_ssl_certificate_arn != "" ? "https://${local.backend_host}" : "http://${local.backend_host}"
  backend_ws_url    = var.target_alb_ssl_certificate_arn != "" ? "wss://${local.backend_host}/ws/transcribe" : "ws://${local.backend_host}/ws/transcribe"
  frontend_base_url = var.custom_domain != "" ? "https://${var.custom_domain}" : "https://${aws_cloudfront_distribution.frontend.domain_name}"
  frontend_ws_url   = "wss://${aws_cloudfront_distribution.frontend.domain_name}/ws/transcribe"
}

output "alerts_sns_topic_arn" {
  description = "ARN of the CloudWatch alerts SNS topic (empty when alarms are disabled)."
  value       = var.enable_alarms ? aws_sns_topic.alerts[0].arn : ""
}

output "cloudfront_url" {
  description = "CloudFront distribution URL for frontend access"
  value       = "https://${aws_cloudfront_distribution.frontend.domain_name}"
}

output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID"
  value       = aws_cloudfront_distribution.frontend.id
}

output "preview_cloudfront_url" {
  description = "Preview CloudFront URL when enable_preview_frontend is true."
  value       = try("https://${aws_cloudfront_distribution.preview[0].domain_name}", null)
}

output "preview_cloudfront_distribution_id" {
  description = "Preview CloudFront distribution ID when enabled."
  value       = try(aws_cloudfront_distribution.preview[0].id, null)
}

output "preview_frontend_bucket_name" {
  description = "S3 bucket for Update/preview frontend builds when enabled."
  value       = try(aws_s3_bucket.frontend_preview[0].id, null)
}

output "alb_dns_name" {
  description = "ALB DNS name for backend API access"
  value       = aws_lb.target.dns_name
}

output "alb_backend_base_url" {
  description = "Backend base URL for frontend VITE_API_BASE_URL"
  value       = local.backend_base_url
}

output "alb_websocket_url" {
  description = "Backend WebSocket URL for frontend VITE_WS_URL"
  value       = local.backend_ws_url
}

output "wake_backend_url" {
  description = "Same-origin CloudFront path for frontend VITE_WAKE_BACKEND_URL when enable_wake_endpoint is true."
  value       = var.enable_wake_endpoint ? "/api/wake" : ""
}

output "frontend_api_base_url" {
  description = "Same-origin CloudFront base URL for frontend API requests."
  value       = local.frontend_base_url
}

output "frontend_websocket_url" {
  description = "CloudFront WebSocket URL for the frontend."
  value       = local.frontend_ws_url
}

output "alb_arn" {
  description = "ARN of the Application Load Balancer"
  value       = aws_lb.target.arn
}

output "ecr_repository_uri" {
  description = "ECR repository URI for backend container images"
  value       = aws_ecr_repository.backend.repository_url
}

output "ecr_repository_name" {
  description = "ECR repository name"
  value       = aws_ecr_repository.backend.name
}

output "frontend_bucket_name" {
  description = "S3 bucket name for frontend static assets"
  value       = aws_s3_bucket.frontend.id
}

output "frontend_bucket_arn" {
  description = "S3 bucket ARN for frontend"
  value       = aws_s3_bucket.frontend.arn
}

output "transcript_bucket_name" {
  description = "S3 bucket name for transcript storage"
  value       = aws_s3_bucket.transcript.id
}

output "transcript_bucket_arn" {
  description = "S3 bucket ARN for transcripts"
  value       = aws_s3_bucket.transcript.arn
}

output "ecs_cluster_name" {
  description = "ECS cluster name"
  value       = aws_ecs_cluster.main.name
}

output "ecs_cluster_arn" {
  description = "ECS cluster ARN"
  value       = aws_ecs_cluster.main.arn
}

output "ecs_service_name" {
  description = "Private-subnet ECS service name."
  value       = aws_ecs_service.target_backend.name
}

output "ecs_task_definition_family" {
  description = "ECS task definition family"
  value       = aws_ecs_task_definition.target_backend.family
}

output "ecs_task_role_arn" {
  description = "IAM role ARN for ECS task (application-level permissions)"
  value       = aws_iam_role.ecs_task.arn
}

output "ecs_task_execution_role_arn" {
  description = "IAM role ARN for ECS task execution (ECR and CloudWatch)"
  value       = aws_iam_role.ecs_task_execution.arn
}

output "cloudwatch_log_group_name" {
  description = "CloudWatch log group name for backend logs"
  value       = aws_cloudwatch_log_group.backend.name
}

output "vpc_id" {
  description = "Dedicated target VPC ID."
  value       = aws_vpc.target.id
}

output "target_alb_dns_name" {
  description = "Dedicated VPC ALB DNS name."
  value       = aws_lb.target.dns_name
}

output "target_private_subnet_ids" {
  description = "Private subnet IDs used by target Fargate tasks."
  value       = [for subnet in aws_subnet.target_private : subnet.id]
}

output "alb_security_group_id" {
  description = "Security group ID for ALB"
  value       = aws_security_group.target_alb.id
}

output "ecs_security_group_id" {
  description = "Security group ID for ECS tasks"
  value       = aws_security_group.target_ecs_tasks.id
}

output "region" {
  description = "AWS region"
  value       = var.aws_region
}

output "environment" {
  description = "Environment name"
  value       = var.environment
}

# --- Security outputs ---

output "vpc_flow_log_group" {
  description = "CloudWatch log group receiving VPC Flow Logs (empty when disabled)."
  value       = var.enable_vpc_flow_logs ? aws_cloudwatch_log_group.vpc_flow_logs[0].name : ""
}

output "guardduty_detector_id" {
  description = "GuardDuty detector ID (empty when disabled)."
  value       = var.enable_guardduty ? aws_guardduty_detector.main[0].id : ""
}

output "security_hub_enabled" {
  description = "Whether Security Hub is enabled."
  value       = var.enable_security_hub
}

# Deployment instructions
output "deployment_instructions" {
  description = "Quick deployment instructions"
  value       = <<-EOT
    
    Deployment Instructions:
    =======================
    
    1. Build and push Docker image:
       aws ecr get-login-password --region ${var.aws_region} | docker login --username AWS --password-stdin ${aws_ecr_repository.backend.repository_url}
       docker build -t ${aws_ecr_repository.backend.name} ./backend
       docker tag ${aws_ecr_repository.backend.name}:${var.backend_image_tag} ${aws_ecr_repository.backend.repository_url}:${var.backend_image_tag}
       docker push ${aws_ecr_repository.backend.repository_url}:${var.backend_image_tag}
    
    2. Deploy frontend to S3:
       cd frontend
       cat > .env.production << EOF
       VITE_API_BASE_URL=${local.frontend_base_url}
       VITE_WS_URL=${local.frontend_ws_url}
       VITE_WAKE_BACKEND_URL=${var.enable_wake_endpoint ? "/api/wake" : ""}
       VITE_BACKEND_HEALTH_URL=/api/health
       VITE_BACKEND_WAKE_TIMEOUT_SECONDS=120
       VITE_MAX_SESSION_SECONDS=${var.session_timeout_seconds}
       EOF
       npm run build
       aws s3 sync dist/ s3://${aws_s3_bucket.frontend.id}/ --delete
    
    3. Invalidate CloudFront cache:
       aws cloudfront create-invalidation --distribution-id ${aws_cloudfront_distribution.frontend.id} --paths "/*"
    
    4. Access the application:
       Frontend: https://${aws_cloudfront_distribution.frontend.domain_name}
       Backend API: ${local.frontend_base_url}/api/
    
  EOT
}
