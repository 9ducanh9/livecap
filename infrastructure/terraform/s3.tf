# S3 Buckets for LiveCap

# Generate unique bucket names if not provided
locals {
  frontend_bucket_name   = var.frontend_bucket_name != "" ? var.frontend_bucket_name : "${var.project_name}-frontend-${var.environment}-${data.aws_caller_identity.current.account_id}"
  transcript_bucket_name = var.transcript_bucket_name != "" ? var.transcript_bucket_name : "${var.project_name}-transcripts-${var.environment}-${data.aws_caller_identity.current.account_id}"
}

# Data source for AWS account ID
data "aws_caller_identity" "current" {}

# Frontend Bucket - Public read via CloudFront
resource "aws_s3_bucket" "frontend" {
  bucket = local.frontend_bucket_name

  tags = merge(
    var.tags,
    {
      Name        = "${var.project_name}-frontend-${var.environment}"
      Environment = var.environment
      Purpose     = "Frontend static assets"
    }
  )
}

resource "aws_s3_bucket_public_access_block" "frontend" {
  bucket = aws_s3_bucket.frontend.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "frontend" {
  bucket = aws_s3_bucket.frontend.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_policy" "frontend_cloudfront_access" {
  bucket = aws_s3_bucket.frontend.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowCloudFrontServicePrincipal"
        Effect = "Allow"
        Principal = {
          Service = "cloudfront.amazonaws.com"
        }
        Action   = "s3:GetObject"
        Resource = "${aws_s3_bucket.frontend.arn}/*"
        Condition = {
          StringEquals = {
            "AWS:SourceArn" = aws_cloudfront_distribution.frontend.arn
          }
        }
      }
    ]
  })
}

# Transcript Bucket - Private, backend-only access
resource "aws_s3_bucket" "transcript" {
  bucket = local.transcript_bucket_name

  tags = merge(
    var.tags,
    {
      Name        = "${var.project_name}-transcripts-${var.environment}"
      Environment = var.environment
      Purpose     = "Transcript storage"
    }
  )
}

resource "aws_s3_bucket_public_access_block" "transcript" {
  bucket = aws_s3_bucket.transcript.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "transcript" {
  bucket = aws_s3_bucket.transcript.id

  versioning_configuration {
    status = "Enabled"
  }
}

# S3 lifecycle policy for configurable transcript retention (14 days by default).
resource "aws_s3_bucket_lifecycle_configuration" "transcript_retention" {
  bucket = aws_s3_bucket.transcript.id

  rule {
    id     = "delete-old-transcripts"
    status = "Enabled"

    filter {
      prefix = "transcripts/"
    }

    expiration {
      days = var.transcript_retention_days
    }

    noncurrent_version_expiration {
      noncurrent_days = 1
    }
  }
}

# Enable server-side encryption
resource "aws_s3_bucket_server_side_encryption_configuration" "frontend" {
  bucket = aws_s3_bucket.frontend.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "transcript" {
  bucket = aws_s3_bucket.transcript.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}
