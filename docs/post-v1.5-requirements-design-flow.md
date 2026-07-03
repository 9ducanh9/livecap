# LiveCap Post-v1.5 Requirements, Design, and Flow

Status: target architecture design for branch `v1.5-production-ready-mvp`.
Terraform implementation is review-gated and must not be described as deployed
until an approved plan has been applied and verified.

This document supplements the original Kiro MVP specification in
`D:\Project\final-project\.kiro\specs\livecap`. It records the post-v1.5
operational hardening work that was added after the original MVP requirements:
security hygiene, Terraform state handling, cost controls, abuse guard,
limited reconnect, and CI checks.

## 1. Updated Requirements

### R1. Secret and Repository Hygiene

The repository must not track local Terraform state, local Terraform variables,
or generated Terraform plan files.

Acceptance criteria:

- `terraform.tfstate`, `terraform.tfstate.backup`, and `terraform.tfvars` are
  ignored and not tracked by Git.
- Local Terraform state or tfvars files inside the repo are moved to an
  operator-controlled backup folder outside the repo before commit.
- Secret scanning must pass before commit. The current supported scan command is
  `gitleaks detect --source . --redact`; Docker may be used as a temporary tool
  runner when `gitleaks` is not installed locally.
- AWS credentials must never be committed, printed, or copied into application
  config files.

### R2. Terraform Remote State Bootstrap

Terraform state for the main infrastructure must move away from local state and
into an S3 backend.

Acceptance criteria:

- Remote-state bootstrap code is isolated under
  `infrastructure/bootstrap/remote-state`.
- The bootstrap stack creates an encrypted, versioned, private S3 bucket for
  Terraform state.
- The main stack uses an S3 backend with native lockfile support.
- State migration is review-gated. Do not run `terraform init -migrate-state`
  until a human has reviewed the migration plan and backend config.
- CI must use `terraform init -backend=false` and must not touch real remote
  state.

### R3. Cost Guardrails

The infrastructure must include baseline cost-control mechanisms aligned with
the AWS Well-Architected Cost Optimization pillar.

Acceptance criteria:

- An AWS Budget can be configured at `$50/month` through Terraform.
- Budget notification email is provided as a variable and is not hardcoded.
- Documentation states that AWS Budget alerts are not real-time and may lag
  behind actual service usage.
- Transcript storage keeps the original S3 lifecycle cleanup behavior.
- ECS service scaling is demo-safe: maximum task count remains `1` while the
  backend session registry is process-local.
- ECS backend desired/min capacity can default to `0` outside active use while
  keeping `backend_max_capacity=1`.
- Scheduled scaling can let the ECS service sit at `0` outside demo hours and
  back at `1` during demo hours while keeping autoscaling max capacity `1`.
- Optional backend idle scale-down can request desired count `0` after the last
  active session ends and the grace period expires.

Out of scope for this increment:

- Removing idle ALB cost.
- Replacing ECS/ALB with a fully pay-per-use WebSocket architecture.

### R4. WebSocket Abuse Guard

The backend must reject excessive concurrent WebSocket sessions before opening
costly Amazon Transcribe or Translate work.

Acceptance criteria:

- Backend config includes `MAX_CONCURRENT_SESSIONS` and `MAX_SESSIONS_PER_IP`.
- The backend resolves client IP from `X-Forwarded-For`, falling back to the
  socket client host.
- If global or per-IP limits are exceeded, the backend sends an error with code
  `TOO_MANY_SESSIONS` and closes the WebSocket.
- Accepted sessions are registered in an in-memory active-session registry.
- Registry entries are removed on every session end path: user stop, browser
  disconnect, timeout, Transcribe error, and internal exception.
- ECS maximum task count stays at `1` while the registry is in memory. Scaling
  beyond one task requires a shared store such as DynamoDB or Redis.

### R5. Limited WebSocket Retry and Heartbeat

The frontend may retry unexpected recording-time disconnects, but it must not
buffer audio indefinitely or pretend to resume the same backend session.

Acceptance criteria:

- Frontend sends heartbeat pings every 30 seconds while the socket is open.
- Backend accepts `{ "type": "ping" }` and responds with `{ "type": "pong" }`.
- If the socket closes unexpectedly during recording, the frontend retries at
  most three times with backoff `1s -> 2s -> 4s`.
- Audio chunks produced while the socket is not open are dropped.
- On successful reconnect, the UI shows a `Reconnected` status.
- Reconnect creates a new backend Session_ID; finalized transcript segments
  already in the UI are preserved.
- If retry fails, capture is stopped and the user is asked to restart.

### R6. Wake-on-Demand Backend Startup

The frontend may optionally wake the ECS backend before opening the WebSocket
when the service has been scaled to zero.

Acceptance criteria:

