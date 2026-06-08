# Output Values

locals {
  backend_host = (
    var.alb_ssl_certificate_arn != "" && var.backend_domain_name != ""
  ) ? var.backend_domain_name : aws_lb.main.dns_name

  backend_base_url = var.alb_ssl_certificate_arn != "" ? "https://${local.backend_host}" : "http://${local.backend_host}"
  backend_ws_url   = var.alb_ssl_certificate_arn != "" ? "wss://${local.backend_host}/ws/transcribe" : "ws://${local.backend_host}/ws/transcribe"
}

output "cloudfront_url" {
  description = "CloudFront distribution URL for frontend access"
  value       = "https://${aws_cloudfront_distribution.frontend.domain_name}"
}

output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID"
  value       = aws_cloudfront_distribution.frontend.id
}

output "alb_dns_name" {
  description = "ALB DNS name for backend API access"
  value       = aws_lb.main.dns_name
}

output "alb_backend_base_url" {
  description = "Backend base URL for frontend VITE_API_BASE_URL"
  value       = local.backend_base_url
}

output "alb_websocket_url" {
  description = "Backend WebSocket URL for frontend VITE_WS_URL"
  value       = local.backend_ws_url
}

output "alb_arn" {
  description = "ARN of the Application Load Balancer"
  value       = aws_lb.main.arn
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
  description = "ECS service name"
  value       = aws_ecs_service.backend.name
}

output "ecs_task_definition_family" {
  description = "ECS task definition family"
  value       = aws_ecs_task_definition.backend.family
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
  description = "VPC ID used for deployment"
  value       = data.aws_vpc.selected.id
}

output "alb_security_group_id" {
  description = "Security group ID for ALB"
  value       = aws_security_group.alb.id
}

output "ecs_security_group_id" {
  description = "Security group ID for ECS tasks"
  value       = aws_security_group.ecs_tasks.id
}

output "region" {
  description = "AWS region"
  value       = var.aws_region
}

output "environment" {
  description = "Environment name"
  value       = var.environment
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
       docker tag ${aws_ecr_repository.backend.name}:latest ${aws_ecr_repository.backend.repository_url}:latest
       docker push ${aws_ecr_repository.backend.repository_url}:latest
    
    2. Deploy frontend to S3:
       cd frontend
       cat > .env.production << EOF
       VITE_API_BASE_URL=${local.backend_base_url}
       VITE_WS_URL=${local.backend_ws_url}
       EOF
       npm run build
       aws s3 sync dist/ s3://${aws_s3_bucket.frontend.id}/ --delete
    
    3. Invalidate CloudFront cache:
       aws cloudfront create-invalidation --distribution-id ${aws_cloudfront_distribution.frontend.id} --paths "/*"
    
    4. Access the application:
       Frontend: https://${aws_cloudfront_distribution.frontend.domain_name}
       Backend API: https://${aws_lb.main.dns_name}
    
  EOT
}
