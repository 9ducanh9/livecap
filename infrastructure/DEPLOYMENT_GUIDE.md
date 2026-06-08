# LiveCap AWS Deployment Guide

This guide walks through deploying LiveCap to AWS using the provided Terraform Infrastructure as Code templates.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Initial Setup](#initial-setup)
3. [Infrastructure Deployment](#infrastructure-deployment)
4. [Application Deployment](#application-deployment)
5. [Verification](#verification)
6. [Ongoing Operations](#ongoing-operations)
7. [Troubleshooting](#troubleshooting)

## Prerequisites

### Required Tools

1. **AWS CLI** (version 2.x or later)
   ```bash
   aws --version
   ```

2. **Terraform** (version 1.0 or later)
   ```bash
   terraform --version
   ```

3. **Docker** (for building backend container)
   ```bash
   docker --version
   ```

4. **Node.js and npm** (for building frontend)
   ```bash
   node --version
   npm --version
   ```

### AWS Account Setup

1. **AWS Account**: Active AWS account with billing enabled
2. **IAM User/Role**: Credentials with permissions to create:
   - S3 buckets
   - CloudFront distributions
   - ECS clusters and services
   - Application Load Balancers
   - IAM roles and policies
   - ECR repositories
   - CloudWatch log groups
   - VPC security groups (if using existing VPC)

3. **AWS CLI Configuration**:
   ```bash
   aws configure
   # Enter your AWS Access Key ID
   # Enter your AWS Secret Access Key
   # Enter your default region (e.g., us-east-1)
   # Enter output format (json recommended)
   ```

4. **Verify AWS Access**:
   ```bash
   aws sts get-caller-identity
   ```

## Initial Setup

### Step 1: Configure Terraform Variables

1. Navigate to the Terraform directory:
   ```bash
   cd infrastructure/terraform
   ```

2. Copy the example variables file:
   ```bash
   cp terraform.tfvars.example terraform.tfvars
   ```

3. Edit `terraform.tfvars` with your configuration:
   ```hcl
   aws_region   = "us-east-1"
   environment  = "dev"
   project_name = "livecap"
   
   # Optional: Customize bucket names (must be globally unique)
   # frontend_bucket_name   = "my-company-livecap-frontend"
   # transcript_bucket_name = "my-company-livecap-transcripts"
   
   # Optional: Adjust resource sizing
   ecs_task_cpu      = 512
   ecs_task_memory   = 1024
   ecs_desired_count = 1

   # Production backend TLS:
   # alb_ssl_certificate_arn = "arn:aws:acm:REGION:ACCOUNT_ID:certificate/BACKEND_CERT_ID"
   # backend_domain_name     = "api.livecap.example.com"
   ```

### Step 2: Review Configuration

1. Review all Terraform files to understand what will be created
2. Check cost implications (see Cost Estimation section below)
3. Ensure bucket names are unique if specified

## Infrastructure Deployment

### Step 1: Initialize Terraform

```bash
cd infrastructure/terraform
terraform init
```

This downloads required provider plugins and prepares the working directory.

### Step 2: Validate Configuration

```bash
terraform validate
```

Ensures all `.tf` files are syntactically valid.

### Step 3: Review Execution Plan

```bash
terraform plan
```

Review the plan carefully. Terraform will show:
- Resources to be created (green `+`)
- Resources to be modified (yellow `~`)
- Resources to be destroyed (red `-`)

Expected resources:
- 2 S3 buckets (frontend + transcripts)
- 1 CloudFront distribution
- 1 Application Load Balancer
- 1 ECS cluster
- 1 ECS service
- 1 ECS task definition
- 1 ECR repository
- 2 CloudWatch log groups
- 4 IAM roles/policies
- 2 Security groups
- Various supporting resources

### Step 4: Create ECR First

```bash
terraform apply -target=aws_ecr_repository.backend
```

Type `yes` when prompted. This creates only the ECR repository so the first Docker image can be pushed before the ECS service starts.

### Step 5: Save Outputs

```bash
terraform output > outputs.txt
```

Save these values for the next steps:
- `ecr_repository_uri`: For pushing Docker images
- `frontend_bucket_name`: For uploading frontend assets
- `cloudfront_distribution_id`: For cache invalidation
- `alb_backend_base_url`: For backend API access
- `alb_websocket_url`: For backend WebSocket access
- `cloudfront_url`: For frontend access

## Application Deployment

### Step 1: Build and Push Backend Container

#### 1a. Authenticate with ECR

```bash
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin $(terraform output -raw ecr_repository_uri)
```

#### 1b. Build Docker Image

```bash
cd ../../backend
docker build -t livecap-backend .
```

#### 1c. Tag and Push Image

```bash
docker tag livecap-backend:latest $(terraform output -raw ecr_repository_uri):latest
docker push $(terraform output -raw ecr_repository_uri):latest
```

#### 1d. Verify ECS Service

ECS will automatically pull the image and start tasks. Check status:

First apply the remaining infrastructure:

```bash
cd ../infrastructure/terraform
terraform apply
```

```bash
aws ecs describe-services \
  --cluster $(terraform output -raw ecs_cluster_name) \
  --services $(terraform output -raw ecs_service_name) \
  --query 'services[0].{Status:status,Running:runningCount,Desired:desiredCount}'
```

Wait until `Running` equals `Desired` (usually 1-2 minutes).

### Step 2: Build and Deploy Frontend

#### 2a. Configure Frontend Environment

```bash
cd ../frontend

# Create production environment file
cat > .env.production << EOF
VITE_API_BASE_URL=$(cd ../infrastructure/terraform && terraform output -raw alb_backend_base_url)
VITE_WS_URL=$(cd ../infrastructure/terraform && terraform output -raw alb_websocket_url)
EOF
```

#### 2b. Build Frontend

```bash
npm install
npm run build
```

This creates an optimized production build in the `dist/` directory.

#### 2c. Upload to S3

```bash
aws s3 sync dist/ s3://$(cd ../infrastructure/terraform && terraform output -raw frontend_bucket_name)/ --delete
```

The `--delete` flag removes old files not in the new build.

#### 2d. Invalidate CloudFront Cache

```bash
aws cloudfront create-invalidation \
  --distribution-id $(cd ../infrastructure/terraform && terraform output -raw cloudfront_distribution_id) \
  --paths "/*"
```

Cache invalidation takes 1-2 minutes to propagate globally.

## Verification

### Step 1: Check Backend Health

```bash
curl $(terraform output -raw alb_backend_base_url)/api/health
```

Expected response:
```json
{
  "status": "healthy",
  "version": "1.0.0"
}
```

### Step 2: Access Frontend

```bash
echo "Frontend URL: $(terraform output -raw cloudfront_url)"
```

Open this URL in your browser. You should see the LiveCap interface.

### Step 3: Test End-to-End

1. Click "Start" to begin capture
2. Grant microphone permission
3. Speak in Vietnamese or English
4. Verify captions appear in both columns
5. Click "Stop" to end capture
6. Test export functionality

### Step 4: Check Logs

```bash
aws logs tail $(terraform output -raw cloudwatch_log_group_name) --follow
```

Look for:
- Session start events
- Transcription activity
- No error messages

## Ongoing Operations

### Update Backend Code

```bash
cd backend
# Make your changes
docker build -t livecap-backend .
docker tag livecap-backend:latest $(cd ../infrastructure/terraform && terraform output -raw ecr_repository_uri):latest
docker push $(cd ../infrastructure/terraform && terraform output -raw ecr_repository_uri):latest

# Force ECS to deploy new version
aws ecs update-service \
  --cluster $(cd ../infrastructure/terraform && terraform output -raw ecs_cluster_name) \
  --service $(cd ../infrastructure/terraform && terraform output -raw ecs_service_name) \
  --force-new-deployment
```

### Update Frontend Code

```bash
cd frontend
# Make your changes
npm run build
aws s3 sync dist/ s3://$(cd ../infrastructure/terraform && terraform output -raw frontend_bucket_name)/ --delete
aws cloudfront create-invalidation \
  --distribution-id $(cd ../infrastructure/terraform && terraform output -raw cloudfront_distribution_id) \
  --paths "/*"
```

### Update Infrastructure

```bash
cd infrastructure/terraform
# Edit .tf files or terraform.tfvars
terraform plan
terraform apply
```

### Scale ECS Service

Manually adjust task count:

```bash
aws ecs update-service \
  --cluster $(terraform output -raw ecs_cluster_name) \
  --service $(terraform output -raw ecs_service_name) \
  --desired-count 2
```

Or update `ecs_desired_count` in `terraform.tfvars` and run `terraform apply`.

### Monitor Costs

1. AWS Cost Explorer: https://console.aws.amazon.com/cost-management/
2. Set up billing alerts for unexpected costs
3. Main cost drivers:
   - Amazon Transcribe: ~$0.024/minute × 2 streams
   - Amazon Translate: ~$15 per million characters
   - ECS Fargate: ~$0.04/vCPU-hour + $0.004/GB-hour
   - ALB: ~$0.0225/hour + $0.008/LCU-hour

### View Logs

```bash
# Tail logs in real-time
aws logs tail $(terraform output -raw cloudwatch_log_group_name) --follow

# View logs from last hour
aws logs tail $(terraform output -raw cloudwatch_log_group_name) --since 1h

# Search logs
aws logs filter-log-events \
  --log-group-name $(terraform output -raw cloudwatch_log_group_name) \
  --filter-pattern "ERROR"
```

## Troubleshooting

### ECS Tasks Not Starting

**Symptoms**: `runningCount` stays at 0

**Solutions**:
1. Check task stopped reason:
   ```bash
   aws ecs describe-tasks \
     --cluster $(terraform output -raw ecs_cluster_name) \
     --tasks $(aws ecs list-tasks --cluster $(terraform output -raw ecs_cluster_name) --query 'taskArns[0]' --output text)
   ```

2. Common issues:
   - Docker image not found in ECR → Push image
   - Insufficient task role permissions → Check IAM policies
   - Container health check failing → Check application logs

### ALB Health Checks Failing

**Symptoms**: Tasks start but immediately stop

**Solutions**:
1. Check security group allows traffic from ALB to ECS tasks
2. Verify `/api/health` endpoint returns 200
3. Check CloudWatch logs for application errors
4. Ensure container port matches task definition (8000)

### Frontend Not Loading

**Symptoms**: CloudFront URL returns 404 or blank page

**Solutions**:
1. Verify files in S3:
   ```bash
   aws s3 ls s3://$(terraform output -raw frontend_bucket_name)/
   ```
2. Check CloudFront distribution status (wait if "In Progress")
3. Invalidate cache
4. Check browser console for errors

### WebSocket Connection Fails

**Symptoms**: Frontend connects but WebSocket fails

**Solutions**:
1. Verify ALB supports WebSocket (protocol upgrade)
2. Check CORS configuration in backend
3. Ensure `ALLOWED_ORIGIN` matches CloudFront URL
4. Check backend logs for connection errors

### High AWS Costs

**Solutions**:
1. Check Transcribe usage (main cost driver)
2. Verify session timeouts are working (prevent abandoned sessions)
3. Consider single-language detection instead of dual-stream
4. Review S3 lifecycle policies
5. Reduce log retention period

### Terraform State Lock

**Symptoms**: `terraform apply` fails with lock error

**Solutions**:
```bash
# Force unlock (use carefully)
terraform force-unlock <LOCK_ID>
```

## Cost Estimation

### Development Environment (Low Usage)

| Service | Monthly Cost |
|---------|-------------|
| ECS Fargate (1 task, 512 CPU, 1GB) | ~$15 |
| ALB | ~$16 |
| S3 Storage (1GB) | $0.02 |
| CloudFront (10GB transfer) | $1 |
| Transcribe (60 min × 2 streams) | $2.88 |
| Translate (100K chars) | $1.50 |
| **Total** | **~$36/month** |

### Production Environment (Moderate Usage)

| Service | Monthly Cost |
|---------|-------------|
| ECS Fargate (2 tasks avg, 512 CPU, 1GB) | ~$30 |
| ALB | ~$16 |
| S3 Storage (10GB) | $0.23 |
| CloudFront (100GB transfer) | $8.50 |
| Transcribe (500 hours × 2 streams) | $1,440 |
| Translate (5M chars) | $75 |
| **Total** | **~$1,570/month** |

**Note**: Transcribe and Translate are usage-based and dominate costs at scale.

## Clean Up

To destroy all resources:

```bash
cd infrastructure/terraform

# Empty S3 buckets first
aws s3 rm s3://$(terraform output -raw frontend_bucket_name) --recursive
aws s3 rm s3://$(terraform output -raw transcript_bucket_name) --recursive

# Destroy infrastructure
terraform destroy
```

Type `yes` when prompted. This removes all AWS resources and stops billing.

## Next Steps

1. **Custom Domain**: Configure Route 53 and ACM certificate
2. **CI/CD**: Set up GitHub Actions or AWS CodePipeline
3. **Monitoring**: Configure CloudWatch alarms and dashboards
4. **Backup**: Enable automated S3 bucket replication
5. **Security**: Implement AWS WAF rules for ALB and CloudFront
6. **Performance**: Configure CloudFront caching strategies
7. **Compliance**: Enable AWS CloudTrail and Config for auditing

## Support Resources

- [AWS ECS Documentation](https://docs.aws.amazon.com/ecs/)
- [Terraform AWS Provider](https://registry.terraform.io/providers/hashicorp/aws/latest/docs)
- [Amazon Transcribe Streaming](https://docs.aws.amazon.com/transcribe/latest/dg/streaming.html)
- [Amazon Translate](https://docs.aws.amazon.com/translate/)
- [CloudFront Developer Guide](https://docs.aws.amazon.com/cloudfront/)