- Wake support is opt-in through Terraform variable `enable_wake_endpoint`.
- The default remains disabled until the CloudFront/Lambda origin and cost
  impact have been reviewed.
- When enabled, Terraform creates an `AWS_IAM` Lambda Function URL behind the
  same CloudFront distribution at `/api/wake`.
- CloudFront OAC signs the Lambda origin request. Anonymous direct Function URL
  calls are not permitted.
- Lambda sets the selected ECS service desired count to `1`; target Application
  Auto Scaling remains bounded to `0-1`.
- The frontend reads `VITE_WAKE_BACKEND_URL`. If it is empty, startup behavior is
  unchanged.
- If `VITE_WAKE_BACKEND_URL` is set, the frontend calls it before WebSocket connect
  and polls `/api/health` until the backend is healthy or the startup timeout is
  reached.
- Audio capture starts only after the backend wake/health check path completes.

Limitations:

- This does not remove idle ALB, NAT Gateway, or WAF fixed costs.
- The wake path is protected by CloudFront WAF and IAM-signed origin access,
  but it can still start paid ECS capacity when an allowed edge request reaches
  `/api/wake`.

### R7. CI Hygiene

GitHub Actions must run verification only. CI must not deploy or mutate
production infrastructure.

Acceptance criteria:

- Backend CI runs `python -m compileall app` and `pytest`.
- Frontend CI runs `npm ci` and `npm run build`.
- Terraform CI runs formatting and validation checks only, using
  `terraform init -backend=false`.
- CI includes secret scanning.
- No CI workflow runs `terraform apply`, state migration, or production deploy.

## 2. Updated Design

### Backend Runtime Components

The original FastAPI WebSocket flow remains the core runtime. Post-v1.5 adds
one process-local guard component:

- `ActiveSessionRegistry`: tracks active session IDs and per-IP counts in the
  backend process.
- `Settings`: now includes `max_concurrent_sessions` and `max_sessions_per_ip`.
- `ErrorCode`: now includes `TOO_MANY_SESSIONS`.
- `PongMessage`: added as a lightweight heartbeat response.

Important design constraint:

The registry is intentionally in-memory for the current demo-safe architecture.
Because it is not shared between ECS tasks, ECS must stay at max capacity `1`.
If the service later needs multiple backend tasks, this guard must move to a
shared store before increasing ECS max capacity.

### Frontend Runtime Components

The original React/Vite frontend still captures microphone audio and streams
PCM chunks. Post-v1.5 adds limited connection resilience:

- `useWebSocket` owns heartbeat, retry state, and connection status.
- `wakeService` optionally calls `VITE_WAKE_BACKEND_URL` and waits for backend
  `/api/health` before capture starts.
- `wakeService` reads `VITE_WAKE_BACKEND_URL`, `VITE_BACKEND_HEALTH_URL`, and
  `VITE_BACKEND_WAKE_TIMEOUT_SECONDS`.
- `ControlPanel` displays max session duration and remaining time while
  recording.
- `App` preserves finalized transcript segments across reconnects.
- The UI shows `Reconnected` after a successful retry.
- Audio capture does not queue chunks while the socket is closed.

### Infrastructure Components

The legacy rollback architecture remains:

- Frontend: S3 + CloudFront.
- Backend: ECS Fargate behind the existing ALB/default VPC path.
- Container image: ECR.
- Transcript storage: private S3 bucket.
- Logs: CloudWatch.

The target architecture uses **Parallel Stack Migration with Blue/Green-style
Cutover**. The legacy backend path remains available while the target network,
ALB, and ECS service are created and validated in parallel.

- Remote-state bootstrap stack under `infrastructure/bootstrap/remote-state`.
- Main Terraform S3 backend with native lockfile support.
- Dedicated target VPC in `ap-southeast-1` across two Availability Zones.
- Two public subnets for the internet-facing ALB.
- Two private subnets for ECS Fargate tasks with
  `assign_public_ip=false`.
- One NAT Gateway in a public subnet as an explicit cost-sensitive tradeoff.
- Target ECS desired/min capacity can reach `0`, while maximum capacity remains
  `1` because session state is process-local.
- A target ALB and ECS service are validated before CloudFront cutover.
- CloudFront origin selection through `route_backend_to_target`.
- AWS Budget resource, gated by `budget_notification_email`.
- ECS scheduled scaling actions for demo-safe scale-to-zero windows.
- IAM-protected Lambda Function URL exposed only through CloudFront
  `/api/wake`, gated by `enable_wake_endpoint`.
- Optional backend idle scale-down, gated by `ENABLE_IDLE_SCALE_DOWN`.
- CloudFront and ALB WAF Web ACLs in COUNT mode.
- CloudWatch dashboard covering target ECS/ALB, wake Lambda, and WAF metrics.
- ECR backend images use immutable Git SHA tags rather than `latest`.
- Frontend assets remain in the private frontend S3 bucket behind CloudFront.
- Exported transcripts remain in the private transcript S3 bucket.
- Raw audio is not stored in the MVP.
- Transcript objects and CloudWatch logs are retained for 14 days.

