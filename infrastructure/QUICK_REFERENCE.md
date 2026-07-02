# LiveCap Infrastructure Quick Reference

> **Legacy reference only.** The one-command deployment below is unsafe for the
> current empty/remote-state recovery and blue/green migration. Follow
> `terraform/README.md` and `terraform/IMPORT_PLAN.md`; review imports and the
> full plan before any apply.

## One-Command Deployment (Using Makefile)

```bash
cd infrastructure/terraform

# 1. Initialize Terraform and create ECR first
make init
terraform apply -target=aws_ecr_repository.backend

# 2. Push the initial backend image, then deploy infrastructure
make push-backend-image
make apply

# 3. Deploy frontend
make deploy-frontend

# 4. View application URL
make outputs
```

## Manual Deployment Steps

### Infrastructure Setup

```bash
cd infrastructure/terraform
terraform init
terraform plan
terraform apply -target=aws_ecr_repository.backend
```

### Backend Deployment

```bash
# Login to ECR
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin $(terraform output -raw ecr_repository_uri)

# Build and push
cd ../../backend
docker build -t livecap-backend .
docker tag livecap-backend:latest $(terraform output -raw ecr_repository_uri):latest
docker push $(terraform output -raw ecr_repository_uri):latest

# Force update
aws ecs update-service --cluster $(terraform output -raw ecs_cluster_name) --service $(terraform output -raw ecs_service_name) --force-new-deployment
```

### Frontend Deployment

```bash
cd frontend

# Configure backend URL
cat > .env.production << EOF
VITE_API_BASE_URL=$(terraform output -raw alb_backend_base_url)
VITE_WS_URL=$(terraform output -raw alb_websocket_url)
EOF

# Build and upload
npm run build
aws s3 sync dist/ s3://$(terraform output -raw frontend_bucket_name)/ --delete

# Invalidate cache
aws cloudfront create-invalidation --distribution-id $(terraform output -raw cloudfront_distribution_id) --paths "/*"
```

## Common Operations

### View Logs
```bash
aws logs tail $(terraform output -raw cloudwatch_log_group_name) --follow
```

### Check Service Status
```bash
aws ecs describe-services --cluster $(terraform output -raw ecs_cluster_name) --services $(terraform output -raw ecs_service_name)
```

### Scale Service
```bash
aws ecs update-service --cluster $(terraform output -raw ecs_cluster_name) --service $(terraform output -raw ecs_service_name) --desired-count 2
```

### Get Application URLs
```bash
terraform output cloudfront_url  # Frontend
terraform output alb_backend_base_url  # Backend API
```

## Key Configuration Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `ecs_task_cpu` | CPU units for backend | 512 |
| `ecs_task_memory` | Memory in MiB | 1024 |
| `ecs_desired_count` | Number of tasks | 1 |
| `transcript_retention_days` | S3 lifecycle retention | 30 |
| `session_timeout_seconds` | Max session duration | 1800 |

Edit `terraform.tfvars` to customize.

## Resource Outputs

| Output | Description |
|--------|-------------|
| `cloudfront_url` | Frontend HTTPS URL |
| `alb_backend_base_url` | Backend API URL |
| `alb_websocket_url` | Backend WebSocket URL |
| `ecr_repository_uri` | Docker registry |
| `frontend_bucket_name` | S3 frontend bucket |
| `transcript_bucket_name` | S3 transcript bucket |
| `ecs_cluster_name` | ECS cluster name |
| `cloudwatch_log_group_name` | Log group name |

## Troubleshooting Quick Checks

### Backend not starting?
```bash
# Check logs
aws logs tail $(terraform output -raw cloudwatch_log_group_name) --since 10m

# Check tasks
aws ecs list-tasks --cluster $(terraform output -raw ecs_cluster_name) --service-name $(terraform output -raw ecs_service_name)
```

### Frontend not loading?
```bash
# Check S3 files
aws s3 ls s3://$(terraform output -raw frontend_bucket_name)/

# Check CloudFront status
aws cloudfront get-distribution --id $(terraform output -raw cloudfront_distribution_id) --query 'Distribution.Status'
```

### High costs?
```bash
# Main cost drivers:
# 1. Amazon Transcribe (~$0.024/min × 2 streams)
# 2. Amazon Translate (~$15/million chars)
# 3. Check CloudWatch for usage patterns
```

## Clean Up

```bash
# Empty buckets
aws s3 rm s3://$(terraform output -raw frontend_bucket_name) --recursive
aws s3 rm s3://$(terraform output -raw transcript_bucket_name) --recursive

# Destroy infrastructure
terraform destroy
```

## File Structure

```
infrastructure/terraform/
├── main.tf           # Provider configuration
├── variables.tf      # Input variables
├── outputs.tf        # Output values
├── vpc.tf            # Networking and security groups
├── s3.tf             # S3 buckets with lifecycle policies
├── cloudfront.tf     # CDN distribution
├── alb.tf            # Load balancer with TLS
├── ecs.tf            # Container orchestration
├── iam.tf            # Roles and permissions
├── ecr.tf            # Container registry
└── cloudwatch.tf     # Logging configuration
```

## Important IAM Permissions

Task role has access to:
- ✅ Transcript S3 bucket (read/write)
- ✅ Amazon Transcribe Streaming
- ✅ Amazon Translate
- ✅ CloudWatch Logs
- ❌ Frontend S3 bucket (isolated for security)

## Network Architecture

```
Internet
   │
   ├─→ CloudFront (HTTPS) ─→ S3 Frontend Bucket
   │
   └─→ ALB (HTTPS/WSS) ─→ ECS Tasks ─→ AWS Services
```

## Estimated Costs

| Usage Level | Monthly Cost |
|-------------|-------------|
| Development (minimal) | ~$36 |
| Production (moderate) | ~$1,570 |

**Note**: Transcribe and Translate dominate costs at scale.

## Support

- Full guide: `DEPLOYMENT_GUIDE.md`
- Terraform docs: `terraform/README.md`
