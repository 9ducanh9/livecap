terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
  backend "s3" {
    key                 = "livecap/benchmark/terraform.tfstate"
    region              = "ap-southeast-1"
    encrypt             = true
    use_lockfile        = true
    allowed_account_ids = ["720459752315"]
  }
}
provider "aws" {
  region              = var.aws_region
  allowed_account_ids = [var.expected_account_id]
  default_tags { tags = local.tags }
}
provider "aws" {
  alias               = "edge"
  region              = "us-east-1"
  allowed_account_ids = [var.expected_account_id]
  default_tags { tags = local.tags }
}
locals {
  prefix = "livecap-benchmark"
  tags = {
    Project     = "LiveCap"
    Environment = "benchmark"
    Purpose     = "performance-test"
    ManagedBy   = "Terraform"
    Owner       = var.owner
  }
}
data "aws_caller_identity" "benchmark" {}
data "aws_vpc" "shared" { id = var.shared_vpc_id }
data "aws_subnet" "public" {
  for_each = toset(var.shared_public_subnet_ids)
  id       = each.value
}
data "aws_subnet" "private" {
  for_each = toset(var.shared_private_subnet_ids)
  id       = each.value
}
data "aws_ec2_managed_prefix_list" "cloudfront" {
  name = "com.amazonaws.global.cloudfront.origin-facing"
}
# Shared network objects are DATA ONLY: this root cannot destroy them.
resource "terraform_data" "benchmark_guard" {
  input = var.environment
  lifecycle {
    precondition {
      condition     = var.environment == "benchmark" && var.aws_region == "ap-southeast-1" && var.expected_account_id == "720459752315"
      error_message = "Only benchmark in the reviewed Singapore account is permitted."
    }
    precondition {
      condition     = alltrue([for s in concat(values(data.aws_subnet.public), values(data.aws_subnet.private)) : s.vpc_id == data.aws_vpc.shared.id])
      error_message = "Every subnet must belong to the reviewed shared VPC."
    }
    precondition {
      condition     = length(toset([for s in data.aws_subnet.public : s.availability_zone])) >= 2
      error_message = "ALB requires at least two public subnet AZs."
    }
    precondition {
      condition     = alltrue([for s in data.aws_subnet.private : !s.map_public_ip_on_launch])
      error_message = "Task subnets must be private."
    }
  }
}
