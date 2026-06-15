# LiveCap Terraform Infrastructure

This directory contains Terraform Infrastructure as Code (IaC) templates for deploying the LiveCap application on AWS.

## Architecture Overview

The infrastructure provisions:

- **Frontend Hosting**: S3 bucket + CloudFront CDN with HTTPS
- **Backend Services**: ECS Fargate cluster with Application Load Balancer
- **Storage**: Isolated S3 buckets for frontend assets and transcript storage
- **Container Registry**: Amazon ECR for Docker images
- **Monitoring**: CloudWatch Logs with configurable retention
- **Security**: IAM roles, security groups, TLS termination, bucket isolation

## Prerequisites

1. **AWS CLI** configured with appropriate credentials
2. **Terraform** >= 1.0 installed
3. **Docker** for building container images
4. An AWS account with permissions to create:
   - S3 buckets
   - CloudFront distributions
   - ECS clusters, services, and task definitions
   - Application Load Balancers
   - IAM roles and policies
   - ECR repositories
   - CloudWatch log groups

## Quick Start

### 0. Bootstrap remote state first

Remote state is managed by a separate bootstrap stack:

```bash
cd infrastructure/bootstrap/remote-state
terraform init
terraform plan
```

Apply the bootstrap stack only after reviewing the plan. Copy the
`state_bucket_name` output into a local, untracked
`infrastructure/terraform/backend.hcl` file:

```hcl
bucket = "livecap-terraform-state-dev-123456789012"
```

The main stack uses an S3 backend with native lockfiles, so Terraform 1.10 or
newer is required. Do not run `terraform init -migrate-state` until the
migration plan has been reviewed.

### 1. Initialize Terraform

```bash
cd infrastructure/terraform
terraform init -backend-config=backend.hcl
```

### 2. Create a terraform.tfvars file

```hcl
aws_region    = "ap-southeast-1"
environment   = "dev"
project_name  = "livecap"

# Optional: Provide custom bucket names (must be globally unique)
# frontend_bucket_name   = "my-livecap-frontend-bucket"
# transcript_bucket_name = "my-livecap-transcript-bucket"

# Optional: Configure ECS resources
ecs_task_cpu          = 512
ecs_task_memory       = 1024
backend_desired_count = 0
backend_min_capacity  = 0
backend_max_capacity  = 1

# Optional: Configure retention periods
transcript_retention_days = 30
log_retention_days        = 7

# Budget alerts are delayed by AWS Billing and are not real-time.
monthly_budget_limit_usd = 50
# budget_notification_email = "billing-alerts@example.com"

# Keep ECS at max=1 while WebSocket session limits are in-memory.
max_concurrent_sessions = 4
max_sessions_per_ip     = 1

# Optional: Provide backend ALB TLS certificate (REQUIRED for production)
# alb_ssl_certificate_arn = "arn:aws:acm:REGION:ACCOUNT_ID:certificate/BACKEND_CERT_ID"
# backend_domain_name = "api.livecap.example.com"

# Optional: Provide CloudFront custom domain and certificate
# cloudfront_ssl_certificate_arn = "arn:aws:acm:us-east-1:ACCOUNT_ID:certificate/FRONTEND_CERT_ID"
# custom_domain = "livecap.example.com"

# WARNING: Without alb_ssl_certificate_arn, ALB uses insecure HTTP on port 80 (development only)
```

### 3. Review the Execution Plan

```bash
terraform plan
```

### 4. Deploy the Infrastructure

```bash
terraform apply
```

Terraform will prompt for confirmation. Type `yes` to proceed.

### 5. Note the Outputs

After deployment, Terraform will output important values:

- `cloudfront_url`: Frontend URL (HTTPS)
- `alb_backend_base_url`: Backend API URL
- `alb_websocket_url`: Backend WebSocket URL
- `ecr_repository_uri`: Container registry URI
- `frontend_bucket_name`: S3 bucket for frontend
- `transcript_bucket_name`: S3 bucket for transcripts

## Deployment Workflow

**IMPORTANT:** For first-time deployment, you must push a Docker image to ECR before applying the full Terraform infrastructure, as the ECS service will try to pull the `:latest` image immediately.

### Initial Deployment (First Time)

#### Step 1: Create ECR Repository First

```bash
cd infrastructure/terraform

# Apply only ECR to create the repository
terraform apply -target=aws_ecr_repository.backend

# Save ECR URI for next steps
export ECR_URI=$(terraform output -raw ecr_repository_uri)
```

#### Step 2: Build and Push Initial Docker Image

