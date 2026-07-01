# LiveCap Infrastructure as Code

This directory contains complete Infrastructure as Code (IaC) templates for deploying LiveCap to AWS using **Terraform**.

## 📋 Overview

LiveCap's infrastructure follows AWS Well-Architected Framework principles and provides:

- **Scalable Backend**: ECS Fargate with autoscaling based on CPU/memory
- **Global Frontend**: S3 + CloudFront CDN with HTTPS
- **Secure Storage**: Isolated S3 buckets for frontend and transcripts
- **High Availability**: Application Load Balancer with health checks
- **Observability**: CloudWatch Logs with configurable retention
- **Cost Optimization**: S3 lifecycle policies, pay-per-use Fargate, CloudFront caching

## 🚀 Quick Start

### Prerequisites
- AWS CLI configured
- Terraform >= 1.0
- Docker installed
- Node.js and npm

### Deploy in 3 Commands

```bash
cd infrastructure/terraform

# 1. Setup Terraform and create ECR
terraform init
terraform apply -target=aws_ecr_repository.backend

# 2. Push backend image, then apply full infrastructure
make push-backend-image
terraform apply

# 3. Deploy frontend
make deploy-frontend

# 4. Access your application
terraform output cloudfront_url
```

**Full guide**: See [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)

## 📁 Directory Structure

```
infrastructure/
├── terraform/                    # Terraform IaC templates
│   ├── main.tf                   # Provider and backend configuration
│   ├── variables.tf              # Input variable definitions
│   ├── outputs.tf                # Output values
│   ├── vpc.tf                    # Networking and security groups
│   ├── s3.tf                     # S3 buckets with lifecycle policies
│   ├── cloudfront.tf             # CloudFront CDN distribution
│   ├── alb.tf                    # Application Load Balancer
│   ├── ecs.tf                    # ECS cluster, service, task definition
│   ├── iam.tf                    # IAM roles and policies
│   ├── ecr.tf                    # Elastic Container Registry
│   ├── cloudwatch.tf             # CloudWatch log groups
│   ├── terraform.tfvars.example  # Example configuration
│   ├── Makefile                  # Automation commands
│   └── README.md                 # Detailed Terraform documentation
├── DEPLOYMENT_GUIDE.md           # Step-by-step deployment instructions
├── QUICK_REFERENCE.md            # Quick command reference
└── README.md                     # This file
```

## 🏗️ Architecture

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        End Users                            │
└────────────┬──────────────────────────┬─────────────────────┘
             │ HTTPS                    │ WSS
             ▼                          ▼
   ┌──────────────────┐      ┌──────────────────────┐
   │  CloudFront CDN  │      │  Application Load    │
   │  + TLS Cert      │      │  Balancer + TLS      │
   └────────┬─────────┘      └──────────┬───────────┘
            │                           │
            ▼                           ▼
   ┌──────────────────┐      ┌──────────────────────┐
   │  S3 Frontend     │      │  ECS Fargate Service │
   │  Bucket          │      │  (Auto-scaling)      │
   └──────────────────┘      └──────────┬───────────┘
                                        │
                             ┌──────────┴──────────┐
                             │  AWS Services       │
                             │  - Transcribe       │
                             │  - Translate        │
                             │  - S3 Transcripts   │
                             │  - CloudWatch       │
                             └─────────────────────┘
