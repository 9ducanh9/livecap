# Isolated frontend preview environment. The stable distribution and bucket keep
# serving main; this stack is for reviewed Update builds only.

locals {
  preview_frontend_bucket_name = "${var.project_name}-frontend-preview-${var.environment}-${data.aws_caller_identity.current.account_id}"
  preview_frontend_origin_id   = "S3-${local.preview_frontend_bucket_name}"
}

resource "aws_s3_bucket" "frontend_preview" {
  count  = var.enable_preview_frontend ? 1 : 0
  bucket = local.preview_frontend_bucket_name

  tags = merge(var.tags, {
    Name        = "${var.project_name}-frontend-preview-${var.environment}"
    Environment = var.environment
    Purpose     = "Preview static assets for the Update branch"
  })
}

resource "aws_s3_bucket_public_access_block" "frontend_preview" {
  count  = var.enable_preview_frontend ? 1 : 0
  bucket = aws_s3_bucket.frontend_preview[0].id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "frontend_preview" {
  count  = var.enable_preview_frontend ? 1 : 0
  bucket = aws_s3_bucket.frontend_preview[0].id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "frontend_preview" {
  count  = var.enable_preview_frontend ? 1 : 0
  bucket = aws_s3_bucket.frontend_preview[0].id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_cloudfront_origin_access_control" "frontend_preview" {
  count                             = var.enable_preview_frontend ? 1 : 0
  name                              = "${var.project_name}-frontend-preview-${var.environment}-oac"
  description                       = "OAC for ${var.project_name} preview frontend bucket"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_cloudfront_distribution" "preview" {
  count               = var.enable_preview_frontend ? 1 : 0
  enabled             = true
  is_ipv6_enabled     = true
  comment             = "${var.project_name} ${var.environment} frontend preview distribution"
  default_root_object = "index.html"
  price_class         = var.cloudfront_price_class
  aliases             = var.preview_custom_domain != "" ? [var.preview_custom_domain] : []
  web_acl_id          = var.enable_waf ? aws_wafv2_web_acl.cloudfront[0].arn : null

  origin {
    domain_name              = aws_s3_bucket.frontend_preview[0].bucket_regional_domain_name
    origin_id                = local.preview_frontend_origin_id
    origin_access_control_id = aws_cloudfront_origin_access_control.frontend_preview[0].id
  }

  origin {
    domain_name = var.target_alb_ssl_certificate_arn != "" ? var.target_backend_domain_name : aws_lb.target.dns_name
    origin_id   = local.target_backend_origin_id

    dynamic "custom_header" {
      for_each = var.enable_waf ? [1] : []

      content {
        name  = "X-LiveCap-Origin-Verify"
        value = var.origin_verify_secret
      }
    }

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = var.target_alb_ssl_certificate_arn != "" ? "https-only" : "http-only"
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
    target_origin_id = local.preview_frontend_origin_id

    forwarded_values {
      query_string = false
      headers      = []

      cookies {
        forward = "none"
      }
    }

    viewer_protocol_policy = "redirect-to-https"
    min_ttl                = 0
    default_ttl            = 3600
    max_ttl                = 31536000
    compress               = true

    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.spa_rewrite.arn
    }
  }

  dynamic "ordered_cache_behavior" {
    for_each = var.enable_wake_endpoint ? [1] : []

    content {
      path_pattern             = "/api/wake"
      allowed_methods          = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
      cached_methods           = ["GET", "HEAD"]
      target_origin_id         = "WakeLambdaFunctionUrl"
      cache_policy_id          = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad"
      origin_request_policy_id = "b689b0a8-53d0-40ab-baf2-68738e2966ac"
      viewer_protocol_policy   = "redirect-to-https"
      compress                 = true
    }
  }

  ordered_cache_behavior {
    path_pattern     = "/api/*"
    allowed_methods  = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
    cached_methods   = ["GET", "HEAD"]
    target_origin_id = local.target_backend_origin_id

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

  ordered_cache_behavior {
    path_pattern     = "/ws/*"
    allowed_methods  = ["GET", "HEAD", "OPTIONS"]
    cached_methods   = ["GET", "HEAD"]
    target_origin_id = local.target_backend_origin_id

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

  ordered_cache_behavior {
    path_pattern     = "/assets/*"
    allowed_methods  = ["GET", "HEAD", "OPTIONS"]
    cached_methods   = ["GET", "HEAD"]
    target_origin_id = local.preview_frontend_origin_id

    forwarded_values {
      query_string = false
      headers      = []

      cookies {
        forward = "none"
      }
    }

    viewer_protocol_policy = "redirect-to-https"
    min_ttl                = 0
    default_ttl            = 31536000
    max_ttl                = 31536000
    compress               = true
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = var.preview_custom_domain == "" || var.cloudfront_ssl_certificate_arn == ""
    acm_certificate_arn            = var.preview_custom_domain != "" ? var.cloudfront_ssl_certificate_arn : null
    ssl_support_method             = var.preview_custom_domain != "" ? "sni-only" : null
    minimum_protocol_version       = "TLSv1.2_2021"
  }
}

resource "aws_s3_bucket_policy" "frontend_preview_cloudfront_access" {
  count  = var.enable_preview_frontend ? 1 : 0
  bucket = aws_s3_bucket.frontend_preview[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "AllowCloudFrontServicePrincipal"
      Effect = "Allow"
      Principal = {
        Service = "cloudfront.amazonaws.com"
      }
      Action   = "s3:GetObject"
      Resource = "${aws_s3_bucket.frontend_preview[0].arn}/*"
      Condition = {
        StringEquals = {
          "AWS:SourceArn" = aws_cloudfront_distribution.preview[0].arn
        }
      }
    }]
  })
}
