# Legacy VPC discovery.
#
# These data sources and security groups keep the currently deployed backend
# intact during the blue/green migration. The dedicated target VPC below is the
# destination architecture and must be cut over before the legacy resources are
# removed in a separate, explicitly reviewed change.

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

  filter {
    name   = "availability-zone"
    values = var.legacy_availability_zones
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

  filter {
    name   = "availability-zone"
    values = var.legacy_availability_zones
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
    description     = "Selected origin protocol from CloudFront origin-facing addresses"
    from_port       = var.alb_ssl_certificate_arn != "" ? 443 : 80
    to_port         = var.alb_ssl_certificate_arn != "" ? 443 : 80
    protocol        = "tcp"
    prefix_list_ids = [data.aws_ec2_managed_prefix_list.cloudfront_origin_facing.id]
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

# Dedicated target VPC for the hardened LiveCap backend.

data "aws_ec2_managed_prefix_list" "cloudfront_origin_facing" {
  name = "com.amazonaws.global.cloudfront.origin-facing"
}

resource "aws_vpc" "target" {
  cidr_block           = var.target_vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = merge(
    var.tags,
    {
      Name        = "${var.project_name}-target-${var.environment}"
      Environment = var.environment
      Migration   = "blue-green-target"
    }
  )
}

resource "aws_internet_gateway" "target" {
  vpc_id = aws_vpc.target.id

  tags = merge(
    var.tags,
    {
      Name        = "${var.project_name}-target-igw-${var.environment}"
      Environment = var.environment
    }
  )
}

resource "aws_subnet" "target_public" {
  for_each = var.target_public_subnets

  vpc_id                  = aws_vpc.target.id
  availability_zone       = each.value.availability_zone
  cidr_block              = each.value.cidr_block
  map_public_ip_on_launch = true

  tags = merge(
    var.tags,
    {
      Name        = "${var.project_name}-target-public-${each.key}-${var.environment}"
      Environment = var.environment
      Tier        = "public"
    }
  )
}

resource "aws_subnet" "target_private" {
  for_each = var.target_private_subnets

  vpc_id                  = aws_vpc.target.id
  availability_zone       = each.value.availability_zone
  cidr_block              = each.value.cidr_block
  map_public_ip_on_launch = false

  tags = merge(
    var.tags,
    {
      Name        = "${var.project_name}-target-private-${each.key}-${var.environment}"
      Environment = var.environment
      Tier        = "private"
    }
  )
}

resource "aws_route_table" "target_public" {
  vpc_id = aws_vpc.target.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.target.id
  }

  tags = merge(
    var.tags,
    {
      Name        = "${var.project_name}-target-public-${var.environment}"
      Environment = var.environment
    }
  )
}

resource "aws_route_table_association" "target_public" {
  for_each = var.target_public_subnets

  subnet_id      = aws_subnet.target_public[each.key].id
  route_table_id = aws_route_table.target_public.id
}

resource "aws_eip" "target_nat" {
  domain = "vpc"

  tags = merge(
    var.tags,
    {
      Name        = "${var.project_name}-target-nat-${var.environment}"
      Environment = var.environment
    }
  )

  depends_on = [aws_internet_gateway.target]
}

resource "aws_nat_gateway" "target" {
  allocation_id = aws_eip.target_nat.id
  subnet_id     = aws_subnet.target_public[var.target_nat_gateway_subnet_key].id

  tags = merge(
    var.tags,
    {
      Name        = "${var.project_name}-target-nat-${var.environment}"
      Environment = var.environment
    }
  )

  depends_on = [aws_internet_gateway.target]
}

resource "aws_route_table" "target_private" {
  vpc_id = aws_vpc.target.id

  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.target.id
  }

  tags = merge(
    var.tags,
    {
      Name        = "${var.project_name}-target-private-${var.environment}"
      Environment = var.environment
    }
  )
}

resource "aws_route_table_association" "target_private" {
  for_each = var.target_private_subnets

  subnet_id      = aws_subnet.target_private[each.key].id
  route_table_id = aws_route_table.target_private.id
}

resource "aws_security_group" "target_alb" {
  name        = "${var.project_name}-target-alb-${var.environment}"
  description = "CloudFront-only ingress for the target LiveCap ALB"
  vpc_id      = aws_vpc.target.id

  ingress {
    description     = "Selected origin protocol from CloudFront origin-facing addresses"
    from_port       = var.target_alb_ssl_certificate_arn != "" ? 443 : 80
    to_port         = var.target_alb_ssl_certificate_arn != "" ? 443 : 80
    protocol        = "tcp"
    prefix_list_ids = [data.aws_ec2_managed_prefix_list.cloudfront_origin_facing.id]
  }

  egress {
    description = "Forward traffic to target Fargate tasks"
    from_port   = var.container_port
    to_port     = var.container_port
    protocol    = "tcp"
    cidr_blocks = [var.target_vpc_cidr]
  }

  tags = merge(
    var.tags,
    {
      Name        = "${var.project_name}-target-alb-${var.environment}"
      Environment = var.environment
    }
  )
}

resource "aws_security_group" "target_ecs_tasks" {
  name        = "${var.project_name}-target-ecs-${var.environment}"
  description = "Private Fargate task access from the target ALB only"
  vpc_id      = aws_vpc.target.id

  ingress {
    description     = "Backend traffic from target ALB"
    from_port       = var.container_port
    to_port         = var.container_port
    protocol        = "tcp"
    security_groups = [aws_security_group.target_alb.id]
  }

  egress {
    description = "AWS APIs and package endpoints through the shared NAT gateway"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(
    var.tags,
    {
      Name        = "${var.project_name}-target-ecs-${var.environment}"
      Environment = var.environment
    }
  )
}
