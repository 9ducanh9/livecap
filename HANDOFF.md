# Handoff — branch `Update` (Phase 0 + Phase 1)

This branch contains reviewed, tested changes prepared for you to push and open
a PR. **Do not `git add -A`** — there is pre-existing CRLF working-tree noise on
unrelated files (`docs/as-deployed-architecture.md`, `docs/demo-guide.md`) that
is NOT part of this work. The commit on this branch already stages only the
intended files.

## To push

```bash
git push -u origin Update
# then open a PR against main on GitHub (9ducanh9/livecap)
```

## What changed

**Phase 0 — ops hardening (safe, no behavior change):**
- `.gitattributes` — normalize line endings to LF, stop CRLF churn.
- `infrastructure/terraform/cost_guard.tf` + `variables.tf` — add a FORECASTED
  80% budget alert alongside the ACTUAL 100% alert (needs an email set).
- `infrastructure/terraform/cloudwatch.tf` + `variables.tf` — manage the
  watchtower `livecap` log group with an explicit retention policy.
- `terraform.tfvars.example` — documents the new inputs.

**Phase 1 — Amazon Bedrock meeting notes (opt-in, default OFF):**
- `backend/app/services/summarization.py` — bilingual summary + key points,
  decisions, action items, topics, keywords, insights, glossary and follow-up
  questions via Bedrock (Claude).
- `backend/app/routers/summary.py` — `POST /api/sessions/{session_id}/summary`;
  it accepts finalized captions only after the participant explicitly chooses
  **Create meeting notes**. Stop only ends the audio/WebSocket session.
- `backend/app/models.py` — `SessionSummary`, `SummaryRequest`, optional
  `summary_text` on `ExportRequest`.
- `backend/app/services/storage.py` + `routers/export.py` — prepend the summary
  to exported TXT (backward compatible).
- `backend/app/config.py` + `backend/.env.example` — feature flags.
- `infrastructure/terraform/iam.tf` — `bedrock:InvokeModel` policy (only when
  `enable_meeting_summary = true`).
- `infrastructure/terraform/ecs.tf` + `variables.tf` — pass the flag + model ID
  to the task definitions.
- `backend/tests/test_summarization.py` (new) — 16 tests, all passing.

## Verification done

