resource "aws_security_group" "benchmark_alb" {
  name        = "${local.prefix}-alb"
  description = "Benchmark CloudFront-origin ingress only"
  vpc_id      = data.aws_vpc.shared.id
  ingress {
    from_port       = 443
    to_port         = 443
    protocol        = "tcp"
    prefix_list_ids = [data.aws_ec2_managed_prefix_list.cloudfront.id]
  }
  egress {
    from_port   = 8000
    to_port     = 8000
    protocol    = "tcp"
    cidr_blocks = [data.aws_vpc.shared.cidr_block]
  }
}
resource "aws_security_group" "benchmark_tasks" {
  name        = "${local.prefix}-tasks"
  description = "Benchmark tasks accept only their benchmark ALB"
  vpc_id      = data.aws_vpc.shared.id
  ingress {
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [aws_security_group.benchmark_alb.id]
  }
  egress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
resource "aws_lb" "benchmark" {
  name               = "${local.prefix}-alb"
  internal           = false
  load_balancer_type = "application"
  subnets            = var.shared_public_subnet_ids
  security_groups    = [aws_security_group.benchmark_alb.id]
  idle_timeout       = 60
  depends_on         = [terraform_data.benchmark_guard]
}
resource "aws_lb_target_group" "benchmark" {
  name                 = "${local.prefix}-tg"
  port                 = 8000
  protocol             = "HTTP"
  vpc_id               = data.aws_vpc.shared.id
  target_type          = "ip"
  deregistration_delay = 30
  health_check {
    path                = "/api/health"
    matcher             = "200"
    interval            = 30
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }
}
resource "aws_acm_certificate" "benchmark" {
  domain_name       = var.benchmark_origin_hostname
  validation_method = "DNS"
}

# External DNS is intentionally a prerequisite, never an edit to production DNS.
resource "aws_acm_certificate_validation" "benchmark" {
  certificate_arn = aws_acm_certificate.benchmark.arn
}

# NEW listener on NEW ALB. Never reference the stable/preview certificate or listener.
resource "aws_lb_listener" "benchmark" {
  load_balancer_arn = aws_lb.benchmark.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = aws_acm_certificate_validation.benchmark.certificate_arn
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.benchmark.arn
  }
}
resource "aws_cloudfront_distribution" "benchmark" {
  enabled         = true
  is_ipv6_enabled = false
  comment         = "${local.prefix}: isolated benchmark API and WebSocket"
  price_class     = "PriceClass_100"
  web_acl_id      = aws_wafv2_web_acl.benchmark_edge.arn
  origin {
    domain_name = var.benchmark_origin_hostname
    origin_id   = local.prefix
    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "https-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }
  default_cache_behavior {
    target_origin_id         = local.prefix
    viewer_protocol_policy   = "https-only"
    allowed_methods          = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
    cached_methods           = ["GET", "HEAD"]
    cache_policy_id          = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad"
    origin_request_policy_id = "b689b0a8-53d0-40ab-baf2-68738e2966ac"
    compress                 = false
  }
  viewer_certificate { cloudfront_default_certificate = true }
  restrictions {
    geo_restriction { restriction_type = "none" }
  }
}