```bash
# Authenticate with ECR
aws ecr get-login-password --region ap-southeast-1 | docker login --username AWS --password-stdin $(terraform output -raw ecr_repository_uri)

# Build the Docker image
cd ../../backend
docker build -t livecap-backend .

# Tag and push
docker tag livecap-backend:latest $(terraform output -raw ecr_repository_uri):latest
docker push $(terraform output -raw ecr_repository_uri):latest
```

#### Step 2: Build and Push Initial Docker Image

```bash
# Authenticate with ECR
aws ecr get-login-password --region ap-southeast-1 | docker login --username AWS --password-stdin $(terraform output -raw ecr_repository_uri)

# Build the Docker image
cd ../../backend
docker build -t livecap-backend .

# Tag and push
docker tag livecap-backend:latest $(terraform output -raw ecr_repository_uri):latest
docker push $(terraform output -raw ecr_repository_uri):latest
```

#### Step 3: Apply Full Infrastructure

Now that the image exists in ECR, apply the complete infrastructure:

```bash
cd ../infrastructure/terraform
terraform apply
```

ECS will pull the `:latest` image and start tasks successfully.

---

### Subsequent Updates (After Initial Deploy)

For updates after the initial deployment, you can update backend code without recreating infrastructure:

#### Update Backend Code

```bash
# Build and push new image
cd backend
docker build -t livecap-backend:v2 .
docker tag livecap-backend:v2 $(cd ../infrastructure/terraform && terraform output -raw ecr_repository_uri):latest
docker push $(cd ../infrastructure/terraform && terraform output -raw ecr_repository_uri):latest

# Force ECS to deploy new version
aws ecs update-service \
  --cluster $(cd ../infrastructure/terraform && terraform output -raw ecs_cluster_name) \
  --service $(cd ../infrastructure/terraform && terraform output -raw ecs_service_name) \
  --force-new-deployment
```

#### Update Frontend Code

```bash
cd frontend
npm run build
aws s3 sync dist/ s3://$(cd ../infrastructure/terraform && terraform output -raw frontend_bucket_name)/ --delete
aws cloudfront create-invalidation \
  --distribution-id $(cd ../infrastructure/terraform && terraform output -raw cloudfront_distribution_id) \
  --paths "/*"
```

---

### Step 2 (Legacy - DO NOT USE for first deployment): Deploy ECS Service

The ECS service is automatically created by Terraform. After pushing the Docker image, ECS will pull and run it.

To force a new deployment:

```bash
aws ecs update-service \
  --cluster $(terraform output -raw ecs_cluster_name) \
  --service $(terraform output -raw ecs_service_name) \
  --force-new-deployment
```

### Step 3: Build and Deploy Frontend

```bash
cd ../../frontend

# Create production environment file
cat > .env.production << EOF
VITE_API_BASE_URL=$(cd ../infrastructure/terraform && terraform output -raw alb_backend_base_url)
VITE_WS_URL=$(cd ../infrastructure/terraform && terraform output -raw alb_websocket_url)
VITE_WAKE_BACKEND_URL=$(cd ../infrastructure/terraform && terraform output -raw wake_backend_url)
VITE_BACKEND_HEALTH_URL=$(cd ../infrastructure/terraform && terraform output -raw alb_backend_base_url)/api/health
VITE_BACKEND_WAKE_TIMEOUT_SECONDS=120
VITE_MAX_SESSION_SECONDS=1800
EOF

# Build the frontend
npm run build

# Upload to S3
aws s3 sync dist/ s3://$(cd ../infrastructure/terraform && terraform output -raw frontend_bucket_name)/ --delete

# Invalidate CloudFront cache
aws cloudfront create-invalidation \
  --distribution-id $(terraform output -raw cloudfront_distribution_id) \
  --paths "/*"
```

### Step 4: Access the Application

```bash
echo "Frontend URL: $(terraform output -raw cloudfront_url)"
echo "Backend API: $(terraform output -raw alb_backend_base_url)"
```

## Configuration Variables

### Core Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `aws_region` | AWS region for deployment | `ap-southeast-1` |
| `environment` | Environment name (dev/staging/prod) | `dev` |
| `project_name` | Project name for resource naming | `livecap` |

### S3 Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `transcript_retention_days` | Days to retain transcripts before deletion | `30` |
| `frontend_bucket_name` | Frontend S3 bucket name (auto-generated if empty) | `""` |
| `transcript_bucket_name` | Transcript S3 bucket name (auto-generated if empty) | `""` |