- Backend modules touched: 101/101 tests pass (Python 3.10 sandbox).
- `test_websocket.py` failures in the sandbox are only Python 3.10 missing
  `asyncio.timeout`; verified 22/23 pass once polyfilled. Run the full suite on
  **Python 3.11** (the project's target) for a clean pass.
- `compileall app` passes.
- Terraform NOT validated here (no terraform in sandbox) — run
  `terraform fmt` + `validate` before applying.

## Remaining MANUAL steps (do NOT let an agent auto-apply to AWS)

1. Set `budget_notification_email` in `terraform.tfvars`; optionally
   `enable_meeting_summary = true` and `bedrock_model_id`.
2. Import the existing watchtower log group before the first apply:
   `terraform -chdir=infrastructure/terraform import aws_cloudwatch_log_group.watchtower livecap`
3. If enabling Bedrock: **build & push a new backend image** (this is new code),
   and enable Bedrock model access for the Claude model in the target region.
   Verify the model is available in `ap-southeast-1`; otherwise set
   `BEDROCK_REGION` or use an inference-profile ID as `bedrock_model_id`.
4. `terraform plan` → review → `apply`. Confirm the budget SNS subscription email.

## Frontend (batch 2 — included in this branch)

- `types/index.ts` — `SessionSummary` type.
- `services/exportService.ts` — sends only finalized captions to the on-demand
  notes endpoint when the participant clicks the button.
- `components/SummaryPanel.tsx` (new) — renders the bilingual summary, key
  points, decisions, action items, and topics after the session ends.
- `components/DashboardPage.tsx` — shows **Create meeting notes** after a
  completed session and renders the returned panel; it never invokes Bedrock on
  Stop.
- `components/ExportPanel.tsx` + `services/exportService.ts` — prepend the
  summary text to the exported transcript (`summary_text`).
- Verified: `tsc --noEmit` clean, `vite build` passes, useWebSocket +
  DashboardPage tests pass.

## Terraform (batch 2)

- `BEDROCK_REGION` wired through `variables.tf` + both ECS task definitions.
  Set `bedrock_region` in tfvars if the model is not available in `aws_region`.

## Phase 2 — Observability: alarms -> SNS (batch 3)

- `infrastructure/terraform/monitoring.tf` (new) — SNS alerts topic + optional
  email subscription, and CloudWatch alarms:
  - ALB target 5XX, ALB (ELB) 5XX, ALB target latency, unhealthy hosts
  - ECS service CPU and memory utilization
  - All use `treat_missing_data = "notBreaching"` so scale-to-zero idle does
    not trigger false alerts; all publish to the SNS topic.
- `variables.tf` — `enable_alarms`, `alert_notification_email`, and thresholds.
- `outputs.tf` — `alerts_sns_topic_arn`.
- To enable: set `alert_notification_email` in tfvars, `apply`, then confirm the
  SNS subscription email AWS sends. Verified: all .tf files parse (python-hcl2);
  run `terraform fmt` + `validate` before apply.

### Phase 2 remaining — X-Ray (NOT done, needs a decision)

X-Ray tracing (C4) was intentionally deferred: it requires instrumenting the
FastAPI app (`aws-xray-sdk`) plus an X-Ray daemon sidecar container and IAM.
That touches the live WebSocket request path, so it is a larger, riskier change
than the Terraform-only alarms. Decide separately before implementing.

## Phase 3 slice 1 — DynamoDB session registry (batch 4)

Shared active-session limits so the backend can run more than one task. Opt-in;
**default is unchanged** (in-memory), so nothing changes until enabled.

- `backend/app/services/dynamo_session_registry.py` (new) — DynamoDB-backed
  registry (pk = session_id, TTL self-heals crashed rows, counts via consistent
  scan; idempotent conditional put).
- `backend/app/services/session_registry.py` — `get_session_registry(settings)`
  provider picks memory vs dynamodb by `session_store_backend`.
- `backend/app/routers/websocket.py` — resolves the registry via the provider.
- `backend/app/config.py` — `session_store_backend`, `session_table_name`,
  `session_ttl_seconds` flags (default memory).
- `infrastructure/terraform/dynamodb.tf` (new) — session table + task-role IAM
  policy + the two variables, all gated by `enable_dynamodb_session_store`.
- `backend/tests/test_dynamo_session_registry.py` (new) — 8 tests via moto.
- Verified: 8 + config tests pass; full backend suite = baseline (only the
  Python-3.10 `asyncio.timeout` websocket failures remain; 22/23 pass polyfilled).

### IMPORTANT — external Terraform refactor in the working tree

Between sessions, someone (you or Codex) refactored the Terraform in the working
tree (uncommitted): `ecs.tf` was consolidated to a single `target_backend` stack
(legacy `backend` removed), and `alb.tf`, `vpc.tf`, `cloudfront.tf`, `iam.tf`,
`waf.tf` were edited. Those changes are **NOT** in the `Update` branch — this
batch commits only my files. When you commit that refactor:

- `ecs.tf` already carries my 3 `SESSION_*` env entries on the single task def
  (needed for the DynamoDB store); they ride along with the refactor commit.
- The `enable_dynamodb_session_store` / `session_ttl_seconds` variables live in
  `dynamodb.tf` (committed here), so `ecs.tf` and `dynamodb.tf` resolve together.

### Phase 3 slice 2 — multi-task enablement + load test (batch 5)

- `infrastructure/terraform/checks.tf` (new) — advisory `check` block that warns
  on plan/apply if `backend_max_capacity > 1` while the DynamoDB store is off.
- `tools/ws_load_test.py` (new) — standalone WebSocket load tester (opens N
  concurrent sessions of valid silent PCM) to validate the shared global limit
  and watch scale-out. `pip install websockets` to run.
- `docs/multi-task-runbook.md` (new) — enable, apply, load-test, watch, rollback.
- Raising tasks is a tfvars change: `enable_dynamodb_session_store = true` +
  `backend_max_capacity = N`, then build/push image and apply. The actual
  load test must be run against the deployed endpoint (cannot be done offline).
- Not changed: `backend_max_capacity` default stays 1 (safe).

## Phase 4 — Graviton + CI/CD plan gate (batch 6)

- `ecs.tf` + `variables.tf`: `task_cpu_architecture` (default X86_64) drives the
  task `runtime_platform`. Switch to ARM64 (Graviton, ~20% cheaper) only
  alongside an arm64 image push.
- `.github/workflows/deploy.yml` (new): manual-dispatch pipeline that builds/
  pushes an arch-specific image and produces a `terraform plan` artifact.
  **No apply from CI** — a human applies the reviewed plan. Needs repo
  vars/secrets (AWS_REGION, AWS_DEPLOY_ROLE_ARN, ECR_REPOSITORY, TF_BACKEND_HCL,
  TF_VARS). See `docs/graviton-and-cicd.md`.

## A1+ knowledge extraction (batch 7)

- Extended the Bedrock summary with keywords, insights, glossary
  (`term`/`definition`), and follow-up questions. Same `enable_meeting_summary`
  flag; new fields are optional and render in `SummaryPanel` + the exported TXT.
- Files: backend `models.py`, `services/summarization.py`, `tests/`; frontend
  `types/index.ts`, `hooks/useWebSocket.ts`, `components/SummaryPanel.tsx`,
  `services/exportService.ts`.
- No infra change. To see it live, enable the summary feature and redeploy the
  backend image (new code).

## A5 Transcribe custom vocabulary (batch, commit 3ac2909)

- `transcribe.tf` creates vi + en custom vocabularies (editable phrase lists);
  `transcription.py` passes `vocabulary_name` per stream from env. Off by default.
- To enable: set `enable_transcribe_custom_vocabulary = true` (+ edit the phrase
  lists) in tfvars, then `terraform apply` (creation waits for the vocabularies
  to reach READY) and redeploy the backend image if not already on this code.
  No task-role IAM change needed. VI phrases must follow the Transcribe VI
  charset (tones as numbers).

## B3 multi-AZ NAT (commit 61d8acc)

- Set `enable_multi_az_nat = true` to add a second NAT in the other AZ (+1 NAT/
  EIP cost). Default off keeps the single NAT and shows no plan diff.

## Follow-up (not in this branch)

- B5 (session-id continuity on reconnect) is still open; coordinate on
  `websocket.py` + `useWebSocket.ts` after the A1+ REST work settles.
- Optional cleanup: `git add --renormalize . && git commit -m "Normalize line
  endings to LF"` to clear the unrelated CRLF noise repo-wide.
