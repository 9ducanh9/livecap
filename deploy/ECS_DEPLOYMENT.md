# ECS Deployment Configuration Guide

> **Legacy manual guide.** This document contains the old public-IP and
> `latest`-tag workflow. It is retained for historical context only. The active
> deployment process is the review-gated Terraform workflow documented in
> `../infrastructure/terraform/README.md` and
> `../infrastructure/terraform/IMPORT_PLAN.md`.

This document describes the Amazon ECS Fargate deployment configuration for the LiveCap backend, including task definitions, service configuration, and IAM roles.

## Overview

The LiveCap backend runs as containerized tasks on **Amazon ECS Fargate** behind an **Application Load Balancer (ALB)**. The ALB terminates TLS and routes both HTTPS REST requests and secure WebSocket (WSS) connections to healthy ECS tasks.

**Architecture:**
```
Internet → ALB (TLS termination) → Target Group → ECS Service → ECS Tasks (Docker containers)
                                                                          ↓
                                                                    AWS Services
                                                                    (Transcribe, Translate, S3, CloudWatch)
```

## Files in This Directory

- **`ecs-task-definition.json`**: ECS task definition defining container configuration, CPU/memory allocation, IAM roles, environment variables, and CloudWatch logging
- **`alb-target-group.json`**: ALB target group configuration with health check settings
- **`ECS_DEPLOYMENT.md`**: This file - comprehensive deployment documentation

## Prerequisites

### 1. Container Image

Build and push the backend Docker image to Amazon ECR:

```bash
# Create ECR repository (one-time setup)
aws ecr create-repository --repository-name livecap-backend --region us-east-1

# Authenticate Docker to ECR
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com

# Build the Docker image
cd backend
docker build -t livecap-backend:latest .

# Tag the image for ECR
docker tag livecap-backend:latest ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/livecap-backend:latest

# Push to ECR
docker push ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/livecap-backend:latest
```


### 2. IAM Roles

Two IAM roles are required:

#### ECS Task Execution Role

The **task execution role** allows ECS to pull container images from ECR and write logs to CloudWatch.

**Role Name:** `ecsTaskExecutionRole` (AWS-managed)

**Managed Policy:** `arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy`

**Trust Policy:**
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "ecs-tasks.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
```

Create the role (if not already exists):
```bash
aws iam create-role \
  --role-name ecsTaskExecutionRole \
  --assume-role-policy-document file://ecs-task-execution-trust-policy.json

aws iam attach-role-policy \
  --role-name ecsTaskExecutionRole \
  --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy
```


#### ECS Task Role

The **task role** grants the backend application permissions to interact with AWS services (Transcribe, Translate, S3, CloudWatch).

**Role Name:** `livecap-task-role`

**Permissions Required:**
- **S3:** Read/write access to `Transcript_Bucket` ONLY (not `Frontend_Bucket`)
- **Transcribe:** Start streaming transcription sessions
- **Translate:** Translate text
- **CloudWatch Logs:** Write application logs

**IAM Policy Document** (`livecap-task-policy.json`):
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "TranscriptBucketAccess",
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:GetObject",
        "s3:DeleteObject"
      ],
      "Resource": "arn:aws:s3:::TRANSCRIPT_BUCKET_NAME/*"
    },
    {
      "Sid": "TranscribeAccess",
      "Effect": "Allow",
      "Action": [
        "transcribe:StartStreamTranscription"
      ],
      "Resource": "*"
    },
    {
      "Sid": "TranslateAccess",
      "Effect": "Allow",
      "Action": [
        "translate:TranslateText"
      ],
      "Resource": "*"
    },
    {
      "Sid": "CloudWatchLogsAccess",
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:*:*:log-group:/ecs/livecap-backend:*"
    }
  ]
}
```


**Trust Policy** (`livecap-task-trust-policy.json`):
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "ecs-tasks.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
```

Create the task role:
```bash
# Create the role
aws iam create-role \
  --role-name livecap-task-role \
  --assume-role-policy-document file://livecap-task-trust-policy.json