Resource scope is intentionally explicit:

- CloudFront and its `CLOUDFRONT` WAF Web ACL are global services. Terraform
  manages the CloudFront WAF through `us-east-1` as required by AWS.
- The VPC, public/private subnets, NAT Gateway, ALB, `REGIONAL` ALB WAF, ECS
  Fargate, ECR, S3 buckets, Lambda, and CloudWatch resources belong to the
  LiveCap deployment in `ap-southeast-1`.

The main application runtime does not pass through Lambda:

```text
User browser
  -> CloudFront WAF (COUNT)
  -> CloudFront
  -> ALB WAF (COUNT)
  -> ALB in public subnets
  -> ECS Fargate task in private subnets
```

Lambda is used only for backend wake-up:

```text
User clicks Start
  -> CloudFront /api/wake
  -> IAM-protected wake Lambda
  -> ECS UpdateService desired_count=1
  -> Frontend polls CloudFront /api/health
  -> Main CloudFront -> ALB -> ECS runtime path begins
```

The target service is self-healing rather than active-active. ECS replaces an
unhealthy task, but because only one task is allowed, replacement causes a
short outage and terminates active WebSocket sessions. Two-task HA requires a
shared session registry before `backend_max_capacity` can increase.

Scale-to-zero removes idle Fargate compute cost, but it does not remove the
fixed or baseline costs of the ALB, NAT Gateway, or enabled WAF Web ACLs and
rules. The single NAT Gateway also remains a single-AZ outbound dependency
accepted for this cost-sensitive MVP.

### Parallel Stack Migration with Blue/Green-style Cutover

1. Keep the legacy ALB/ECS path running as the rollback stack.
2. Create the target VPC, two public subnets, two private subnets, NAT Gateway,
   target ALB, and target ECS service in parallel.
3. Push the backend image to ECR using an immutable Git SHA.
4. Start one target Fargate task and verify that it has no public IP, passes ALB
   health checks, and reaches required AWS services through NAT.
5. Validate wake-up, API, WebSocket, Transcribe, Translate, transcript export,
   CloudWatch metrics, and WAF COUNT observations.
6. Change CloudFront `/api/*` and `/ws/*` routing to the target ALB only after
   the target path passes review.
7. Validate ECS wake `0 -> 1` and idle scale-down `1 -> 0`, with maximum capacity
   fixed at one task.
8. Keep legacy resources during the rollback observation window.
9. Do not destroy the stopped EC2 instance, EBS volume, legacy security group,
   old S3 bucket, legacy ALB/ECS resources, or any other pre-existing resource
   until ownership and removal are explicitly confirmed in a separate review.

### CI and Safety Design

CI is intentionally validation-only:

- It can compile, test, build, scan, format-check, and validate.
- It must not deploy.
- It must not apply Terraform.
- It must not migrate Terraform state.
- It must not depend on local state files or tracked secrets.

## 3. Updated Flow

### Normal Capture Flow

```text
User clicks Start
  -> If VITE_WAKE_BACKEND_URL is configured:
       - frontend POSTs to CloudFront /api/wake
       - Lambda sets ECS desired count to 1
       - frontend polls CloudFront /api/health until backend is ready
  -> Frontend requests microphone permission
  -> Frontend opens CloudFront WebSocket /ws/transcribe
  -> CloudFront routes /ws/* through the ALB to the ECS Fargate task
  -> Backend accepts socket and resolves client IP
  -> Backend checks active-session registry limits
  -> Backend sends session_start with Session_ID
  -> Frontend sends PCM audio chunks only while socket is open
  -> Backend fans audio into Transcribe stream(s)
  -> Backend translates finalized segments
  -> Backend sends captions to frontend
  -> Frontend renders Vietnamese and English columns
```

### Abuse-Rejection Flow

```text
Client opens WebSocket
  -> Backend accepts socket
  -> Backend resolves client IP
  -> Registry check fails global or per-IP limit
  -> Backend sends error code TOO_MANY_SESSIONS
  -> Backend closes socket
  -> No Transcribe or Translate work is started
```

### Heartbeat Flow

```text
Socket open
  -> Frontend sends {"type":"ping"} every 30 seconds
  -> Backend responds {"type":"pong"}
  -> Frontend ignores pong except for connection health visibility/debugging
```

### Limited Retry Flow

```text
Unexpected socket close while recording
  -> Frontend marks connection as reconnecting
  -> Retry after 1 second
  -> Retry after 2 seconds if still closed
  -> Retry after 4 seconds if still closed
  -> If a retry succeeds:
       - backend creates a new Session_ID
       - frontend keeps existing finalized transcript rows
       - UI shows Reconnected
  -> If all retries fail:
       - frontend stops capture
       - UI asks user to restart
```

