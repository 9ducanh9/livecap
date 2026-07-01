# CloudFront Distribution for Frontend

locals {
  legacy_backend_origin_id = "ALB-${aws_lb.main.name}"
  target_backend_origin_id = "ALB-${aws_lb.target.name}"
  selected_backend_origin_id = (
    var.route_backend_to_target
    ? local.target_backend_origin_id
    : local.legacy_backend_origin_id
  )
  frontend_allowed_origin = (
    var.custom_domain != ""
    ? "https://${var.custom_domain}"
    : "https://${aws_cloudfront_distribution.frontend.domain_name}"
  )
}

# Origin Access Control for S3
resource "aws_cloudfront_origin_access_control" "frontend" {
  name                              = "${var.project_name}-frontend-${var.environment}-oac"
  description                       = "OAC for ${var.project_name} frontend bucket"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# CloudFront Distribution
resource "aws_cloudfront_distribution" "frontend" {
  enabled             = true
  is_ipv6_enabled     = true
  comment             = "${var.project_name} ${var.environment} frontend distribution"
  default_root_object = "index.html"
  price_class         = var.cloudfront_price_class
  aliases             = var.custom_domain != "" ? [var.custom_domain] : []
  web_acl_id          = var.enable_waf ? aws_wafv2_web_acl.cloudfront[0].arn : null

  origin {
    domain_name              = aws_s3_bucket.frontend.bucket_regional_domain_name
    origin_id                = "S3-${aws_s3_bucket.frontend.id}"
    origin_access_control_id = aws_cloudfront_origin_access_control.frontend.id
  }

  origin {
    domain_name = var.alb_ssl_certificate_arn != "" ? var.backend_domain_name : aws_lb.main.dns_name
    origin_id   = local.legacy_backend_origin_id

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = var.alb_ssl_certificate_arn != "" ? "https-only" : "http-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  origin {
    domain_name = var.alb_ssl_certificate_arn != "" ? var.target_backend_domain_name : aws_lb.target.dns_name
    origin_id   = local.target_backend_origin_id

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = var.alb_ssl_certificate_arn != "" ? "https-only" : "http-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  dynamic "origin" {
    for_each = var.enable_wake_endpoint ? [1] : []

    content {
      domain_name              = trimsuffix(trimprefix(aws_lambda_function_url.wake_backend[0].function_url, "https://"), "/")
      origin_id                = "WakeLambdaFunctionUrl"
      origin_access_control_id = aws_cloudfront_origin_access_control.wake_backend[0].id

      custom_origin_config {
        http_port              = 80
        https_port             = 443
        origin_protocol_policy = "https-only"
        origin_ssl_protocols   = ["TLSv1.2"]
      }
    }
  }

  default_cache_behavior {
    allowed_methods  = ["GET", "HEAD", "OPTIONS"]
    cached_methods   = ["GET", "HEAD"]
    target_origin_id = "S3-${aws_s3_bucket.frontend.id}"

    forwarded_values {
      query_string = false
      headers      = []

      cookies {
        forward = "none"
      }
    }

    viewer_protocol_policy = "redirect-to-https"
    min_ttl                = 0
    default_ttl            = 3600     # 1 hour
    max_ttl                = 31536000 # 1 year
    compress               = true
  }

  # The wake endpoint is more specific than /api/* and must be evaluated first.
  dynamic "ordered_cache_behavior" {
    for_each = var.enable_wake_endpoint ? [1] : []

    content {
      path_pattern     = "/api/wake"
      allowed_methods  = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
      cached_methods   = ["GET", "HEAD"]
      target_origin_id = "WakeLambdaFunctionUrl"

      forwarded_values {
        query_string = true
        headers      = ["*"]

        cookies {
          forward = "none"
        }
      }

      viewer_protocol_policy = "redirect-to-https"
      min_ttl                = 0
      default_ttl            = 0
      max_ttl                = 0
      compress               = true
    }
  }

  # Proxy API requests through the same CloudFront origin to avoid HTTPS page
  # mixed-content blocks while the backend ALB is still HTTP-only.
  ordered_cache_behavior {
    path_pattern     = "/api/*"
    allowed_methods  = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
    cached_methods   = ["GET", "HEAD"]
    target_origin_id = local.selected_backend_origin_id

    forwarded_values {
      query_string = true
      headers      = ["*"]

      cookies {
        forward = "all"
      }
    }

    viewer_protocol_policy = "redirect-to-https"
    min_ttl                = 0
    default_ttl            = 0
    max_ttl                = 0
    compress               = true
  }

  # Proxy WebSocket upgrade requests through CloudFront so the browser can use
  # wss://<cloudfront>/ws/transcribe without requiring an ALB certificate yet.
  ordered_cache_behavior {
    path_pattern     = "/ws/*"
    allowed_methods  = ["GET", "HEAD", "OPTIONS"]
    cached_methods   = ["GET", "HEAD"]
    target_origin_id = local.selected_backend_origin_id

    forwarded_values {
      query_string = true
      headers      = ["*"]

      cookies {
        forward = "all"
      }
    }

    viewer_protocol_policy = "redirect-to-https"
    min_ttl                = 0
    default_ttl            = 0
    max_ttl                = 0
    compress               = false
  }

  # Cache behavior for versioned static assets (long TTL)
  ordered_cache_behavior {
    path_pattern     = "/assets/*"
    allowed_methods  = ["GET", "HEAD", "OPTIONS"]
    cached_methods   = ["GET", "HEAD"]
    target_origin_id = "S3-${aws_s3_bucket.frontend.id}"

    forwarded_values {
      query_string = false
      headers      = []

      cookies {
        forward = "none"
      }
    }

    viewer_protocol_policy = "redirect-to-https"
    min_ttl                = 0
    default_ttl            = 31536000 # 1 year
    max_ttl                = 31536000 # 1 year
    compress               = true
  }

  # Custom error response for SPA routing
  custom_error_response {
    error_code         = 404
    response_code      = 200
    response_page_path = "/index.html"
  }

  custom_error_response {
    error_code         = 403
    response_code      = 200
    response_page_path = "/index.html"
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    # Use custom certificate if provided, otherwise use default CloudFront certificate
    cloudfront_default_certificate = var.cloudfront_ssl_certificate_arn == ""
    acm_certificate_arn            = var.cloudfront_ssl_certificate_arn != "" ? var.cloudfront_ssl_certificate_arn : null
    ssl_support_method             = var.cloudfront_ssl_certificate_arn != "" ? "sni-only" : null
    minimum_protocol_version       = "TLSv1.2_2021"
  }

  tags = merge(
    var.tags,
    {
      Name        = "${var.project_name}-frontend-${var.environment}"
      Environment = var.environment
    }
  )

  lifecycle {
    precondition {
      condition = (
        var.alb_ssl_certificate_arn == ""
        || (var.backend_domain_name != "" && var.target_backend_domain_name != "")
      )
      error_message = "backend_domain_name and target_backend_domain_name are required when alb_ssl_certificate_arn is set."
    }
  }
}