# Attach the custom policy
aws iam put-role-policy \
  --role-name livecap-task-role \
  --policy-name livecap-task-permissions \
  --policy-document file://livecap-task-policy.json
```

**IMPORTANT:** Replace `TRANSCRIPT_BUCKET_NAME` in the policy with your actual S3 bucket name before applying.


### 3. VPC and Networking

The ECS tasks run in **awsvpc** network mode, requiring:

- **VPC:** An existing VPC with private or public subnets
- **Subnets:** At least 2 subnets in different Availability Zones for high availability
- **Security Group:** A security group allowing inbound traffic on port 8000 from the ALB security group

**Security Group Configuration:**

```bash
# Create security group for ECS tasks
aws ec2 create-security-group \
  --group-name livecap-ecs-sg \
  --description "Security group for LiveCap ECS tasks" \
  --vpc-id vpc-XXXXXXXX

# Allow inbound traffic from ALB security group
aws ec2 authorize-security-group-ingress \
  --group-id sg-YYYYYYYY \
  --protocol tcp \
  --port 8000 \
  --source-group sg-ALB_SECURITY_GROUP_ID

# Allow outbound traffic to AWS services (Transcribe, Translate, S3, CloudWatch)
aws ec2 authorize-security-group-egress \
  --group-id sg-YYYYYYYY \
  --protocol tcp \
  --port 443 \
  --cidr 0.0.0.0/0
```


### 4. S3 Buckets

Two isolated S3 buckets are required:

1. **Frontend_Bucket:** Hosts static frontend assets (served via CloudFront)
2. **Transcript_Bucket:** Stores exported transcript files (private, backend-only access)

Create the Transcript_Bucket:
```bash
aws s3 mb s3://livecap-transcripts --region us-east-1

# Configure lifecycle policy for automatic cleanup after 30 days
aws s3api put-bucket-lifecycle-configuration \
  --bucket livecap-transcripts \
  --lifecycle-configuration file://transcript-lifecycle-policy.json
```

**Lifecycle Policy** (`transcript-lifecycle-policy.json`):
```json
{
  "Rules": [
    {
      "Id": "DeleteOldTranscripts",
      "Status": "Enabled",
      "Prefix": "transcripts/",
      "Expiration": {
        "Days": 30
      }
    }
  ]
}
```


## ECS Task Definition

The `ecs-task-definition.json` file defines the container configuration for the LiveCap backend.

### Key Configuration

**Resource Allocation:**
- **CPU:** 512 (0.5 vCPU) - estimated based on transcription workload
- **Memory:** 1024 MB (1 GB) - sufficient for FastAPI + boto3 + streaming buffers
- **Network Mode:** `awsvpc` (required for Fargate)

**Container Configuration:**
- **Image:** Replace `ACCOUNT_ID` and `REGION` with your AWS account ID and region
- **Port Mapping:** Container listens on port 8000
- **Health Check:** Curl-based check against `/api/health` endpoint
  - Interval: 30s
  - Timeout: 5s
  - Retries: 3
  - Start period: 60s (allows container initialization time)
- **Stop Timeout:** 30s (allows graceful WebSocket session closure)

**Environment Variables:**
All application configuration is injected via environment variables:
- `AWS_REGION`: AWS region for all services
- `S3_BUCKET`: Name of the Transcript_Bucket
- `ALLOWED_ORIGIN`: Frontend CloudFront URL (replace `CLOUDFRONT_DOMAIN`)
- See `.env.example` for full variable descriptions

**Logging:**
- **Driver:** `awslogs` (CloudWatch Logs)
- **Log Group:** `/ecs/livecap-backend` (auto-created)
- **Stream Prefix:** `ecs`
- **Region:** us-east-1


### Registering the Task Definition

Before updating the task definition, replace placeholders:
- `ACCOUNT_ID`: Your AWS account ID
- `REGION`: Your AWS region (e.g., `us-east-1`)
- `CLOUDFRONT_DOMAIN`: Your CloudFront distribution domain

```bash
# Register the task definition
aws ecs register-task-definition \
  --cli-input-json file://ecs-task-definition.json