```

### Components Created

| Component | Purpose | Scalability |
|-----------|---------|-------------|
| **CloudFront** | Global CDN for frontend | Automatic edge caching |
| **S3 Frontend** | Static asset hosting | Unlimited storage |
| **S3 Transcripts** | Private transcript storage | Lifecycle policies |
| **ALB** | Load balancing + TLS | Cross-AZ distribution |
| **ECS Fargate** | Container orchestration | Auto-scales 1-4+ tasks |
| **ECR** | Container registry | Unlimited images |
| **CloudWatch** | Centralized logging | Configurable retention |
| **IAM Roles** | Secure AWS access | No embedded credentials |

## 🎯 Key Features

### Operational Excellence
- ✅ Health checks with automatic task restart
- ✅ Structured logging to CloudWatch
- ✅ Graceful shutdown handling
- ✅ Infrastructure as Code for reproducibility

### Security
- ✅ HTTPS/WSS everywhere (TLS 1.2+)
- ✅ Isolated S3 buckets with distinct policies
- ✅ IAM task roles (no embedded credentials)
- ✅ Security groups with least-privilege access
- ✅ CORS enforcement for API access

### Reliability
- ✅ ALB health checks with automatic recovery
- ✅ Stateless design supports horizontal scaling
- ✅ Multi-AZ load balancer deployment
- ✅ ECS task auto-restart on failure

### Performance
- ✅ CloudFront edge caching globally
- ✅ Fargate right-sizing (configurable)
- ✅ ALB connection draining
- ✅ Auto-scaling based on CPU/memory

### Cost Optimization
- ✅ Fargate pay-per-use (no idle EC2)
- ✅ S3 lifecycle policies (14-day retention by default)
- ✅ CloudFront caching reduces origin load
- ✅ ECR image cleanup policies
- ✅ Configurable log retention

## 📊 Configuration

### Key Variables

Edit `terraform/terraform.tfvars`:

```hcl
# AWS Configuration
aws_region   = "ap-southeast-1"
environment  = "dev"
project_name = "livecap"

# Target ECS configuration
ecs_task_cpu                 = 512       # 0.5 vCPU
ecs_task_memory              = 1024      # 1 GB
backend_image_tag            = "54c423b" # Immutable Git SHA already in ECR
target_backend_desired_count = 0
backend_min_capacity         = 0
backend_max_capacity         = 1         # In-memory session registry

# Retention Policies
transcript_retention_days = 14  # S3 lifecycle
log_retention_days        = 14  # CloudWatch

# Application Settings
session_timeout_seconds          = 1800   # 30 minutes
download_link_expiration_seconds = 86400  # 24 hours
```

See `terraform/variables.tf` for all available options.

## 🔧 Common Operations

### Deploy Infrastructure
```bash
cd terraform
terraform init
terraform apply
```

### Deploy Backend
```bash
make deploy-backend
```

### Deploy Frontend
```bash
make deploy-frontend
```

### View Logs
```bash
make logs
```

### Check Status
```bash
make status
```

### Scale Service
```bash
aws ecs update-service \
  --cluster $(terraform output -raw ecs_cluster_name) \
  --service $(terraform output -raw ecs_service_name) \
  --desired-count 2
```

## 💰 Cost Estimation

### Development Environment
- **Monthly**: ~$36
- ECS Fargate: $15
- ALB: $16
- Other services: $5

### Production Environment (Moderate Usage)
- **Monthly**: ~$1,570
- Amazon Transcribe: $1,440 (500 hours × 2 streams)
- Amazon Translate: $75 (5M characters)
- ECS Fargate: $30
- ALB: $16
- Other services: $9

**Note**: Transcribe and Translate are usage-based and dominate costs at scale.

### Cost Optimization Tips
1. Implement session timeouts to prevent abandoned streams
2. Consider single-language Transcribe (50% cost reduction)
3. Reduce log retention period if acceptable
4. Use CloudFront caching effectively
5. Set up AWS billing alerts

## 🔒 Security Considerations

### Bucket Isolation
- Frontend bucket: Public read via CloudFront only
- Transcript bucket: Private, backend-only access
- IAM task role: Access to transcripts only, NOT frontend

### Network Security
- All traffic over HTTPS/WSS (TLS 1.2+)
- ALB in public subnets, ECS in private subnets (configurable)
- Security groups enforce least-privilege access
- CORS enforced at application level

### Credential Management
- ECS task IAM roles (automatic rotation)
- No AWS keys in container images
- Secrets via environment variables (extendable to Secrets Manager)

## 📈 Monitoring and Observability

### CloudWatch Logs
```bash
# Tail logs
aws logs tail /ecs/livecap-backend-dev --follow

# Search for errors
aws logs filter-log-events \
  --log-group-name /ecs/livecap-backend-dev \
  --filter-pattern "ERROR"
