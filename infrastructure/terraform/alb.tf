# Application Load Balancer for the dedicated target VPC.

resource "aws_lb" "target" {
  name               = "${var.project_name}-target-alb-${var.environment}"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.target_alb.id]
  subnets            = [for subnet in aws_subnet.target_public : subnet.id]

  enable_deletion_protection       = false
  enable_http2                     = true
  enable_cross_zone_load_balancing = true

  tags = merge(
    var.tags,
    {
      Name        = "${var.project_name}-target-alb-${var.environment}"
      Environment = var.environment
      Migration   = "blue-green-target"
    }
  )
}

resource "aws_lb_target_group" "target_backend" {
  name        = "${var.project_name}-target-tg-${var.environment}"
  port        = var.container_port
  protocol    = "HTTP"
  vpc_id      = aws_vpc.target.id
  target_type = "ip"

  health_check {
    enabled             = true
    healthy_threshold   = var.healthy_threshold
    unhealthy_threshold = var.unhealthy_threshold
    timeout             = var.health_check_timeout
    interval            = var.health_check_interval
    path                = var.health_check_path
    protocol            = "HTTP"
    matcher             = "200"
  }

  deregistration_delay = 30

  stickiness {
    type    = "lb_cookie"
    enabled = false
  }

  tags = merge(
    var.tags,
    {
      Name        = "${var.project_name}-target-tg-${var.environment}"
      Environment = var.environment
      Migration   = "blue-green-target"
    }
  )
}

resource "aws_lb_listener" "target_https" {
  count = var.target_alb_ssl_certificate_arn != "" ? 1 : 0

  load_balancer_arn = aws_lb.target.arn
  port              = "443"
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = var.target_alb_ssl_certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.target_backend.arn
  }
}

resource "aws_lb_listener" "target_http_dev" {
  count = var.target_alb_ssl_certificate_arn == "" ? 1 : 0

  load_balancer_arn = aws_lb.target.arn
  port              = "80"
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.target_backend.arn
  }
}
