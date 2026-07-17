# Collaboration Log — LiveCap

Shared worklog for the humans and AI agents working on this repo (e.g. Claude in
Cowork and Codex). **Read this before starting; append an entry after every
change.** It is the single place to learn what was done, why, and what is next,
so neither side has to reverse-engineer the other's work from diffs.

Companion docs: `HANDOFF.md` (push/deploy steps for the current branch),
`docs/upgrade-roadmap.md` (the plan and phases), `docs/multi-task-runbook.md`.

---

## How to use this file

1. **Before working:** read "Current state" and the latest change-log entries.
2. **After working:** add a new entry at the top of the Change log with: date,
   who (agent/human), branch, commit hashes, what changed, why, and how it was
   verified. Keep it short — one screenful per batch.
3. **Update "Current state"** whenever flags, branch, or pending-deploy status
   change.
4. If you leave the working tree with uncommitted changes, say so under
   "Open items" so the other side does not commit or clobber them.

## Working agreement

- Active branch: **`Update`** (off `main`). Push, then open a PR to `main`.
- **Do not commit the other side's uncommitted work.** Stage only your own files
  (`git add <path> ...`, not `git add -A`). If files are entangled, split them
  (e.g. move new variables into a new file) or leave them for the author.
- **No auto-deploy to AWS.** Agents may write Terraform/code and run
  `plan`/`validate`; a human runs `apply`. Never `apply`/`destroy` from an agent.
- Line endings: repo is LF (`.gitattributes`). Two docs
  (`docs/as-deployed-architecture.md`, `docs/demo-guide.md`) carry pre-existing
  CRLF churn — ignore them; do not `git add -A`.
- Tests: backend needs **Python 3.11** (uses `asyncio.timeout`); on 3.10 the
  `test_websocket.py` timeout tests fail spuriously. Frontend: `npm test` +
  `npm run build`.
- Feature work is flag-gated and defaults to OFF so `main`/prod behaviour is
  unchanged until explicitly enabled.

---

## Current state (2026-07-17)

Branch `Update` = `main` + 6 commits. Working tree clean except the known CRLF
churn on the two docs above.

**Feature flags (all default OFF / unchanged behaviour):**

| Capability | Flag(s) | Default |
|---|---|---|
| Bedrock meeting summary | `ENABLE_MEETING_SUMMARY` / `enable_meeting_summary`; `BEDROCK_MODEL_ID`, `BEDROCK_REGION` | off |
| CloudWatch alarms → SNS | `enable_alarms` (+ `alert_notification_email`) | on (topic; email only if set) |
| Budget email alerts | `budget_notification_email` | off until email set |
| DynamoDB session store | `enable_dynamodb_session_store` / `SESSION_STORE_BACKEND` | off (in-memory) |
| Multi-task (>1) | `backend_max_capacity` | 1 |
| Graviton (arm64) | `task_cpu_architecture` | X86_64 |
| CI/CD plan-gate | `.github/workflows/deploy.yml` (manual dispatch) | needs repo vars/secrets |

**Pending human actions before any of this is live:** set the relevant tfvars,
build/push a new backend image (new code), enable Bedrock model access in-region,
`terraform plan` → review → `apply`, confirm SNS/budget subscription emails.
Details in `HANDOFF.md`.

---

## Change log (newest first)

### 2026-07-17 — Claude (Cowork) — Phase 4: Graviton + CI/CD plan gate
- Files: `infrastructure/terraform/ecs.tf` (+`runtime_platform`),
  `variables.tf` (+`task_cpu_architecture`, default X86_64),
  `.github/workflows/deploy.yml` (new), `docs/graviton-and-cicd.md` (new).
- Graviton is opt-in: set `task_cpu_architecture = "ARM64"` + push an arm64
  image together. New manual-dispatch pipeline builds/pushes an arch-specific
  image and produces a `terraform plan` artifact — **no apply from CI**.
- Verified: YAML + HCL parse. Pipeline needs repo vars/secrets before it runs.

### 2026-07-17 — Claude (Cowork) — Phase 3 slice 2: multi-task enablement
- Commit `33fcea7`. Files: `infrastructure/terraform/checks.tf`,
  `tools/ws_load_test.py`, `docs/multi-task-runbook.md`, `HANDOFF.md`.
- Advisory `check` warns if `backend_max_capacity > 1` while the DynamoDB store
  is off. Added a standalone WebSocket load tester and a runbook.
- Raising tasks is a tfvars change; default stays 1. Load test runs against the
  deployed endpoint (cannot be done offline). Verified: HCL parses, script
  compiles.

### 2026-07-17 — external (Codex/local) — infra refactor
- Commit `6a725e3` "Retire legacy rollback infrastructure". Consolidated the
  Terraform to a single `target_backend` stack (removed the legacy `backend`
  task/service) and cleaned up `alb.tf`, `vpc.tf`, `cloudfront.tf`, `iam.tf`,
  `waf.tf`. This commit also carried Claude's `SESSION_*` task env additions.
- Reconciled OK with Claude's work: no dangling refs, all `.tf` parse.

### 2026-07-17 — Claude (Cowork) — Phase 3 slice 1: DynamoDB session registry
- Commit `8a6e864`. New `dynamo_session_registry.py` (shared active-session
  limits, TTL self-heal, consistent-scan counts), `get_session_registry`
  provider (memory default vs dynamodb), config flags, `dynamodb.tf` (table +
  IAM + vars), 8 moto tests. Default unchanged (in-memory).

### 2026-07-17 — Claude (Cowork) — Phase 2 / C1: alarms → SNS
- Commit `7a0b092`. New `monitoring.tf`: SNS alerts topic + alarms (ALB 5XX,
  ELB 5XX, latency, unhealthy hosts, ECS CPU/memory); `notBreaching` so
  scale-to-zero is quiet. Vars + `alerts_sns_topic_arn` output.
- X-Ray (C4) intentionally deferred (needs app instrumentation + sidecar).

### 2026-07-17 — Claude (Cowork) — batch 2: frontend summary + BEDROCK_REGION
- Commit `9349d8c`. Frontend renders `session_summary` (new `SummaryPanel`,
  `useWebSocket` parse, summary text added to export). Terraform wires
  `BEDROCK_REGION`. Verified: `tsc` clean, `vite build` + tests pass.

### 2026-07-17 — Claude (Cowork) — Phase 0 + Phase 1
- Commit `112163b`. Phase 0: `.gitattributes` (LF), budget forecast alert,
  watchtower log-group retention. Phase 1: Amazon Bedrock end-of-session meeting
  summary (backend service + websocket + models + export + IAM + 16 tests),
  default off.

### (pre-existing) — baseline
- `main` @ `b1347f7` — v1.5.2 line: real-time VI/EN captions, ECS Fargate,
  CloudFront/WAF, Transcribe/Translate, scale-to-zero. See `README.md`.

---

## Open items / next up

- **Phase 4** (not started): Graviton/arm64 image (~20% cheaper), CI/CD
  auto-deploy pipeline with a plan gate (no auto-apply).
- **Phase 2 C4** (deferred): X-Ray tracing — needs FastAPI instrumentation + an
  X-Ray daemon sidecar; decide before implementing.
- **Deploy validation:** none of the new capability is live yet; see the pending
  human actions above and `HANDOFF.md`.
- Optional: repo-wide `git add --renormalize .` to clear the CRLF doc churn.