### ECS Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `ecs_task_cpu` | CPU units (256, 512, 1024, 2048, 4096) | `512` |
| `ecs_task_memory` | Memory in MiB (512, 1024, 2048, etc.) | `1024` |
| `backend_desired_count` | Initial backend task count; use `0` outside active demo/use windows | `0` |
| `backend_min_capacity` | Minimum tasks for autoscaling and scale-to-zero | `0` |
| `backend_max_capacity` | Maximum tasks; keep `1` while session limits are in-memory | `1` |
| `container_port` | Backend container port | `8000` |

### Application Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `session_timeout_seconds` | Max session duration | `1800` (30 min) |
| `download_link_expiration_seconds` | Presigned URL expiration | `86400` (24 hours) |
| `max_speakers` | Max speakers for diarization | `5` |

### Health Check Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `health_check_path` | ALB health check endpoint | `/api/health` |
| `health_check_interval` | Check interval in seconds | `30` |
| `health_check_timeout` | Check timeout in seconds | `5` |
| `healthy_threshold` | Successes required | `2` |
| `unhealthy_threshold` | Failures required | `3` |

### CloudFront Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `cloudfront_price_class` | Price class (All/200/100) | `PriceClass_100` |
| `alb_ssl_certificate_arn` | Required for production backend HTTPS/WSS. ACM certificate ARN for the ALB listener in the same AWS region as the ALB. Empty enables insecure HTTP dev mode. | `""` |
| `backend_domain_name` | Backend domain covered by `alb_ssl_certificate_arn`, for example `api.livecap.example.com`. Point this DNS name at the ALB before production use. | `""` |
| `cloudfront_ssl_certificate_arn` | ACM certificate ARN for a CloudFront custom domain. Must be in `us-east-1`. | `""` |
| `custom_domain` | Custom domain name | `""` |

### Network Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `vpc_id` | VPC ID (uses default if empty) | `""` |
| `public_subnet_ids` | Public subnet IDs for ALB | `[]` (auto-discovered) |
| `private_subnet_ids` | Private subnet IDs for ECS | `[]` (auto-discovered) |

### Autoscaling Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `autoscaling_target_cpu` | Target CPU % for scaling | `70` |
| `autoscaling_target_memory` | Target memory % for scaling | `80` |

## File Structure

```
infrastructure/terraform/
â”œâ”€â”€ main.tf              # Provider and Terraform configuration
â”œâ”€â”€ variables.tf         # Input variable definitions
â”œâ”€â”€ outputs.tf           # Output value definitions
â”œâ”€â”€ vpc.tf               # VPC and security groups
â”œâ”€â”€ s3.tf                # S3 buckets and lifecycle policies
â”œâ”€â”€ cloudfront.tf        # CloudFront distribution
â”œâ”€â”€ alb.tf               # Application Load Balancer
â”œâ”€â”€ ecs.tf               # ECS cluster, service, task definition
â”œâ”€â”€ iam.tf               # IAM roles and policies
â”œâ”€â”€ ecr.tf               # Elastic Container Registry
â”œâ”€â”€ cloudwatch.tf        # CloudWatch log groups
â””â”€â”€ README.md            # This file
```

## Security Features

1. **Bucket Isolation**: Frontend and transcript buckets are separate with distinct IAM policies
2. **TLS Everywhere**: ALB terminates TLS; CloudFront uses HTTPS
3. **IAM Task Roles**: No embedded credentials; automatic rotation
4. **Security Groups**: Least-privilege network access
5. **Encryption**: S3 server-side encryption enabled by default
6. **Private Backend**: ECS tasks optionally run in private subnets

## Cost Optimization

- **S3 Lifecycle Policies**: Automatic transcript cleanup after 30 days
- **Fargate Pay-per-Use**: No idle EC2 costs
- **CloudFront Caching**: Reduces S3 GET requests and improves performance
- **ECR Lifecycle**: Cleans up old container images
- **Right-Sizing**: Configurable CPU/memory for cost efficiency

## Monitoring and Operations

### View Logs

```bash
# Backend application logs
aws logs tail /ecs/livecap-backend-dev --follow

# View specific time range
aws logs tail /ecs/livecap-backend-dev --since 1h
```

### Check ECS Service Status

```bash
aws ecs describe-services \
  --cluster $(terraform output -raw ecs_cluster_name) \
  --services $(terraform output -raw ecs_service_name)
```

### Check Task Health

```bash
aws ecs list-tasks \
  --cluster $(terraform output -raw ecs_cluster_name) \
  --service-name $(terraform output -raw ecs_service_name)
```

### Scale Service Manually

```bash
aws ecs update-service \
  --cluster $(terraform output -raw ecs_cluster_name) \
  --service $(terraform output -raw ecs_service_name) \
  --desired-count 1
```

