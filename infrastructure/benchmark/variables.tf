variable "environment" {
  type        = string
  description = "Mandatory explicit benchmark var-file selection."
}
variable "aws_region" {
  type        = string
  description = "Must be ap-southeast-1."
}
variable "expected_account_id" {
  type        = string
  description = "Must be 720459752315."
}
variable "owner" {
  type        = string
  description = "Cost owner label, not an email."
  validation {
    condition     = trimspace(var.owner) != ""
    error_message = "Owner is required."
  }
}

variable "benchmark_origin_hostname" {
  type        = string
  description = "New benchmark-only DNS hostname; ownership, absence of collision and external DNS validation are P4B prerequisites."
  validation {
    condition     = can(regex("^benchmark-origin\\.[a-z0-9.-]+$", var.benchmark_origin_hostname))
    error_message = "Use a new benchmark-origin hostname, never the stable or preview origin."
  }
}
variable "shared_vpc_id" {
  type        = string
  description = "Read-only existing VPC."
}
variable "shared_public_subnet_ids" {
  type        = list(string)
  description = "Read-only ALB public subnets."
}
variable "shared_private_subnet_ids" {
  type        = list(string)
  description = "Read-only task private subnets."
}
variable "image_git_sha" {
  type        = string
  description = "Full 40-character source checkpoint SHA; image may be built only in P4B."
  validation {
    condition     = can(regex("^[0-9a-f]{40}$", var.image_git_sha))
    error_message = "Image SHA must be a full lowercase Git commit SHA."
  }
}
variable "benchmark_client_ipv4_cidrs" {
  type        = list(string)
  description = "Fail-closed design placeholder; replace with benchmark public egress /32 before P4B."
  default     = ["127.0.0.1/32"]
  validation {
    condition     = length(var.benchmark_client_ipv4_cidrs) > 0 && alltrue([for c in var.benchmark_client_ipv4_cidrs : can(cidrnetmask(c)) && endswith(c, "/32")])
    error_message = "Only explicit IPv4 host /32 allowlist entries are permitted."
  }
}
variable "monthly_budget_limit_usd" {
  type        = number
  description = "User-selected alert threshold, NOT an estimated bill or enforced cap."
  default     = 20
  validation {
    condition     = var.monthly_budget_limit_usd > 0
    error_message = "Budget threshold must be positive."
  }
}
variable "benchmark_alert_email" {
  type        = string
  description = "Private local-only cost alert recipient; subscription is created only in authorized P4B. Empty disables subscription in design plans."
  sensitive   = true
  default     = ""
  validation {
    condition     = var.benchmark_alert_email == "" || can(regex("^[^[:space:]@]+@[^[:space:]@]+\\.[^[:space:]@]+$", var.benchmark_alert_email))
    error_message = "Provide one valid cost alert email privately, or empty for design."
  }
}
variable "log_retention_days" {
  type        = number
  description = "Short application log retention."
  default     = 3
  validation {
    condition     = contains([1, 3, 5, 7], var.log_retention_days)
    error_message = "Benchmark retention must be 1, 3, 5 or 7 days."
  }
}
variable "max_sessions_per_ip" {
  type        = number
  description = "Benchmark-only per-IP concurrency; not measured capacity."
  default     = 4
  validation {
    condition     = var.max_sessions_per_ip >= 4 && var.max_sessions_per_ip <= 16 && floor(var.max_sessions_per_ip) == var.max_sessions_per_ip
    error_message = "Benchmark per-IP limit must be an integer from 4 to 16."
  }
}