# Verify registration
aws ecs describe-task-definition \
  --task-definition livecap-backend
```


## Application Load Balancer Configuration

### Target Group

The `alb-target-group.json` file defines the ALB target group with health check configuration.

**Configuration:**
- **Protocol:** HTTP (internal traffic between ALB and ECS tasks)
- **Port:** 8000 (matches container port)
- **Target Type:** `ip` (required for awsvpc network mode)
- **Health Check Path:** `/api/health`
- **Health Check Settings:**
  - Interval: 30s
  - Timeout: 5s
  - Healthy threshold: 2 consecutive successes
  - Unhealthy threshold: 3 consecutive failures
  - Matcher: HTTP 200
- **Deregistration Delay:** 30s (allows in-flight requests to complete)
- **Load Balancing Algorithm:** `least_outstanding_requests` (optimal for WebSocket connections)

Create the target group:
```bash
# Replace VpcId with your VPC ID
aws elbv2 create-target-group \
  --cli-input-json file://alb-target-group.json
```


### ALB Listeners

The ALB requires two listeners to handle HTTP and HTTPS traffic:

**HTTP Listener (Port 80) - Redirect to HTTPS:**
```bash
aws elbv2 create-listener \
  --load-balancer-arn arn:aws:elasticloadbalancing:REGION:ACCOUNT_ID:loadbalancer/app/livecap-alb/XXXXXXXX \
  --protocol HTTP \
  --port 80 \
  --default-actions Type=redirect,RedirectConfig='{Protocol=HTTPS,Port=443,StatusCode=HTTP_301}'
```

**HTTPS Listener (Port 443) - Forward to Target Group:**
```bash
aws elbv2 create-listener \
  --load-balancer-arn arn:aws:elasticloadbalancing:REGION:ACCOUNT_ID:loadbalancer/app/livecap-alb/XXXXXXXX \
  --protocol HTTPS \
  --port 443 \
  --certificates CertificateArn=arn:aws:acm:REGION:ACCOUNT_ID:certificate/CERT_ID \
  --default-actions Type=forward,TargetGroupArn=arn:aws:elasticloadbalancing:REGION:ACCOUNT_ID:targetgroup/livecap-backend-tg/YYYYYYYY
```

**TLS Certificate:**
- Obtain a certificate from **AWS Certificate Manager (ACM)** for your domain
- The certificate must cover the domain used for backend API access
- ALB automatically handles TLS termination (TLS 1.2+)


### WebSocket Support

The ALB supports WebSocket connections (WSS) without additional configuration. The HTTP Upgrade mechanism is automatically handled by the ALB when:
1. Client sends `Upgrade: websocket` header
2. ALB forwards the upgrade request to the backend
3. Backend accepts and upgrades the connection
4. ALB maintains the long-lived connection

**No special listener rules are required** - the default HTTPS listener handles both REST and WebSocket traffic.


## ECS Service Configuration

The ECS service defines how tasks are deployed and managed.

### Service Parameters

**Basic Configuration:**
- **Service Name:** `livecap-backend-service`
- **Launch Type:** `FARGATE`
- **Desired Count:** 1 (MVP - can be increased for horizontal scaling)
- **Platform Version:** `LATEST`

**Network Configuration:**
- **Subnets:** At least 2 subnets in different AZs for high availability
- **Security Groups:** The ECS task security group created earlier
- **Assign Public IP:** `ENABLED` if using public subnets, `DISABLED` if using private subnets with NAT Gateway

**Load Balancer Integration:**
- **Target Group ARN:** ARN of the target group created from `alb-target-group.json`
- **Container Name:** `livecap-backend`
- **Container Port:** 8000

### Creating the ECS Service

```bash
aws ecs create-service \
  --cluster livecap-cluster \
  --service-name livecap-backend-service \
  --task-definition livecap-backend \
  --desired-count 1 \
  --launch-type FARGATE \
  --platform-version LATEST \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-XXXXXXXX,subnet-YYYYYYYY],securityGroups=[sg-ZZZZZZZZ],assignPublicIp=ENABLED}" \
  --load-balancers targetGroupArn=arn:aws:elasticloadbalancing:REGION:ACCOUNT_ID:targetgroup/livecap-backend-tg/YYYYYYYY,containerName=livecap-backend,containerPort=8000 \
  --health-check-grace-period-seconds 60