Keep desired count and autoscaling max at `1` while backend session limits are
process-local. For demo cost control, prefer scheduled scale-to-zero through
`enable_demo_scheduled_scaling`. If `enable_wake_endpoint=true` is reviewed and
applied, the frontend can call `wake_backend_url` before capture starts to bring
the ECS service back to one task. This still keeps the ALB running and does not
remove ALB hourly cost.

The MVP wake endpoint is a public Lambda Function URL with
`authorization_type = NONE`. It is convenient for demo use, but anyone who can
call it can wake ECS to one task. Use authentication, AWS WAF, and rate limiting
before real production use.

## Updating the Infrastructure

After modifying `.tf` files or variables:

```bash
# Review changes
terraform plan

# Apply changes
terraform apply
```

## Destroying the Infrastructure

**Warning**: This will delete all resources, including S3 buckets and logs.

```bash
# Empty S3 buckets first (required for deletion)
aws s3 rm s3://$(terraform output -raw frontend_bucket_name) --recursive
aws s3 rm s3://$(terraform output -raw transcript_bucket_name) --recursive

# Destroy infrastructure
terraform destroy
```

## Troubleshooting

### ECS Tasks Not Starting

1. Check CloudWatch logs for task errors
2. Verify Docker image exists in ECR
3. Check security group rules allow ALB â†’ ECS communication
4. Verify IAM task execution role has ECR pull permissions

### ALB Health Checks Failing

1. Ensure backend `/api/health` endpoint returns 200
2. Check security groups allow traffic on container port
3. Verify ECS tasks are running in correct subnets
4. Check CloudWatch logs for application errors

### Frontend Not Loading

1. Verify files are in S3 bucket: `aws s3 ls s3://$(terraform output -raw frontend_bucket_name)/`
2. Check CloudFront distribution status: `aws cloudfront get-distribution --id $(terraform output -raw cloudfront_distribution_id)`
3. Invalidate CloudFront cache if stale content

### High Costs

1. Check Transcribe/Translate usage (main cost drivers)
2. Verify S3 lifecycle policies are active
3. Review ECS task count and autoscaling policies
4. Monitor CloudWatch logs for unnecessary API calls

## Production Considerations

### Obtaining ACM Certificate for ALB (REQUIRED for Production)

**âš ï¸ CRITICAL:** Never deploy to production without TLS. Follow these steps to obtain an ACM certificate:

#### Option 1: Using AWS Certificate Manager (Recommended)

```bash
# Request certificate for your domain
aws acm request-certificate \
  --domain-name api.yourdomain.com \
  --validation-method DNS \
  --region ap-southeast-1

# Note the CertificateArn from output
# ARN format: arn:aws:acm:ap-southeast-1:ACCOUNT_ID:certificate/CERT_ID

# Validate certificate by adding DNS record
# Follow instructions in ACM console or:
aws acm describe-certificate \
  --certificate-arn <cert-arn> \
  --query 'Certificate.DomainValidationOptions'

# Add the CNAME record to your DNS provider
# Wait for validation (usually 5-10 minutes)

# Update terraform.tfvars with backend certificate ARN:
alb_ssl_certificate_arn = "arn:aws:acm:ap-southeast-1:ACCOUNT_ID:certificate/CERT_ID"
backend_domain_name = "api.yourdomain.com"
```

#### Option 2: Import Existing Certificate

```bash
aws acm import-certificate \
  --certificate fileb://certificate.pem \
  --private-key fileb://private-key.pem \
  --certificate-chain fileb://certificate-chain.pem \
  --region ap-southeast-1
```

#### Development Without Certificate

For **local development/testing only**, you can deploy without a certificate:
- ALB will create an HTTP listener on port 80 (insecure)
- Terraform output `alb_backend_base_url` will use `http://`
- Terraform output `alb_websocket_url` will use `ws://`
- **This configuration is NOT suitable for production**

```hcl
# terraform.tfvars for development
alb_ssl_certificate_arn = ""  # Empty = dev mode
```

---

### 1. State Management

Configure S3 backend for Terraform state (see `main.tf`):
2. **TLS Certificates**: Provide `alb_ssl_certificate_arn` for backend production traffic and CloudFront certs only when using a custom frontend domain
3. **Network Isolation**: Use private subnets for ECS tasks
4. **Monitoring**: Set up CloudWatch alarms for key metrics
5. **Backup**: Enable S3 versioning (already configured)
6. **CI/CD**: Integrate with AWS CodePipeline or GitHub Actions
7. **Multi-Environment**: Use workspaces or separate state files per environment

## Support

For issues or questions:
- Review CloudWatch logs
- Check AWS service health dashboard
