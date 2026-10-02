resource "aws_wafv2_ip_set" "benchmark_alb" {
  name               = "${local.prefix}-alb-clients"
  scope              = "REGIONAL"
  ip_address_version = "IPV4"
  addresses          = var.benchmark_client_ipv4_cidrs
}
resource "aws_wafv2_web_acl" "benchmark_alb" {
  name  = "${local.prefix}-alb-waf"
  scope = "REGIONAL"
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
      metric_name                = "${local.prefix}-alb-managed-0"
      sampled_requests_enabled   = false
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
      metric_name                = "${local.prefix}-alb-managed-1"
      sampled_requests_enabled   = false
    }
  }
  rule {
    name     = "BenchmarkRateLimit"
    priority = 30
    action {
      block {}
    }
    statement {
      rate_based_statement {
        limit              = 2000
        aggregate_key_type = "FORWARDED_IP"
        forwarded_ip_config {
          header_name       = "X-Forwarded-For"
          fallback_behavior = "MATCH"
        }
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${local.prefix}-alb-rate"
      sampled_requests_enabled   = false
    }
  }
  rule {
    name     = "BenchmarkClientAllowlist"
    priority = 100
    action {
      allow {}
    }
    statement {
      ip_set_reference_statement {
        arn = aws_wafv2_ip_set.benchmark_alb.arn
        ip_set_forwarded_ip_config {
          header_name       = "X-Forwarded-For"
          fallback_behavior = "NO_MATCH"
          position          = "LAST"
        }
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${local.prefix}-alb-clients"
      sampled_requests_enabled   = false
    }
  }
  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "${local.prefix}-alb"
    sampled_requests_enabled   = false
  }
}
resource "aws_wafv2_ip_set" "benchmark_edge" {
  provider           = aws.edge
  name               = "${local.prefix}-edge-clients"
  scope              = "CLOUDFRONT"
  ip_address_version = "IPV4"
  addresses          = var.benchmark_client_ipv4_cidrs
}
resource "aws_wafv2_web_acl" "benchmark_edge" {
  provider = aws.edge
  name     = "${local.prefix}-edge-waf"
  scope    = "CLOUDFRONT"
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
      metric_name                = "${local.prefix}-edge-managed-0"
      sampled_requests_enabled   = false
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
      metric_name                = "${local.prefix}-edge-managed-1"
      sampled_requests_enabled   = false
    }
  }
  rule {
    name     = "BenchmarkRateLimit"
    priority = 30
    action {
      block {}
    }
    statement {
      rate_based_statement {
        limit              = 2000
        aggregate_key_type = "IP"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${local.prefix}-edge-rate"
      sampled_requests_enabled   = false
    }
  }
  rule {
    name     = "BenchmarkClientAllowlist"
    priority = 100
    action {
      allow {}
    }
    statement {
      ip_set_reference_statement {
        arn = aws_wafv2_ip_set.benchmark_edge.arn
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${local.prefix}-edge-clients"
      sampled_requests_enabled   = false
    }
  }
  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "${local.prefix}-edge"
    sampled_requests_enabled   = false
  }
}
resource "aws_wafv2_web_acl_association" "benchmark" {
  resource_arn = aws_lb.benchmark.arn
  web_acl_arn  = aws_wafv2_web_acl.benchmark_alb.arn
}
# No WAF request samples/access logs: these can contain tokens, query strings and IPs.
