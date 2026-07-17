# Multi-task runbook (Phase 3 slice 2)

Raising the backend above one task, validating it under load, and rolling back.
Do NOT skip the DynamoDB step: with the in-memory registry each task counts
sessions independently, so the global limit would be wrong.

## Preconditions

- Phase 3 slice 1 is deployed: `dynamo_session_registry` in the image and
  `dynamodb.tf` applied.
- `checks.tf` guards this: `terraform plan` warns if `backend_max_capacity > 1`
  while `enable_dynamodb_session_store = false`.

## 1. Enable the shared session store

In `terraform.tfvars`:

```hcl
enable_dynamodb_session_store = true
backend_max_capacity          = 3   # target max tasks
# backend_min_capacity stays 0 for scale-to-zero
```

The task also needs `SESSION_STORE_BACKEND=dynamodb`. `ecs.tf` already sets it
from `enable_dynamodb_session_store`, so no manual env edit is required once that
variable is true.

## 2. Build, push, apply

```powershell
# Build & push a backend image that contains the slice-1 code (immutable tag).
# Then:
terraform -chdir=infrastructure/terraform plan    # review: DynamoDB table,
                                                  # IAM policy, autoscaling max
terraform -chdir=infrastructure/terraform apply
```

Confirm the new task definition revision rolls out and the DynamoDB table
`livecap-sessions-<env>` exists.

## 3. Load test

Wake the backend first (open the app once, or hit the wake endpoint), then:

```powershell
pip install websockets
python tools/ws_load_test.py --url wss://<host>/ws/transcribe --concurrency 12 --duration 8 --ramp 0.2
```

Interpreting the summary:

- **Admitted** should not exceed `max_concurrent_sessions` (the global cap),
  even across multiple tasks — that proves the shared DynamoDB limit works.
- **Rejected (limit)** counts connections closed with `TOO_MANY_SESSIONS`; this
  is expected once the cap is reached.
- Raise `--concurrency` past the cap on purpose to see rejections kick in.

## 4. What to watch (CloudWatch + DynamoDB)

- ECS `CPUUtilization` / `MemoryUtilization` — should trigger the target-tracking
  policies and add tasks up to `backend_max_capacity`.
- Actual running task count: Container Insights is disabled for cost, so read it
  from the ECS console/service events rather than a metric.
- DynamoDB table item count ≈ active sessions; it should drain to ~0 after the
  test (TTL removes any stragglers within `session_ttl_seconds`).
- The Phase 2 alarms (5XX, latency, unhealthy hosts) should stay green.

## 5. Rollback

```hcl
backend_max_capacity          = 1
enable_dynamodb_session_store = false   # optional; keeping it on is harmless
```

Then `terraform apply`. Setting max back to 1 returns to single-task behaviour
immediately; the in-memory registry is correct again at one task. The DynamoDB
table can stay (empty, near-zero cost) or be removed by leaving the store
disabled and running `apply`.

## Known limits

- `try_register` is check-then-put, so under a hard concurrency burst it can
  admit one or two sessions over the cap. Acceptable for an abuse guard; it is
  not exact accounting.
- The idle scale-to-zero scheduler reads the shared count, so an idle multi-task
  service still scales to zero correctly.
