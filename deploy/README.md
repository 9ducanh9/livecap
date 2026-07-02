# LiveCap Deployment Configuration

> **Legacy reference only.** The JSON templates and manual EC2/ECS steps in
> this directory predate the current private-Fargate, immutable-SHA and
> blue/green Terraform design. Do not use them for the submission deployment.
> Use `../infrastructure/terraform/README.md` and
> `../infrastructure/terraform/IMPORT_PLAN.md` instead.

This directory contains deployment configuration files for the LiveCap application, supporting both traditional EC2 deployment and modern containerized ECS Fargate deployment.

## Directory Structure

```
deploy/
├── README.md                          # This file
├── ECS_DEPLOYMENT.md                  # Comprehensive ECS Fargate deployment guide
├── ecs-task-definition.json           # ECS task definition for backend container
├── alb-target-group.json              # ALB target group with health check configuration
├── iam-policies/                      # IAM policy templates
│   ├── livecap-task-policy.json       # Task role permissions (Transcribe, Translate, S3)
│   ├── livecap-task-trust-policy.json # Task role trust relationship
│   └── ecs-task-execution-trust-policy.json  # Execution role trust relationship
├── s3/                                # S3 configuration
│   └── transcript-lifecycle-policy.json  # Auto-delete transcripts after 30 days
├── autoscaling/                       # Auto-scaling configuration
│   └── scaling-policy.json            # CPU-based target tracking policy
├── livecap.service                    # systemd service unit (EC2 deployment)
└── nginx.conf                         # Nginx reverse proxy config (EC2 deployment)
```

## Deployment Options

### Option 1: ECS Fargate (Recommended for Production)

**Architecture:** Docker containers on ECS Fargate behind Application Load Balancer

**Advantages:**
- Automatic scaling and self-healing
- No server management
- Pay-per-use pricing
- AWS Well-Architected alignment

**Start here:** Read `ECS_DEPLOYMENT.md` for complete deployment instructions.


### Option 2: EC2 with systemd (Legacy/Development)

**Architecture:** FastAPI on EC2 behind Nginx reverse proxy

**Advantages:**
- Simpler initial setup for development
- Direct SSH access for debugging
- Lower cost for single-instance deployments

**Configuration files:**
- `livecap.service`: systemd service unit for managing the FastAPI process
- `nginx.conf`: Nginx reverse proxy configuration with TLS termination

**Note:** This deployment model does not provide automatic scaling or self-healing. It is suitable for development and low-traffic scenarios.

## Quick Start

### For ECS Deployment

1. **Read the comprehensive guide:**
   ```bash
   cat ECS_DEPLOYMENT.md
   ```

2. **Update placeholders** in configuration files:
   - `ACCOUNT_ID`: Your AWS account ID
   - `REGION`: Your AWS region
   - `CLOUDFRONT_DOMAIN`: Your CloudFront distribution domain
   - `TRANSCRIPT_BUCKET_NAME`: Your S3 bucket name

3. **Build and push Docker image:**
   ```bash
   # See ECS_DEPLOYMENT.md section "Prerequisites > Container Image"
   cd ../backend
   docker build -t livecap-backend .
   # ... push to ECR
   ```

4. **Deploy infrastructure** following the step-by-step instructions in `ECS_DEPLOYMENT.md`


### For EC2 Deployment

1. **Launch EC2 instance** with Amazon Linux 2 or Ubuntu
2. **Install dependencies:**
   ```bash
   # Python, Nginx, certbot
   sudo yum install python3 nginx certbot python3-certbot-nginx -y
   ```
3. **Clone repository** and set up environment:
   ```bash
   cd /home/ec2-user
   git clone https://github.com/your-org/livecap.git
   cd livecap/backend
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   cp .env.example .env
   # Edit .env with your configuration
   ```
4. **Configure systemd service:**
   ```bash
   sudo cp deploy/livecap.service /etc/systemd/system/
   # Edit the file to match your paths
   sudo systemctl daemon-reload
   sudo systemctl enable livecap
   sudo systemctl start livecap
   ```
5. **Configure Nginx:**
   ```bash
   sudo cp deploy/nginx.conf /etc/nginx/conf.d/livecap.conf
   # Replace YOUR_DOMAIN with your actual domain
   sudo certbot --nginx -d your-domain.com
   sudo systemctl reload nginx
   ```

## Configuration Files Reference

### ecs-task-definition.json

Defines ECS task configuration including:
- Container image URI (ECR)
- CPU/memory allocation (0.5 vCPU, 1 GB RAM)
- Port mappings (container port 8000)
- Environment variables (AWS region, S3 bucket, CORS origin, etc.)
- IAM roles (task role, execution role)
- Health check configuration
- CloudWatch Logs integration

**Before use:** Replace placeholders for account ID, region, and CloudFront domain.


### alb-target-group.json