```

### ECS Metrics
- CPU utilization (triggers autoscaling at 70%)
- Memory utilization (triggers autoscaling at 80%)
- Task count (running vs. desired)
- Health check status

### Recommended Alarms
1. ECS service no running tasks
2. ALB target group unhealthy targets > 0
3. ECS task CPU utilization > 90%
4. ALB 5XX errors > threshold
5. CloudWatch logs error rate > threshold

## 🐛 Troubleshooting

### ECS Tasks Not Starting
1. Check CloudWatch logs for errors
2. Verify Docker image exists in ECR
3. Check IAM task execution role permissions
4. Verify security groups allow ALB → ECS traffic

### Frontend Not Loading
1. Verify S3 files: `aws s3 ls s3://<bucket>/`
2. Check CloudFront status (wait if "In Progress")
3. Invalidate cache
4. Check browser console for errors

### High Costs
1. Check Transcribe usage in CloudWatch
2. Verify session timeouts are working
3. Review S3 storage growth
4. Check for failed tasks in restart loops

See [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md#troubleshooting) for detailed troubleshooting.

## 📚 Documentation

- **[DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)**: Complete step-by-step deployment instructions
- **[QUICK_REFERENCE.md](QUICK_REFERENCE.md)**: Quick command reference
- **[terraform/README.md](terraform/README.md)**: Detailed Terraform documentation

## 🔄 CI/CD Integration

The infrastructure can be integrated with CI/CD pipelines:

### GitHub Actions Example
```yaml
- name: Deploy Backend
  run: |
    aws ecr get-login-password | docker login ...
    docker build -t livecap-backend ./backend
    docker push ...
    aws ecs update-service --force-new-deployment

- name: Deploy Frontend
  run: |
    cd frontend && npm run build
    aws s3 sync dist/ s3://${{ secrets.FRONTEND_BUCKET }}/
    aws cloudfront create-invalidation ...
```

### AWS CodePipeline
Configure CodePipeline to:
1. Source: GitHub repository
2. Build: CodeBuild for Docker image
3. Deploy: ECS rolling update
4. Post-deploy: S3 sync + CloudFront invalidation

## 🌍 Multi-Environment Setup

Use Terraform workspaces or separate state files:

```bash
# Create dev environment
terraform workspace new dev
terraform apply -var-file=dev.tfvars

# Create prod environment
terraform workspace new prod
terraform apply -var-file=prod.tfvars
```

Or use separate directories:
```
infrastructure/
├── terraform/
│   ├── environments/
│   │   ├── dev/
│   │   │   └── terraform.tfvars
│   │   ├── staging/
│   │   │   └── terraform.tfvars
│   │   └── prod/
│   │       └── terraform.tfvars
```

## 🧹 Cleanup

To destroy all resources:

```bash
cd terraform

# Empty S3 buckets first
aws s3 rm s3://$(terraform output -raw frontend_bucket_name) --recursive
aws s3 rm s3://$(terraform output -raw transcript_bucket_name) --recursive

# Destroy infrastructure
terraform destroy
```

This removes all AWS resources and stops billing.

## 📞 Support

For issues or questions:
1. Check [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) troubleshooting section
2. Review CloudWatch logs
3. Consult AWS service health dashboard
4. Review design and requirements documents

## 🚦 Requirements Coverage

This infrastructure satisfies:
- **Requirement 11**: Public deployment with CloudFront + ALB
- **Requirement 12**: Health check endpoint
- **Requirement 13**: Container deployment with ECS
- **Requirement 14**: S3 bucket isolation
- **Requirement 15**: Cost-aware resource management with lifecycle policies

Additional requirements from design document:
- Task 14.1: Containerize backend application (Dockerfile)
- Task 14.2: ECS task definition and service
- Task 14.3: ALB with TLS termination
- Task 14.4: Frontend S3 + CloudFront
- Task 14.5: ECR repository for container images
- Task 15.1: IAM roles for ECS tasks
- Task 15.2: S3 lifecycle policies
- Task 15.3: Infrastructure as Code templates ✅ **This task**

## 📄 License

This infrastructure code is part of the LiveCap project.
