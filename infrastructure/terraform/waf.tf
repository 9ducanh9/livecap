# Blocking AWS WAF for LiveCap CloudFront and ALB entrypoints.

resource "aws_wafv2_web_acl" "cloudfront" {
  provider = aws.us_east_1
  count    = var.enable_waf ? 1 : 0

  name        = "${var.project_name}-cloudfront-waf-${var.environment}"
  description = "Blocking WAF for LiveCap CloudFront frontend edge traffic."
  scope       = "CLOUDFRONT"

  default_action {
    allow {}
  }

  rule {
    name     = "AWSManagedRulesCommonRuleSet"
    priority = 10

    override_action {
      none {}
    }

    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesCommonRuleSet"
        vendor_name = "AWS"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.project_name}-cloudfront-common-${var.environment}"
      sampled_requests_enabled   = true
    }
  }

  rule {
    name     = "AWSManagedRulesKnownBadInputsRuleSet"
    priority = 20

    override_action {
      none {}
    }

    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesKnownBadInputsRuleSet"
        vendor_name = "AWS"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.project_name}-cloudfront-known-bad-${var.environment}"
      sampled_requests_enabled   = true
    }
  }

  rule {
    name     = "RateLimitBlock"
    priority = 30

    action {
      block {}
    }

    statement {
      rate_based_statement {
        aggregate_key_type = "IP"
        limit              = var.waf_rate_limit
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.project_name}-cloudfront-rate-${var.environment}"
      sampled_requests_enabled   = true
    }
  }

  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "${var.project_name}-cloudfront-waf-${var.environment}"
    sampled_requests_enabled   = true
  }
}

resource "aws_wafv2_web_acl" "alb" {
  count = var.enable_waf ? 1 : 0

  name        = "${var.project_name}-alb-waf-${var.environment}"
  description = "Blocking WAF for LiveCap ALB with verified CloudFront origin."
  scope       = "REGIONAL"

  default_action {
    block {}
  }

  rule {
    name     = "AWSManagedRulesCommonRuleSet"
    priority = 10

    override_action {
      none {}
    }

    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesCommonRuleSet"
        vendor_name = "AWS"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.project_name}-alb-common-${var.environment}"
      sampled_requests_enabled   = true
    }
  }

  rule {
    name     = "AWSManagedRulesKnownBadInputsRuleSet"
    priority = 20

    override_action {
      none {}
    }

    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesKnownBadInputsRuleSet"
        vendor_name = "AWS"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.project_name}-alb-known-bad-${var.environment}"
      sampled_requests_enabled   = true
    }
  }

  rule {
    name     = "RateLimitBlock"
    priority = 30

    action {
      block {}
    }

    statement {
      rate_based_statement {
        aggregate_key_type = "FORWARDED_IP"
        limit              = var.waf_rate_limit

        forwarded_ip_config {
          fallback_behavior = "MATCH"
          header_name       = "X-Forwarded-For"
        }
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.project_name}-alb-rate-${var.environment}"
      sampled_requests_enabled   = true
    }
  }

  dynamic "rule" {
    for_each = var.enable_waf ? [1] : []

    content {
      name     = "AllowVerifiedCloudFrontOrigin"
      priority = 100

      action {
        allow {}
      }

      statement {
        byte_match_statement {
          positional_constraint = "EXACTLY"
          search_string         = var.origin_verify_secret

          field_to_match {
            single_header {
              name = "x-livecap-origin-verify"
            }
          }

          text_transformation {
            priority = 0
            type     = "NONE"
          }
        }
      }

      visibility_config {
        cloudwatch_metrics_enabled = true
        metric_name                = "${var.project_name}-alb-verified-origin-${var.environment}"
        sampled_requests_enabled   = true
      }
    }
  }

  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "${var.project_name}-alb-waf-${var.environment}"
    sampled_requests_enabled   = true
  }

  lifecycle {
    precondition {
      condition     = nonsensitive(var.origin_verify_secret != "")
      error_message = "origin_verify_secret must be set when enable_waf is true."
    }
  }
}

resource "aws_wafv2_web_acl_association" "alb" {
  count = var.enable_waf ? 1 : 0

  resource_arn = aws_lb.main.arn
  web_acl_arn  = aws_wafv2_web_acl.alb[0].arn
}

resource "aws_wafv2_web_acl_association" "target_alb" {
  count = var.enable_waf ? 1 : 0

  resource_arn = aws_lb.target.arn
  web_acl_arn  = aws_wafv2_web_acl.alb[0].arn
}

resource "aws_cloudwatch_log_group" "cloudfront_waf" {
  provider = aws.us_east_1
  count    = var.enable_waf ? 1 : 0

  name              = "aws-waf-logs-${var.project_name}-cloudfront-${var.environment}"
  retention_in_days = var.log_retention_days
}

resource "aws_cloudwatch_log_group" "alb_waf" {
  count = var.enable_waf ? 1 : 0

  name              = "aws-waf-logs-${var.project_name}-alb-${var.environment}"
  retention_in_days = var.log_retention_days
}

resource "aws_wafv2_web_acl_logging_configuration" "cloudfront" {
  provider = aws.us_east_1
  count    = var.enable_waf ? 1 : 0

  resource_arn            = aws_wafv2_web_acl.cloudfront[0].arn
  log_destination_configs = ["${aws_cloudwatch_log_group.cloudfront_waf[0].arn}:*"]

  redacted_fields {
    single_header {
      name = "authorization"
    }
  }

  redacted_fields {
    single_header {
      name = "cookie"
    }
  }

  redacted_fields {
    single_header {
      name = "x-livecap-origin-verify"
    }
  }

  logging_filter {
    default_behavior = "DROP"

    filter {
      behavior    = "KEEP"
      requirement = "MEETS_ANY"

      condition {
        action_condition {
          action = "BLOCK"
        }
      }

      condition {
        action_condition {
          action = "COUNT"
        }
      }
    }
  }
}

resource "aws_wafv2_web_acl_logging_configuration" "alb" {
  count = var.enable_waf ? 1 : 0

  resource_arn            = aws_wafv2_web_acl.alb[0].arn
  log_destination_configs = ["${aws_cloudwatch_log_group.alb_waf[0].arn}:*"]

  redacted_fields {
    single_header {
      name = "authorization"
    }
  }

  redacted_fields {
    single_header {
      name = "cookie"
    }
  }

  redacted_fields {
    single_header {
      name = "x-livecap-origin-verify"
    }
  }

  logging_filter {
    default_behavior = "DROP"

    filter {
      behavior    = "KEEP"
      requirement = "MEETS_ANY"

      condition {
        action_condition {
          action = "BLOCK"
        }
      }

      condition {
        action_condition {
          action = "COUNT"
        }
      }
    }
  }
}
