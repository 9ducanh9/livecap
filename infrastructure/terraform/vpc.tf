# VPC and Networking Configuration

# Use existing VPC if provided, otherwise use default VPC
data "aws_vpc" "selected" {
  id      = var.vpc_id != "" ? var.vpc_id : null
  default = var.vpc_id == "" ? true : null
}

# Get subnets if not provided
data "aws_subnets" "public" {
  count = length(var.public_subnet_ids) == 0 ? 1 : 0

  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.selected.id]
  }

  filter {
    name   = "map-public-ip-on-launch"
    values = ["true"]
  }
}

data "aws_subnets" "private" {
  count = length(var.private_subnet_ids) == 0 ? 1 : 0

  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.selected.id]
  }

  filter {
    name   = "map-public-ip-on-launch"
    values = ["false"]
  }
}

# Use provided subnets or discovered subnets
locals {
  public_subnet_ids  = length(var.public_subnet_ids) > 0 ? var.public_subnet_ids : (length(data.aws_subnets.public) > 0 ? data.aws_subnets.public[0].ids : [])
  private_subnet_ids = length(var.private_subnet_ids) > 0 ? var.private_subnet_ids : (length(data.aws_subnets.private) > 0 ? data.aws_subnets.private[0].ids : [])

  # If no private subnets, use public subnets for ECS tasks
  ecs_subnet_ids = length(local.private_subnet_ids) > 0 ? local.private_subnet_ids : local.public_subnet_ids

  # Determine if ECS tasks should have public IPs (required if using public subnets)
  assign_public_ip = length(local.private_subnet_ids) == 0
}

# Security Group for ALB
resource "aws_security_group" "alb" {
  name        = "${var.project_name}-alb-${var.environment}"
  description = "Security group for ${var.project_name} Application Load Balancer"
  vpc_id      = data.aws_vpc.selected.id

  ingress {
    description = "HTTPS from anywhere"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTP from anywhere (redirect to HTTPS)"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "Allow all outbound traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(
    var.tags,
    {
      Name        = "${var.project_name}-alb-${var.environment}"
      Environment = var.environment
    }
  )
}

# Security Group for ECS Tasks
resource "aws_security_group" "ecs_tasks" {
  name        = "${var.project_name}-ecs-tasks-${var.environment}"
  description = "Security group for ${var.project_name} ECS tasks"
  vpc_id      = data.aws_vpc.selected.id

  ingress {
    description     = "Allow traffic from ALB"
    from_port       = var.container_port
    to_port         = var.container_port
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    description = "Allow all outbound traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(
    var.tags,
    {
      Name        = "${var.project_name}-ecs-tasks-${var.environment}"
      Environment = var.environment
    }
  )
}
