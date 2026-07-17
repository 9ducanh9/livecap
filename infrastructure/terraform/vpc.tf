# Dedicated VPC for the hardened LiveCap backend.

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

# --- Optional second NAT gateway for multi-AZ egress (enable_multi_az_nat) ---
# Additive by design: the primary NAT above is untouched. When disabled
# (default) every private subnet keeps routing through the single primary NAT,
# so `terraform plan` shows no change. When enabled, a second NAT is created in
# the secondary AZ and private subnets in that AZ route through it, removing the
# single-AZ egress dependency.

locals {
  secondary_nat_az = var.target_public_subnets[var.target_nat_gateway_secondary_subnet_key].availability_zone
}

resource "aws_eip" "target_nat_secondary" {
  count = var.enable_multi_az_nat ? 1 : 0

  domain = "vpc"

  tags = merge(
    var.tags,
    {
      Name        = "${var.project_name}-target-nat-secondary-${var.environment}"
      Environment = var.environment
    }
  )

  depends_on = [aws_internet_gateway.target]
}

resource "aws_nat_gateway" "target_secondary" {
  count = var.enable_multi_az_nat ? 1 : 0

  allocation_id = aws_eip.target_nat_secondary[0].id
  subnet_id     = aws_subnet.target_public[var.target_nat_gateway_secondary_subnet_key].id

  tags = merge(
    var.tags,
    {
      Name        = "${var.project_name}-target-nat-secondary-${var.environment}"
      Environment = var.environment
    }
  )

  depends_on = [aws_internet_gateway.target]
}

resource "aws_route_table" "target_private_secondary" {
  count = var.enable_multi_az_nat ? 1 : 0

  vpc_id = aws_vpc.target.id

  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.target_secondary[0].id
  }

  tags = merge(
    var.tags,
    {
      Name        = "${var.project_name}-target-private-secondary-${var.environment}"
      Environment = var.environment
    }
  )
}

resource "aws_route_table_association" "target_private" {
  for_each = var.target_private_subnets

  subnet_id = aws_subnet.target_private[each.key].id
  # Route through the NAT in the subnet's own AZ when multi-AZ egress is on;
  # otherwise (default) through the single primary NAT.
  route_table_id = (
    var.enable_multi_az_nat &&
    each.value.availability_zone == local.secondary_nat_az
  ) ? one(aws_route_table.target_private_secondary[*].id) : aws_route_table.target_private.id
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
