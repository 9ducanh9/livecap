output "state_bucket_name" {
  description = "S3 bucket name to use in infrastructure/terraform/backend.hcl."
  value       = aws_s3_bucket.state.id
}

output "backend_config" {
  description = "Minimal backend.hcl content for the main Terraform configuration."
  value       = "bucket = \"${aws_s3_bucket.state.id}\""
}