Defines ALB target group with health check configuration:
- Protocol: HTTP (internal traffic)
- Port: 8000 (matches container port)
- Target type: IP (required for awsvpc network mode)
- Health check path: `/api/health`
- Health check intervals: 30s interval, 5s timeout
- Thresholds: 2 healthy, 3 unhealthy
- Deregistration delay: 30s (allows graceful shutdown)

**Before use:** Replace `VpcId` with your VPC ID.

### IAM Policies

**`iam-policies/livecap-task-policy.json`**

Grants the backend application permissions to:
- **S3:** Read/write access to Transcript_Bucket ONLY (not Frontend_Bucket)
- **Transcribe:** Start streaming transcription sessions
- **Translate:** Translate text between Vietnamese and English
- **CloudWatch Logs:** Write application logs

**Security Note:** This policy follows the principle of least privilege by granting access ONLY to the Transcript_Bucket, not the Frontend_Bucket.

**Before use:** Replace `TRANSCRIPT_BUCKET_NAME` with your actual S3 bucket name.

**`iam-policies/livecap-task-trust-policy.json`**

Trust policy allowing ECS tasks to assume the task role.

**`iam-policies/ecs-task-execution-trust-policy.json`**

Trust policy for the ECS task execution role (standard AWS configuration).


### S3 Lifecycle Policy

**`s3/transcript-lifecycle-policy.json`**

Configures automatic deletion of transcript files after 30 days to control storage costs.

Apply to Transcript_Bucket:
```bash
aws s3api put-bucket-lifecycle-configuration \
  --bucket livecap-transcripts \
  --lifecycle-configuration file://s3/transcript-lifecycle-policy.json
```

**Customization:** Adjust the `Days` value to change the retention period.

### Auto-Scaling Policy

**`autoscaling/scaling-policy.json`**

Target tracking scaling policy for ECS service auto-scaling:
- Target metric: CPU utilization
- Target value: 70%
- Scale-out cooldown: 60s (fast response to traffic spikes)
- Scale-in cooldown: 300s (conservative to avoid thrashing)

**Alternative metrics:**
- `ECSServiceAverageMemoryUtilization`: Scale based on memory
- ALB Request Count: Scale based on traffic volume (recommended for WebSocket workloads)

## Environment Variables

The following environment variables must be configured in the ECS task definition or `.env` file:

| Variable | Description | Example |
|----------|-------------|---------|
| `AWS_REGION` | AWS region for all services | `us-east-1` |
| `S3_BUCKET` | Transcript_Bucket name | `livecap-transcripts` |
| `DOWNLOAD_LINK_EXPIRATION` | Presigned URL expiration (seconds) | `86400` (24 hours) |
| `SESSION_TIMEOUT` | Max session duration (seconds) | `1800` (30 minutes) |
| `MAX_SPEAKERS` | Max speakers for diarization | `5` |
| `BILINGUAL_DUAL_STREAM` | Enable dual vi-VN/en-US streams | `true` |
| `ALLOWED_ORIGIN` | Frontend CloudFront URL | `https://d1234567890.cloudfront.net` |
| `CLOUDWATCH_LOG_GROUP` | CloudWatch log group name | `livecap` |


## Requirements Satisfied

This deployment configuration satisfies the following requirements from the specification:

- **Requirement 13.3:** Backend packaged as Container_Image and deployed as ECS_Tasks
- **Requirement 13.4:** ALB routes HTTP/HTTPS and WebSocket traffic to ECS_Tasks with TLS termination
- **Requirement 13.5:** ECS Fargate automatically restarts unhealthy tasks based on ALB health checks
- **Requirement 13.6:** Backend reads configuration from environment variables injected by ECS task definition
- **Requirement 12.3:** ALB performs health checks against `/api/health` endpoint to determine task health
- **Requirement 14.5:** ECS task IAM role grants access ONLY to Transcript_Bucket, not Frontend_Bucket

## Additional Resources

- **`ECS_DEPLOYMENT.md`**: Complete deployment guide with step-by-step instructions
- **`../backend/.env.example`**: Environment variable reference with descriptions
- **`../backend/Dockerfile`**: Container image build instructions (to be created)
- **AWS Documentation:**
  - [ECS on Fargate](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/AWS_Fargate.html)
  - [ALB WebSocket Support](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/load-balancer-listeners.html#websocket-listener)
  - [ECS Task Definitions](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task_definitions.html)

## Troubleshooting

For common issues and solutions, see the **Monitoring and Troubleshooting** section in `ECS_DEPLOYMENT.md`.

**Quick diagnostics:**
```bash
# Check service status
aws ecs describe-services --cluster livecap-cluster --services livecap-backend-service

# View task logs
aws logs tail /ecs/livecap-backend --follow

# Check target health
aws elbv2 describe-target-health --target-group-arn YOUR_TARGET_GROUP_ARN
```

## Support

For issues related to deployment, refer to:
1. `ECS_DEPLOYMENT.md` for detailed troubleshooting steps
2. AWS documentation linked above
3. Project repository issues: https://github.com/your-org/livecap/issues