```


### Service Auto-Scaling (Optional - Future Enhancement)

ECS Service Auto Scaling allows automatic adjustment of task count based on metrics.

**Target Tracking Scaling Policy - CPU Utilization:**
```bash
# Register scalable target
aws application-autoscaling register-scalable-target \
  --service-namespace ecs \
  --resource-id service/livecap-cluster/livecap-backend-service \
  --scalable-dimension ecs:service:DesiredCount \
  --min-capacity 1 \
  --max-capacity 5

# Create scaling policy
aws application-autoscaling put-scaling-policy \
  --service-namespace ecs \
  --resource-id service/livecap-cluster/livecap-backend-service \
  --scalable-dimension ecs:service:DesiredCount \
  --policy-name livecap-cpu-scaling \
  --policy-type TargetTrackingScaling \
  --target-tracking-scaling-policy-configuration file://scaling-policy.json
```

**Scaling Policy Configuration** (`scaling-policy.json`):
```json
{
  "TargetValue": 70.0,
  "PredefinedMetricSpecification": {
    "PredefinedMetricType": "ECSServiceAverageCPUUtilization"
  },
  "ScaleInCooldown": 300,
  "ScaleOutCooldown": 60
}
```

**Alternative Metrics:**
- `ECSServiceAverageMemoryUtilization`: Scale based on memory usage
- **ALB Request Count:** Scale based on traffic volume (recommended for WebSocket workloads)


## Deployment Workflow

### Initial Deployment

1. **Build and push Docker image** to ECR (see Prerequisites)
2. **Create IAM roles** (task execution role and task role)
3. **Create S3 buckets** (Frontend_Bucket and Transcript_Bucket)
4. **Create ECS cluster:**
   ```bash
   aws ecs create-cluster --cluster-name livecap-cluster
   ```
5. **Create ALB and target group** (see ALB Configuration section)
6. **Update task definition placeholders** (account ID, region, CloudFront domain)
7. **Register task definition:**
   ```bash
   aws ecs register-task-definition --cli-input-json file://ecs-task-definition.json
   ```
8. **Create ECS service** (see Service Configuration section)
9. **Verify deployment:**
   ```bash
   # Check service status
   aws ecs describe-services --cluster livecap-cluster --services livecap-backend-service
   
   # Check task status
   aws ecs list-tasks --cluster livecap-cluster --service-name livecap-backend-service
   
   # View task logs
   aws logs tail /ecs/livecap-backend --follow
   ```


### Updating the Application

To deploy a new version of the backend:

1. **Build and push new Docker image:**
   ```bash
   docker build -t livecap-backend:v2 backend/
   docker tag livecap-backend:v2 ACCOUNT_ID.dkr.ecr.REGION.amazonaws.com/livecap-backend:v2
   docker push ACCOUNT_ID.dkr.ecr.REGION.amazonaws.com/livecap-backend:v2
   ```

2. **Update task definition** with new image tag:
   ```bash
   # Edit ecs-task-definition.json to use :v2 tag
   aws ecs register-task-definition --cli-input-json file://ecs-task-definition.json
   ```

3. **Update ECS service** to use new task definition:
   ```bash
   aws ecs update-service \
     --cluster livecap-cluster \
     --service livecap-backend-service \
     --task-definition livecap-backend:2
   ```

4. **Monitor deployment:**
   ```bash
   aws ecs describe-services \
     --cluster livecap-cluster \
     --services livecap-backend-service \
     --query 'services[0].deployments'
   ```

**Rollback:**
If issues occur, rollback to the previous task definition revision:
```bash
aws ecs update-service \
  --cluster livecap-cluster \
  --service livecap-backend-service \
  --task-definition livecap-backend:1
