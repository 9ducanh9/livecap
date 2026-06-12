variable "aws_region" {
  description = "AWS region for the Terraform remote-state bucket."
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment name used in the remote-state bucket name."
  type        = string
  default     = "dev"
}

variable "project_name" {
  description = "Project name used in the remote-state bucket name."
  type        = string
  default     = "livecap"
}

variable "state_bucket_name" {
  description = "Optional explicit remote-state bucket name. Leave empty to generate one from project, environment, and AWS account ID."
  type        = string
  default     = ""
}