### Cleanup Flow

```text
Any session end path
  -> user stop OR browser disconnect OR timeout OR Transcribe error OR internal error
  -> Backend pushes end-of-stream sentinel(s) to audio queues
  -> Backend cancels worker tasks and gathers task results
  -> Backend sends session_end when possible
  -> Backend unregisters active session from process-local registry
  -> Backend closes WebSocket
```

### Terraform State Flow

```text
Bootstrap phase
  -> cd infrastructure/bootstrap/remote-state
  -> terraform init
  -> terraform plan
  -> human review
  -> terraform apply only after review
  -> copy output bucket to local backend.hcl

Main infrastructure phase
  -> cd infrastructure/terraform
  -> terraform init -backend-config=backend.hcl
  -> terraform plan
  -> human review
  -> terraform init -migrate-state only after explicit approval
```

### Wake-on-Demand Flow

```text
Outside demo hours
  -> ECS minimum capacity can remain 0

User clicks Start in frontend
  -> Frontend calls CloudFront /api/wake if configured
  -> CloudFront invokes the IAM-protected wake Lambda
  -> Lambda updates ECS desired count to 1
  -> Frontend polls CloudFront /api/health
  -> Once healthy, CloudFront routes WebSocket traffic through ALB to ECS
  -> Frontend starts microphone capture

After the last active session
  -> Idle scale-down can return desired count to 0 while max stays 1
```

### Idle Scale-Down Flow

```text
Last active WebSocket session ends
  -> Backend unregisters the session from ActiveSessionRegistry
  -> If ENABLE_IDLE_SCALE_DOWN=false, no AWS call is made
  -> If enabled and no sessions remain:
       - backend waits IDLE_SCALE_DOWN_GRACE_SECONDS
       - a new session during the grace period cancels the pending scale-down
       - if still idle, backend requests ECS desired count 0
```

### CI Flow

```text
Push or pull request
  -> Secret scan
  -> Backend compile and tests
  -> Frontend npm ci and build
  -> Terraform fmt check
  -> Terraform init -backend=false
  -> Terraform validate
  -> No deploy, no apply, no state migration
```

## 4. Current Verification Baseline

The latest local pre-commit gate passed with:

- `python -m compileall app`
- `python -m pytest` with 204 tests passing
- `npm run build`
- Docker-based `gitleaks detect --source=/repo --redact`
- Docker-based `gitleaks dir /repo --redact`
- Docker-based Terraform `fmt -check -recursive`
- Docker-based Terraform `init -backend=false` and `validate` for both the
  bootstrap and main infrastructure stacks

The submission deployment was refreshed on 2026-07-04 with ECS task definition
revision `livecap-backend-dev:5`, immutable backend image tag
`1ef4250-amd64`, and frontend revision `b58a80c`. Production smoke verification
passed for CloudFront `/` and `/app`, `/api/health`, desktop and 390 px mobile
layout, WebSocket session start, heartbeat, real 16 kHz PCM transcription,
English-to-Vietnamese translation, clean session end, S3 transcript export,
and presigned TXT download.

A synthesized 16 kHz, 16-bit, mono PCM sentence completed the full WSS ->
Transcribe -> Translate -> finalized bilingual caption -> clean session end ->
S3 export -> presigned TXT download path. The ECS service was healthy at one
desired/running task, transcript and backend log retention were both verified
at 14 days, and the public frontend production dependency audit reported zero
known vulnerabilities. GitHub Dependabot alerts and automated security fixes
are enabled; there were zero open Dependabot alerts at verification time.

Local Terraform state files were moved out of the repository to:

```text
D:\secure\livecap-state-backup-20260613-011930
```

## 5. Remaining Architecture Questions

These items are intentionally not fully solved by post-v1.5 hardening:

- Applying and testing the optional wake-on-demand and idle scale-down paths in AWS.
- Removing idle ALB cost when the app is not being demoed. The current wake
  design still keeps ALB as the stable backend entrypoint.
- Migrating the session registry from process memory to DynamoDB or Redis.
- Deciding whether legacy LiveCap resources should be deleted:
  - stopped EC2 instance `Name=LiveCap`
  - `LiveCapEC2Role`
  - legacy S3 bucket `livecaptranscripts`
- Applying the new Terraform budget and scheduled scaling resources to AWS.
- Monitoring the pinned Bookworm base image for patched packages. ECR Basic
  Scanning completed for the single-manifest `1ef4250-amd64` image. Its
  inherited Debian OS baseline still reports 1 critical, 6 high, 6 medium, and
  3 low findings; the critical/high package findings remain a tracked residual
  risk until Debian publishes compatible fixes.
