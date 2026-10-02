output "benchmark_websocket_url" { value = "wss://${aws_cloudfront_distribution.benchmark.domain_name}/ws/transcribe" }
output "benchmark_health_url" { value = "https://${aws_cloudfront_distribution.benchmark.domain_name}/api/health" }
output "benchmark_cognito_pool_id" { value = aws_cognito_user_pool.benchmark.id }
output "benchmark_cognito_client_id" { value = aws_cognito_user_pool_client.benchmark.id }
output "benchmark_ecr_uri" { value = aws_ecr_repository.benchmark.repository_url }
output "benchmark_log_group" { value = aws_cloudwatch_log_group.benchmark.name }
output "benchmark_ecs_cluster" { value = aws_ecs_cluster.benchmark.name }
output "benchmark_ecs_service" { value = aws_ecs_service.benchmark.name }

output "benchmark_origin_alb_dns" { value = aws_lb.benchmark.dns_name }
output "benchmark_certificate_dns_validation" {
  value = aws_acm_certificate.benchmark.domain_validation_options
}
