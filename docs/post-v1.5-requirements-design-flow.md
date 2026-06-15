# LiveCap Post-v1.5 Requirements, Design, and Flow

Status: current as of branch `v1.5-production-ready-mvp`, after commit `817e037`
plus uncommitted wake-on-demand cost-optimization work.

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
- The default remains disabled to avoid exposing a public URL that can start
  paid ECS capacity before review.
- When enabled, Terraform creates a Lambda Function URL that sets the ECS
  service desired count to `1` and keeps the Application Auto Scaling target at
  min/max `1`.
- The frontend reads `VITE_WAKE_BACKEND_URL`. If it is empty, startup behavior is
  unchanged.
- If `VITE_WAKE_BACKEND_URL` is set, the frontend calls it before WebSocket connect
  and polls `/api/health` until the backend is healthy or the startup timeout is
  reached.
- Audio capture starts only after the backend wake/health check path completes.

Limitations:

- This does not remove idle ALB cost. The ALB still exists so the frontend has a
  stable backend health and WebSocket target.
- The wake endpoint is public when enabled (`authorization_type = NONE`). It can
  only wake ECS to one task, but it can still trigger paid capacity. Add
  authentication, WAF, and rate limiting before real production use.

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

The deployed architecture remains:

- Frontend: S3 + CloudFront.
- Backend: ECS Fargate behind ALB.
- Container image: ECR.
- Transcript storage: private S3 bucket.
- Logs: CloudWatch.

Post-v1.5 infrastructure additions:

- Remote-state bootstrap stack under `infrastructure/bootstrap/remote-state`.
- Main Terraform S3 backend with native lockfile support.
- AWS Budget resource, gated by `budget_notification_email`.
- ECS scheduled scaling actions for demo-safe scale-to-zero windows.
- ECS max capacity default set to `1` while session limits are in-memory.
- Optional Lambda Function URL wake endpoint, gated by `enable_wake_endpoint`.
- Optional backend idle scale-down, gated by `ENABLE_IDLE_SCALE_DOWN`.

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
       - frontend POSTs to wake endpoint
       - Lambda sets ECS desired count to 1
       - frontend polls /api/health until backend is ready
  -> Frontend requests microphone permission
  -> Frontend opens WebSocket /ws/transcribe
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
  -> ECS scheduled scaling can set service capacity to 0

User clicks Start in frontend
  -> Frontend calls VITE_WAKE_BACKEND_URL if configured
  -> Lambda updates ECS desired count to 1
  -> Frontend polls backend /api/health
  -> Once healthy, frontend opens WebSocket and starts microphone capture

Later off-hours schedule
  -> ECS scheduled scaling can return min to 0 while max stays 1
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
- `python -m pytest` with 196 tests passing
- `npm run build`
- Docker-based `gitleaks detect --source=/repo --redact`
- Docker-based `gitleaks dir /repo --redact`
- Docker-based Terraform `fmt -check -recursive`
- Docker-based Terraform `init -backend=false` and `validate` for both the
  bootstrap and main infrastructure stacks

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