```


## Monitoring and Troubleshooting

### CloudWatch Logs

View real-time logs from ECS tasks:
```bash
# Tail logs for all tasks
aws logs tail /ecs/livecap-backend --follow

# Filter logs by session ID
aws logs filter-log-events \
  --log-group-name /ecs/livecap-backend \
  --filter-pattern "session_id:abc-123"

# View logs for specific task
aws logs tail /ecs/livecap-backend --follow --log-stream-name-prefix ecs/livecap-backend/TASK_ID
```

### Health Check Status

Check ALB target health:
```bash
aws elbv2 describe-target-health \
  --target-group-arn arn:aws:elasticloadbalancing:REGION:ACCOUNT_ID:targetgroup/livecap-backend-tg/YYYYYYYY
```

**Healthy Response:**
```json
{
  "TargetHealthDescriptions": [
    {
      "Target": {
        "Id": "10.0.1.100",
        "Port": 8000
      },
      "HealthCheckPort": "8000",
      "TargetHealth": {
        "State": "healthy"
      }
    }
  ]
}
```


### Common Issues

**Issue: Tasks fail to start**
- Check task logs: `aws logs tail /ecs/livecap-backend --follow`
- Verify IAM roles have correct permissions
- Ensure Docker image exists in ECR
- Check security group allows outbound HTTPS (443) to AWS services

**Issue: Health checks fail**
- Verify `/api/health` endpoint is accessible: `curl http://TASK_IP:8000/api/health`
- Check health check configuration matches container port (8000)
- Increase `startPeriod` if container initialization takes longer than 60s
- Review application logs for startup errors

**Issue: WebSocket connections fail**
- Verify ALB listener forwards to correct target group
- Check security group allows traffic from ALB to ECS tasks on port 8000
- Ensure `ALLOWED_ORIGIN` environment variable matches frontend CloudFront URL
- Test WebSocket upgrade: `wscat -c wss://YOUR_DOMAIN/ws/transcribe`

**Issue: Tasks crash or OOM (Out of Memory)**
- Monitor memory usage: CloudWatch metrics `MemoryUtilization`
- Increase memory allocation in task definition (e.g., 2048 MB)
- Check for memory leaks in application code


## Cost Estimation

**Monthly Cost Breakdown (1 task running 24/7):**

| Service | Configuration | Monthly Cost |
|---------|--------------|--------------|
| ECS Fargate | 0.5 vCPU × 1 GB × 730 hours | ~$21 |
| ALB | 1 ALB + data processing | ~$23 |
| CloudWatch Logs | 5 GB ingestion + storage | ~$3 |
| ECR | 1 GB storage | $0.10 |
| **Total Infrastructure** | | **~$47/month** |
| | | |
| Transcribe Streaming | $0.024/minute × 2 streams | Variable |
| Translate | $15 per million characters | Variable |
| S3 (transcripts) | Storage + requests | ~$1/month |

**Usage-Based Costs (examples):**
- 10 hours/month usage: ~$47 + $288 (Transcribe) + $30 (Translate) = **$365/month**
- 100 hours/month usage: ~$47 + $2,880 (Transcribe) + $300 (Translate) = **$3,227/month**

**Cost Optimization:**
- Use AWS Free Tier for initial testing (1 million S3 requests, 5GB CloudWatch Logs)
- Implement session timeout to prevent abandoned long-running transcriptions
- Scale down to 0 tasks during off-hours (requires manual service update)
- Consider AWS Savings Plans for predictable workloads


## Security Best Practices

### Network Security

1. **Use private subnets with NAT Gateway** for ECS tasks (recommended for production)
2. **Restrict security group rules:**
   - ECS task security group: Allow inbound only from ALB security group on port 8000
   - ALB security group: Allow inbound 443 from 0.0.0.0/0, allow outbound to ECS task security group
3. **Enable VPC Flow Logs** for network traffic monitoring

### IAM Security

1. **Principle of least privilege:** Task role grants access ONLY to Transcript_Bucket, not Frontend_Bucket
2. **Use IAM roles, not access keys:** No AWS credentials in container images or environment variables
3. **Rotate secrets regularly** if using Secrets Manager for sensitive configuration
4. **Enable CloudTrail** to audit API calls

### Application Security

1. **TLS 1.2+ only:** ALB enforces modern TLS versions
2. **CORS enforcement:** Backend accepts requests only from configured frontend origin
3. **Health check security:** Use internal health check (no authentication required for `/api/health`)
4. **Session timeout:** Configure `SESSION_TIMEOUT` to limit maximum transcription duration

### Container Security

1. **Use minimal base images:** Python slim or Alpine-based images
2. **Scan images for vulnerabilities:** Enable ECR image scanning
3. **Run as non-root user** in Dockerfile (add `USER` directive)
4. **Keep dependencies updated:** Regularly update `requirements.txt`


## High Availability and Scaling

### Current MVP Configuration

- **Desired Count:** 1 task
- **Availability Zones:** Tasks deployed across 2 AZs (via subnet configuration)
- **Automatic Recovery:** ECS restarts failed tasks automatically
- **Health Checks:** ALB routes traffic only to healthy tasks

### Horizontal Scaling Strategy

To support higher traffic volumes:

1. **Increase desired count:**
   ```bash
   aws ecs update-service \
     --cluster livecap-cluster \
     --service livecap-backend-service \
     --desired-count 3
   ```

2. **Enable auto-scaling** (see Service Auto-Scaling section)

3. **WebSocket Considerations:**
   - Each WebSocket connection is pinned to a specific task for the session duration
   - ALB uses `least_outstanding_requests` algorithm to distribute new connections
   - No session state is shared between tasks (stateless design)
   - Scaling down may interrupt active sessions (plan maintenance windows)

### Multi-Region Deployment (Future)

For global availability:
1. Deploy ECS services in multiple AWS regions
2. Use Route 53 for DNS-based failover and latency routing
3. Replicate S3 buckets across regions with Cross-Region Replication
4. Consider Aurora Global Database for future database requirements


## References

### AWS Documentation

- [ECS on Fargate](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/AWS_Fargate.html)
- [ALB WebSocket Support](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/load-balancer-listeners.html#websocket-listener)
- [ECS Task Definitions](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task_definitions.html)
- [ECS Service Auto Scaling](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/service-auto-scaling.html)
- [Amazon Transcribe Streaming](https://docs.aws.amazon.com/transcribe/latest/dg/streaming.html)

### Related Files

- `ecs-task-definition.json`: Task definition with container configuration
- `alb-target-group.json`: ALB target group with health check settings
- `../backend/.env.example`: Environment variable reference
- `../backend/Dockerfile`: Container image build instructions (to be created in Task 15.1)

### Architecture Alignment

This deployment configuration satisfies requirements:
- **Requirement 13.3:** Backend packaged as Container_Image and run as ECS_Tasks
- **Requirement 13.4:** ALB routes HTTP/HTTPS and WebSocket traffic to ECS_Tasks
- **Requirement 13.5:** ECS automatically restarts unhealthy tasks based on ALB health checks
- **Requirement 12.3:** ALB health checks use `/api/health` endpoint to verify task health

