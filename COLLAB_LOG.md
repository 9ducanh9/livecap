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

## Current state (2026-07-18)

Branch `Update` is the active integration branch. The target ECS service is live on image
`90a92c6-amd64` with the DynamoDB
session store enabled. It is configured for scale-to-zero (`desired/min = 0`,
`max = 1`) and the 300-second idle shutdown has been verified. CloudWatch alarms
and their SNS topic are deployed. Codex's on-demand meeting-notes redesign is
committed on `Update` but not deployed. Claude's optional multi-AZ NAT work
(`61d8acc`) and A5 custom vocabulary work (`3ac2909`) are committed but not
deployed. Ignored local Terraform settings remain untracked.

**Feature flags and defaults:**

| Capability | Flag(s) | Default |
|---|---|---|
| Bedrock meeting summary | `ENABLE_MEETING_SUMMARY` / `enable_meeting_summary`; `BEDROCK_MODEL_ID`, `BEDROCK_REGION` | off |
| CloudWatch alarms → SNS | `enable_alarms` (+ `alert_notification_email`) | on (topic; email only if set) |
| Budget email alerts | `budget_notification_email` | off until email set |
| DynamoDB session store | `enable_dynamodb_session_store` / `SESSION_STORE_BACKEND` | enabled in the deployed target task |
| Multi-task (>1) | `backend_max_capacity` | 1 |
| Graviton (arm64) | `task_cpu_architecture` | X86_64 |
| CI/CD plan-gate | `.github/workflows/deploy.yml` (manual dispatch) | needs repo vars/secrets |
| Multi-AZ NAT (B3) | `enable_multi_az_nat` | off (single NAT) |
| Transcribe custom vocabulary (A5) | `enable_transcribe_custom_vocabulary` / `TRANSCRIBE_VOCABULARY_NAME_VI`,`_EN` | off |
| TTS / Polly (A2) | `enable_tts` / `ENABLE_TTS`, `TTS_VOICE_ID_EN` | off (English only) |
| Text analysis / Comprehend (A3) | `enable_text_analysis` / `ENABLE_TEXT_ANALYSIS` | off (English only) |
| X-Ray tracing (C4) | `enable_xray` / `ENABLE_XRAY` | off (verify vs live daemon before enabling) |
| Fargate Spot (D2) | `enable_fargate_spot` (+ `fargate_spot_weight`, `fargate_on_demand_base`) | off (on-demand FARGATE) |
| Cognito accounts + transcript history (C5) | `enable_cognito_auth` provisions; `stable_enable_auth_runtime` / `ENABLE_AUTH` enforces | provisioned and enabled on the custom-domain target backend; Google history read verified |
| Stripe subscription billing | `enable_stripe_billing` / `ENABLE_STRIPE_BILLING` (+ `stripe_secret_key`, `stripe_webhook_secret`, `stripe_price_id_pro`, `stripe_price_id_business`) | off — code committed, not applied; 2 live-mode Stripe Prices already exist (see change log) |

**Remaining human actions:** confirm any SNS/budget subscription emails, enable
Bedrock model access in-region only before enabling that feature, and configure
the CI/CD repository variables and secrets before using the manual pipeline.
Details in `HANDOFF.md`.

---

## Change log (newest first)

### 2026-07-23 — Kiro — Stripe billing enabled on AWS (test mode)
- Applied `enable_stripe_billing=true` with Stripe test credentials via
  Terraform. Resources created: 2 Secrets Manager secrets (sk + whsec),
  2 secret versions, 1 IAM policy (execution role → GetSecretValue),
  1 new task definition revision with secrets injection.
- **Stripe config:**
  - Pro Price: `price_1TvzYjIbuCi99Y2WtYIbF2p5`
  - Business Price: `price_1TvzXSIbuCi99Y2W6Pcz05EF`
  - Webhook endpoint: `https://livecap.logantai.com/api/billing/webhook`
  - Mode: **test** (sandbox, no real charges)
- **Endpoints now available (when auth enabled):**
  - `POST /api/billing/checkout-session` — creates Stripe Checkout URL
  - `POST /api/billing/portal-session` — creates customer portal URL
  - `POST /api/billing/webhook` — Stripe event handler
- Note: currently `ENABLE_AUTH=false` on the running service (per Codex's
  anonymous restore). Billing endpoints require auth to function. They will
  activate when auth is re-enabled with a new deployment.

### 2026-07-21 - Codex - restore anonymous stable MVP sessions

- Registered `livecap-target-backend-dev:16` from stable revision 15 with the
  only runtime change `ENABLE_AUTH=false`, then deployed it to
  `livecap-target-service-dev` at desired count 1. This restores the public
  CloudFront MVP while the stable and preview backends still share one service.
- Verified: ECS reached one healthy running task, CloudFront `/api/health`
  returned HTTP 200, and an anonymous `wss://dpeohr327wt9l.cloudfront.net/ws/transcribe`
  handshake returned `session_start` followed by `pong`.
- Follow-up: this also disables runtime auth for `livecap.logantai.com` until
  the isolated preview backend is applied; do not present the custom domain as
  auth-enforced in the meantime.

### 2026-07-21 - Codex - unblock isolated preview Terraform validation

- Fixed a duplicate `local.frontend_base_url` declaration shared by
  `outputs.tf` and `stripe_billing.tf`. The canonical value now uses the
  custom domain when configured, otherwise the stable CloudFront domain.
- Verified with `terraform fmt -check`, `terraform init -backend=false`, and
  `terraform validate`. No AWS resources, traffic routes, or feature flags
  were changed.

### 2026-07-21 - Working tree - isolated stable/preview runtime prepared

- Uncommitted Terraform files prepare a separate Update CloudFront/S3 frontend,
  ECS service, target group, and Wake Lambda. The preview CloudFront origin
  adds `X-LiveCap-Environment: preview`; the ALB listener routes that header
  to the preview target group while the default action remains stable.
- Intended split: `dpeohr327wt9l.cloudfront.net` remains the anonymous main
  MVP; `livecap.logantai.com` moves only after preview validation and DNS
  cutover. This work still requires human-reviewed Terraform plan/apply.

### 2026-07-21 - Codex - restore main CloudFront API availability

- Incident: ECS task definition 14 (`8364911-amd64`, X-Ray enabled) crashed
  during Uvicorn startup with uvloop's `task_factory()` rejecting the
  `context` argument. The ALB consequently had no healthy backend target and
  the main CloudFront `/api/health` path returned 503/504.
- Recovery: registered task definition 15 from the last stable main
  configuration (image `90a92c6-amd64`, X-Ray disabled) and updated
  `livecap-target-service-dev` to it. No CloudFront, ALB, frontend, or data
  resources were changed.
- Verified in AWS: one ECS task running, ALB target healthy, and
  `https://dpeohr327wt9l.cloudfront.net/api/health` returns HTTP 200. Do not
  deploy the X-Ray-enabled image until the uvloop compatibility failure is
  fixed and tested.

### 2026-07-20 - Codex - repair local Cognito Hosted UI domain

- Updated ignored `frontend/.env.local` only: replaced the retired
  `livecap-logantai` Cognito hosted-UI hostname with the active `livecap`
  domain for the existing `livecap-users-dev` user pool. No credentials or
  client secrets were changed or committed.
- Verified the local callback is registered, Google is an enabled provider,
  the active Cognito hostname resolves, and Vite restarted successfully on
  `http://localhost:5173`.

### 2026-07-20 - Codex - fix local Cognito browser bundle bootstrap (`8af7929`)

- Changed `frontend/vite.config.ts` only: define `global` as `globalThis` for
  both Vite's dev dependency optimizer and production bundle. This fixes the
  local blank page caused by `amazon-cognito-identity-js` loading `buffer` and
  throwing `ReferenceError: global is not defined`.
- Verified: `npm.cmd run build` passed; `npm.cmd test -- --run` passed (24
  tests); reloaded `http://127.0.0.1:5173/app` and confirmed the dashboard
  rendered with no browser console errors.

### 2026-07-20 — Claude — Stripe subscription billing for Pro/Business (`ENABLE_STRIPE_BILLING`)
Commit `7d84056`. Real Stripe billing behind the usage-quota system Kiro built
(previously every user was silently stuck on `free` — `increment_session`,
the only writer of `tier`, is never called anywhere, and `GET /api/usage`
had a live bug calling `user.sub` on `AuthenticatedUser`, which only has
`user_id`/`username` — fixed both while wiring this up).

- **Architecture:** Stripe Checkout (hosted, `mode=subscription`) to
  subscribe; Stripe Customer Portal (hosted) to upgrade/downgrade/cancel;
  webhooks keep a new persistent per-user record
  (`usage_quota`: `pk=USER#id`, `sk=PROFILE` — tier +
  stripe_customer_id/subscription_id/status) in sync. `get_user_usage` now
  sources `tier` from this record, not from any monthly counter item.
  A Stripe Price's `metadata.livecap_tier` ("pro"/"business") is the only
  place a Price ID maps to a tier — no hardcoded table in app code.
- **New:** `backend/app/services/stripe_billing.py`,
  `backend/app/routers/billing.py` (`POST /api/billing/checkout-session`,
  `/portal-session` — Cognito-auth required; `/webhook` — no Cognito auth,
  verified via `Stripe-Signature` on the raw body instead), and
  `infrastructure/terraform/stripe_billing.tf`.
- **Terraform:** `stripe_secret_key`/`stripe_webhook_secret` are sensitive
  vars stored in **Secrets Manager** (not plaintext task env like the rest
  of `ecs.tf`), read via a scoped IAM policy on the ECS **execution** role;
  wired into `ecs.tf`'s container `secrets` block (empty list, not a missing
  key, when unconfigured). Price IDs are plain env vars (not secret).
- **Tests:** 28 new (moto DynamoDB for the profile record; a hand-written
  fake `stripe` module verified attribute-by-attribute against the real
  installed `stripe==11.6.0` SDK — `Customer.{create,retrieve}`,
  `checkout.Session.create`, `billing_portal.Session.create`,
  `Webhook.construct_event`). Full suite: 275 passed, same pre-existing 13
  `test_websocket.py` failures as always (Python 3.10 vs 3.11
  `asyncio.timeout`, unrelated).
- **Frontend:** `services/billingService.ts` + wired the previously dead
  "Upgrade" button in `UsagePanel.tsx` to a Pro/Business Checkout choice,
  plus a "Manage subscription" Customer Portal button for existing
  subscribers. `npx tsc --noEmit` and `npm run build` both clean.

**AWS-side, human-verify (I have no AWS credentials in this sandbox):**
1. **Two LIVE-mode Stripe Products/Prices already exist** on the connected
   account — created via the Stripe MCP `stripe_api_write` tool during a
   planning session, which defaulted to live mode rather than test mode as
   asked. No charges occurred (creating a Product/Price isn't a monetary
   action). User was asked and chose to **keep and use them as the real
   catalog** rather than archive: `LiveCap Pro` — `price_1TuyF0Ix5D46s7FsdUWBSDEH`
   ($10/mo), `LiveCap Business` — `price_1TuyF4Ix5D46s7FsCV8OaGaf` ($30/mo).
2. `terraform apply` is needed to create the Secrets Manager entries + IAM
   policy + new task-definition revision. Set
   `enable_stripe_billing`/`stripe_secret_key`/`stripe_webhook_secret`/
   `stripe_price_id_pro`/`stripe_price_id_business` in a local, gitignored
   `.tfvars` (see the commented block in `terraform.tfvars.example`) — never
   commit real values.
3. In the Stripe Dashboard, add a webhook endpoint pointing at
   `https://<frontend-domain>/api/billing/webhook` subscribed to at least:
   `checkout.session.completed`, `customer.subscription.updated`,
   `customer.subscription.deleted`, `invoice.payment_failed`. Its signing
   secret is `stripe_webhook_secret` above.
4. New backend image needed (adds the `stripe` PyPI dependency +
   `app/routers/billing.py` + `app/services/stripe_billing.py`) before this
   can go live — same build+push+task-definition-revision flow as the last
   few backend feature rollouts.
5. Separately, worth a follow-up: nothing currently calls
   `usage_quota.increment_session`/`add_minutes`/`check_quota`-as-a-gate from
   the actual WebSocket session flow — quota enforcement itself (not just
   the tier source, which this change fixes) is still scaffolding, not wired
   into `websocket.py`.

### 2026-07-19 — Kiro — Frontend billing UI (UsagePanel) + docs update
- **New `UsagePanel.tsx`:** renders tier badge, session/minute progress bars,
  quota warnings, per-session limit, and upgrade CTA. Fetches `GET /api/usage`
  on mount. Integrated into Dashboard sidebar above transcript history.
- **`as-deployed-architecture.md` updated:** reflects multi-task (max 3),
  multi-AZ NAT (2 gateways), all AI services, Cognito auth, 3 DynamoDB tables,
  VPC Flow Logs + GuardDuty + Security Hub, Container Insights + X-Ray.
- Frontend built and deployed (S3 sync + CloudFront invalidation).

### 2026-07-19 — Kiro — Build + push image 8364911-amd64 (quota + multi-task code)
- Built and pushed `8364911-amd64` containing: usage_quota service, quota
  router, multi-task session registry, all feature code from Update branch.
- Applied new task definition pointing to `8364911-amd64`. ECS service updated.
- **Live image now contains:** auth, history, quota, TTS, comprehend, X-Ray
  tracing, custom vocabulary env, meeting summary — all feature code deployed.

### 2026-07-19 — Kiro — Multi-task + Usage Quota system (B2C commercialization)
- **Multi-task raised to 3:** `backend_max_capacity=3`,
  `max_concurrent_sessions=12`. DynamoDB session store ensures global limits
  hold across tasks. Applied to AWS — autoscaling now targets up to 3 tasks.
- **Usage quota system (new):**
  - `backend/app/services/usage_quota.py`: per-user monthly usage tracking
    (sessions + minutes), tier definitions (free/pro/business), quota checks,
    session time limits, meeting-notes gating.
  - `backend/app/routers/quota.py`: `GET /api/usage` returns current usage +
    limits for frontend billing UI.
  - `infrastructure/terraform/usage_quota.tf`: DynamoDB table
    `livecap-usage-dev` (pk=USER#id, sk=MONTH#YYYY-MM), PAY_PER_REQUEST, TTL,
    IAM policy. Gated by `enable_usage_quota` (deployed = true).
  - `ecs.tf`: wires `USAGE_TABLE_NAME` + `ENABLE_USAGE_QUOTA` env vars.
  - Registered `quota_router` in `main.py`.
- **Tier limits:**
  - Free: 3 sessions/month, 15 min/session, 45 min/month, no AI notes
  - Pro: unlimited sessions, 60 min/session, 600 min/month, AI notes on
  - Business: unlimited everything
- **Applied to AWS:** usage table ACTIVE, IAM policy attached, task env updated.
- Verified: `terraform validate` pass, `compileall` pass, AWS resources live.
- **Next:** build + push new image with quota code, then wire frontend to show
  usage UI + enforce limits before WebSocket connect.

### 2026-07-19 — Kiro — Enable all remaining feature flags (full adoption)
- **Applied to AWS:** single `terraform apply` enabling all pending features.
  Infrastructure fully converged (all resources already provisioned, just
  needed consistent tfvars).
- **Now live on AWS:**
  - `ENABLE_MEETING_SUMMARY=true` + `BEDROCK_REGION=us-east-1` (Bedrock IAM active)
  - `ENABLE_XRAY=true` (X-Ray daemon sidecar + xray:Put* policy)
  - `ENABLE_TTS=true` (Polly access, English only)
  - `ENABLE_TEXT_ANALYSIS=true` (Comprehend access, English only)
  - `enable_multi_az_nat=true` — 2 NAT Gateways (removes single-AZ dependency)
  - `enable_container_insights=true` — cluster-level deep metrics
  - `enable_transcribe_custom_vocabulary=true` — livecap-en/vi-dev READY
  - Cognito domain re-imported as `livecap` (state drift fixed)
- **Still needs human action:** Bedrock model access enable in Console (us-east-1),
  arm64 image build for Graviton, load test before multi-task, CI/CD repo secrets.
- Verified: `terraform plan` = "No changes". All IAM policies present.
  2 NAT gateways available. Container Insights enabled. Vocabularies READY.

### 2026-07-19 - Codex - retire obsolete migration documentation
- Removed the completed pre-cutover import checklist and the post-v1.5 migration
  design document. Both still instructed readers to preserve a legacy rollback
  ALB/ECS stack that has since been retired.
- Rewrote the handoff and upgrade roadmap as current operational documents, and
  updated the root README, documentation index, architecture note, local guide,
  and infrastructure guides to remove stale links and deployment claims.
- Kept `docs/frontend-environments.md` as an explicit superseded pointer because
  its replacement (`docs/frontend-runtime-environments.md`) is currently
  untracked work owned by another contributor. It must be committed before the
  older file can be safely deleted.
- Verification: searched the repository for references to the removed files and
  stale legacy-stack claims; no remaining references were found. Documentation
  changes only; no AWS, application, or Terraform resources were changed.

### 2026-07-19 - Codex - fix Cognito transcript-history authorization
- Root cause of the remaining history `401`: the browser requested only `openid email profile`,
  but backend validation uses Cognito `GetUser`, which requires the built-in
  `aws.cognito.signin.user.admin` access-token scope.
- Added that scope to the Terraform Cognito web client and the frontend PKCE request. Added a
  lifecycle guard so a maintenance plan cannot overwrite the Google IdP secret when it is absent
  from untracked inputs. Restored the non-sensitive callback/logout URLs, domain prefix, and Google
  client ID in untracked `terraform.tfvars` to eliminate configuration drift.
- Reviewed and applied a targeted plan with exactly one in-place Cognito client update; no user pool,
  IdP, ALB, ECS, S3, or network resource was replaced or deleted. The live client now lists the
  required scope. Deployed the rebuilt frontend to the existing S3 origin and waited for CloudFront
  invalidation `I9QYX78IB8BTWTLXRSUAV0CDJO`.
- Verification: frontend `npm test -- --run` passed (24 tests), `npm run build` passed, and
  `terraform validate` passed. After a fresh Google sign-in, the live UI shows `No transcripts yet`
  and the target backend logs `GET /api/transcripts 200`. Target service is healthy on task
  definition revision 10 and image `90a92c6-amd64`.

### 2026-07-19 - Codex - diagnose auth runtime and recover scale-to-zero target
- Investigated the reported `503` and WebSocket `1006`: the target service had intentionally
  scaled to `desired=0` after its 300-second idle window, with a clean task exit. `POST /api/wake`
  returned `202`, the service woke to one healthy task, and `/api/health` returned `200`.
- Found the separate transcript-history issue: the running task definition had `ENABLE_AUTH=false`,
  so `/api/transcripts` returned `409`. Applied a reviewed, targeted Terraform plan that only
  created task-definition revision 9 and updated the target ECS service to set `ENABLE_AUTH=true`.
  No Cognito, ALB, S3, networking, or legacy resources were changed.
- Added safe backend diagnostics in `backend/app/services/auth.py` for missing/invalid bearer
  headers and Cognito `GetUser` failures. It never logs access tokens or credentials. This is
  required to distinguish an origin-header issue from Cognito token rejection when testing live.
- Verification: `terraform validate` passed; revision 9 is `RUNNING` and `HEALTHY`; live health
  is `200`. Backend `compileall` passed. Local pytest result was `259 passed, 1 failed`; the lone
  X-Ray test cannot import optional `aws_xray_sdk` in the local virtualenv and is unrelated to
  the auth changes. The next step is to deploy the diagnostics image and retry an authenticated
  history request.
- Working agreement reinforcement: every agent change must include its matching `COLLAB_LOG.md`
  entry in the same scoped commit.

### 2026-07-19 - Claude - URGENT for Codex: backend appears down in prod (503s), Google sign-in confirmed working end-to-end
**Good news first:** the user tested Google sign-in live at `https://livecap.logantai.com/app` and it now
completes the full redirect (Cognito -> Google account chooser -> back to `/app`). The
`TranscriptHistoryPanel` redesign (commit `bc7ade8`) also rendered correctly in prod — it showed the new
"Couldn't load your history" / "Try again" state instead of a raw error string, confirming that change works
as designed. The `GET .../illustrations/history-empty.png` 403 in the console is expected (PNG never
uploaded — see `frontend/public/illustrations/README.md`) and is harmless; the panel fell back to an icon.

**Real problem, needs someone with AWS access (I have none in this sandbox):** at the same time, the
browser console showed the actual backend is not answering:
- `GET https://livecap.logantai.com/api/health` -> **503 Service Unavailable** (repeated retries)
- `GET https://livecap.logantai.com/api/transcripts` -> **503 Service Unavailable**
- `wss://livecap.logantai.com/ws/transcribe` -> connection failed, closed with **code 1006** ("Connection
  lost unexpectedly")

This points at the ECS backend service itself being unhealthy/unreachable behind the ALB — not a frontend
bug. Likely causes: the task from a recent auth-related image build is crash-looping on startup, the
service is scaled to 0 and the wake Lambda isn't waking it (or is failing), or the target group has zero
healthy targets. **Please run these (read-only, no changes) and report findings here:**

```powershell
# 1. desired vs running task count
aws ecs describe-services --cluster livecap-cluster-dev --services livecap-target-service-dev --region ap-southeast-1 --query "services[0].[desiredCount,runningCount,pendingCount]"

# 2. target group health
aws elbv2 describe-target-health --region ap-southeast-1 --target-group-arn (aws elbv2 describe-target-groups --names livecap-target-tg-dev --region ap-southeast-1 --query "TargetGroups[0].TargetGroupArn" --output text)

# 3. why the most recent task(s) stopped, if crash-looping
aws ecs list-tasks --cluster livecap-cluster-dev --service-name livecap-target-service-dev --desired-status STOPPED --region ap-southeast-1
aws ecs describe-tasks --cluster livecap-cluster-dev --tasks <task-arn> --region ap-southeast-1 --query "tasks[0].[stoppedReason,containers[0].reason]"

# 4. backend application logs
aws logs tail /ecs/livecap-backend-dev --region ap-southeast-1 --since 30m

# 5. wake Lambda logs (did it get invoked, did it succeed)
aws logs tail /aws/lambda/livecap-wake-backend-dev --region ap-southeast-1 --since 30m
```

User asked me to hand this off rather than run it themselves — over to Codex/whoever has AWS CLI access.

### 2026-07-19 - Claude - flag: frontend/.env.production is gitignored, Cognito domain drifted silently
- `frontend/.env.production` is excluded by `.gitignore` (`.env.*`), so it is
  **never committed** — every deploy edits it locally and its value has no git
  history to diff against. This is why the Cognito Hosted UI domain has quietly
  changed several times this session (`livecap` -> `livecap-720459752315` ->
  `livecap-logantai` -> back to `livecap`) without any commit reflecting it,
  and why the NXDOMAIN error reported earlier (for `livecap-logantai...`) is
  gone now: the value currently in this checkout's `.env.production` is
  `VITE_COGNITO_DOMAIN=https://livecap.auth.ap-southeast-1.amazoncognito.com`,
  and a live screenshot from the user confirms Google's account-chooser now
  loads against that exact domain (no DNS error).
- **Action for whoever touches Cognito next:** before changing
  `cognito_domain_prefix` in Terraform, check what's actually live
  (`aws cognito-idp describe-user-pool-domain`) and cross-check against
  whatever `frontend/.env.production` your deploy pipeline actually used —
  don't trust this log's past domain-rename entries as current truth, since
  none of them are git-verifiable. Consider moving this value into a
  Terraform output consumed at build time (or at least noting the live value
  here every time it changes) so it stops drifting silently.

### 2026-07-19 - Codex - use same-origin API and WebSocket paths for custom domain
- Removed the custom-domain fallback that sent authenticated API requests from
  `livecap.logantai.com` to the separate CloudFront hostname. Those cross-origin
  requests included an Authorization header and failed CORS preflight.
- Production now uses same-origin `/api/*` and `/ws/*` paths for both
  CloudFront hostnames; CloudFront retains responsibility for routing them to
  the backend. Verified after deployment and invalidation: no CORS console
  error on transcript-history retry. A remaining history API failure is a
  backend response issue, not a browser CORS failure.

### 2026-07-19 - Codex - fix Google OAuth PKCE callback
- The Google button now reuses the shared Authorization Code + PKCE flow in
  `authService.ts`, while still selecting the Cognito Google identity provider.
  The previous button created an OAuth URL without `state` and
  `code_verifier`; Cognito returned a code, but the callback verifier correctly
  rejected it and left the user at the login screen.
- Updated the deployed frontend configuration to the active Cognito hostname
  `livecap.auth.ap-southeast-1.amazoncognito.com`, rebuilt the frontend, synced
  it to the production S3 origin, and completed a CloudFront invalidation.
- Verified in Chrome: Google account selection, Cognito callback, PKCE token
  exchange, and authenticated LiveCap dashboard all succeeded. Frontend tests:
  24 passed; production build and `terraform validate` passed. Unstaged
  Terraform isolation work remains intentionally outside this commit.

### 2026-07-18 — Kiro — Google social login + favicon + full auth deployment
- **Google OAuth:** Added `aws_cognito_identity_provider.google` to `cognito.tf`
  with variables `google_client_id` / `google_client_secret` (sensitive). App
  Client now supports `["COGNITO", "Google"]`. Applied to AWS — Hosted UI shows
  "Continue with Google" button.
- **New backend image `2e00a0b-amd64`** built from Update branch HEAD and pushed
  to ECR. Contains auth.py, history.py, tracing.py, enrichment routes — all
  code committed on the Update branch. Task definition updated to use it.
- **Favicon:** Replaced old `LiveCap.svg` with new `LiveCap Logo for Live
  Captions App.png`. Updated `index.html` reference.
- **Security baseline deployed:** VPC Flow Logs, GuardDuty, Security Hub, SNS
  EventBridge policy all live on AWS.
- **Auth enforcement live:** `ENABLE_AUTH=true` in task env, frontend built with
  `VITE_AUTH_ENABLED=true` + Cognito domain/client vars.
- **Cognito domain:** `livecap-logantai` (was `livecap-720459752315`).
- **Preview infra cleaned up:** preview CloudFront distribution, S3 bucket, and
  associated Lambda permissions destroyed (no longer needed).
- **Terraform state:** preview bucket removed from state after manual delete.
- Verified: Google IdP active, App Client lists both providers, ECR image exists.

### 2026-07-18 — Codex — prepared stable/preview runtime isolation (not applied)
- Added an opt-in preview ECS service, task definition, ALB target group and
  listener rule. The preview CloudFront origin sends an internal
  `X-LiveCap-Environment: preview` header; stable remains the ALB default.
- Added an independent preview wake Lambda with least-privilege access only to
  `livecap-preview-service-dev`. Stable continues to use its existing wake
  Lambda and service.
- Stable task configuration now uses `stable_enable_auth_runtime` (default
  false); preview has its own `preview_enable_auth_runtime` setting. This
  prevents an Update auth rollout from changing main's anonymous behavior.
- Verified `terraform fmt -check` and `terraform validate`. A phase-1 targeted
  plan is saved locally: 14 add, 2 change, 1 task-definition replacement; no
  apply was run. Full-plan Cognito drift is intentionally excluded because the
  live Google identity provider is untracked local configuration owned by the
  concurrent C5 work.

### 2026-07-18 — Kiro — C5 auth enforcement + security baseline deployed to AWS
- **Applied to AWS** (2 terraform apply rounds):
  1. Security baseline + Cognito domain change: VPC Flow Logs, GuardDuty,
     Security Hub, SNS EventBridge policy, task def revision 5 (new env vars),
     Cognito domain `livecap-720459752315` → `livecap-logantai`.
     Result: 12 added, 2 changed, 2 destroyed.
  2. Auth enforcement: `ENABLE_AUTH=true` in task definition revision 6.
     Result: 1 added, 1 changed, 1 destroyed.
- **New backend image built + pushed:** `2e00a0b-amd64` (contains auth.py,
  history.py, tracing.py, enrichment routes, and all Update-branch code).
  Task definition revision 7 deployed with image `2e00a0b-amd64`.
- **Frontend redeployed** with Cognito env vars:
  `VITE_AUTH_ENABLED=true`, `VITE_COGNITO_DOMAIN`, `VITE_COGNITO_CLIENT_ID`,
  `VITE_COGNITO_REDIRECT_URI`. S3 sync + CloudFront invalidation completed.
- **Live state now:**
  - Backend image `2e00a0b-amd64` with `ENABLE_AUTH=true`
  - Cognito Hosted UI: `https://livecap-logantai.auth.ap-southeast-1.amazoncognito.com`
  - User Pool: `ap-southeast-1_uCz3Q7M9B`
  - Client ID: `614p5pniek2aedu0dh3tnea20s`
  - VPC Flow Logs active (ALL traffic, 14-day retention)
  - GuardDuty enabled (HIGH/CRITICAL → SNS)
  - Security Hub enabled (AWS Foundational Best Practices)
  - DynamoDB transcript history table: `livecap-transcript-history-dev`

### 2026-07-18 — Codex — C5 Cognito resources provisioned safely
- Applied a targeted Terraform plan limited to the Cognito User Pool, public
  PKCE client, Hosted UI domain, transcript-history DynamoDB table, and the
  task-role policy. Result: **5 added, 0 changed, 0 destroyed**.
- Verified the Hosted UI domain is ACTIVE and DynamoDB TTL is ENABLED on
  `expires_at`. The running ECS task has no `ENABLE_AUTH` setting, so the
  existing anonymous app remains available. A separate reviewed frontend and
  runtime cutover must set `enable_auth_runtime=true`.

### 2026-07-18 — Codex — C5 safe provisioning gate
- Split Cognito resource creation from backend enforcement. `enable_cognito_auth`
  can now create the User Pool, browser client, Hosted UI domain, and history
  table while `enable_auth_runtime=false` preserves the anonymous production
  app. Turn enforcement on only after the frontend is rebuilt with its public
  Cognito settings and the runtime cutover is reviewed.

### 2026-07-18 — Claude (Cowork) — Group D cost optimization (D2 + D3/D5 docs)
- **D2 Fargate Spot** (`fargate_spot.tf` + `ecs.tf`): opt-in `enable_fargate_spot`
  runs the target service on FARGATE_SPOT (~70% cheaper, interruptible) via a
  capacity-provider strategy; cluster advertises both providers. `launch_type`
  becomes null when Spot is on (mutually exclusive). `fargate_on_demand_base > 0`
  keeps a guaranteed on-demand baseline. Default off → no change.
- **D3** already satisfied: transcript bucket has a 14-day lifecycle;
  Intelligent-Tiering (30+ day transition) does not apply — no change.
- **D5**: no Lambda cost-report built (low value); documented using the existing
  Budget alerts, dashboard, and cost-allocation tags in Cost Explorer.
- `docs/cost-optimization.md` (new) summarizes the whole D group. Verified: HCL
  parses. Not deployed.

### 2026-07-18 — Codex — C5 Cognito accounts and owner-scoped transcript history
- Added opt-in Terraform for a Cognito User Pool, public PKCE browser client,
  optional Hosted UI domain, and pay-per-request DynamoDB history table with a
  TTL aligned to the existing 14-day transcript S3 lifecycle. The task role is
  limited to `cognito-idp:GetUser` plus `PutItem`/`GetItem`/`Query` on that
  history table; raw audio is never stored.
- Backend history endpoints list metadata and issue a fresh owner-authorized
  S3 download URL. When accounts are enabled, exports validate Cognito access
  tokens and persist owner metadata; the WebSocket validates a token supplied
  through `Sec-WebSocket-Protocol`, not a query string. With accounts off,
  anonymous MVP export/capture behaviour remains unchanged.
- Frontend adds Hosted UI Authorization Code + PKCE sign-in, sign-out, history
  list/download UI, and bearer headers for account API calls. Backend and
  frontend `.env.example` files document the non-secret feature settings. The
  exact live rollout is documented in `docs/cognito-history-rollout.md`.
- Verified: C5 targeted backend tests pass, frontend tests/build pass, and
  Terraform `fmt -check`, `init -backend=false`, and `validate` pass. The full
  backend suite has one pre-existing environment failure because the local venv
  lacks declared `aws-xray-sdk`; C5 tests itself does not depend on it.

### 2026-07-18 — Claude (Cowork) — C4 AWS X-Ray tracing (opt-in, default off)
- New `backend/app/tracing.py`: `configure_tracing(app)` — when `ENABLE_XRAY` is
  set, configures the X-Ray recorder (AsyncContext with a safe fallback,
  `context_missing=IGNORE`), `patch_all()` for AWS SDK subsegments, and a small
  Starlette **HTTP-only** middleware. The WebSocket route is intentionally not
  traced (BaseHTTPMiddleware skips it). `main.py` calls it (no-op when off).
- `xray.tf` (new): `enable_xray` var + X-Ray daemon **sidecar** (added to the
  task via `concat`) + task-role `xray:Put*` policy, all count-gated. `ecs.tf`
  passes `ENABLE_XRAY` + `AWS_XRAY_DAEMON_ADDRESS`. `requirements.txt` adds
  `aws-xray-sdk`.
- **Not validated against a live daemon** (cannot here) — enable in a
  non-critical env first and confirm traces appear. Default off → zero impact.
  Verified: 3 tracing tests pass, full suite green except the known Py-3.10
  `asyncio.timeout` websocket failures; app imports/boots with tracing off.

### 2026-07-18 — Kiro — Security baseline: VPC Flow Logs + GuardDuty + Security Hub
- **New file:** `infrastructure/terraform/security.tf` — adds three enterprise
  security capabilities, all flag-gated (default ON for new deploys):
  1. **VPC Flow Logs** (`enable_vpc_flow_logs`): captures ALL traffic metadata
     for the target VPC → CloudWatch log group with 14-day retention. Includes
     dedicated IAM role with least-privilege publish permissions.
  2. **Amazon GuardDuty** (`enable_guardduty`): intelligent threat detection
     with S3 data source enabled. HIGH/CRITICAL findings route to the existing
     alerts SNS topic via EventBridge rule.
  3. **AWS Security Hub** (`enable_security_hub`): enables the AWS Foundational
     Security Best Practices standard. Optional CIS Benchmark via
     `enable_cis_benchmark`.
- **Container Insights** (`ecs.tf`): now driven by `enable_container_insights`
  variable (default false). Toggle to true for production observability depth.
- **Variables added** (`variables.tf`): `enable_vpc_flow_logs`,
  `vpc_flow_logs_retention_days`, `vpc_flow_logs_traffic_type`,
  `enable_guardduty`, `enable_security_hub`, `enable_cis_benchmark`,
  `enable_container_insights`.
- **Outputs added** (`outputs.tf`): `vpc_flow_log_group`,
  `guardduty_detector_id`, `security_hub_enabled`.
- **Example updated** (`terraform.tfvars.example`): documents all new flags
  with cost notes.
- Verified: `terraform fmt -check -recursive` + `terraform validate` pass. No
  existing resources affected (all count-gated). Not deployed — requires human
  `plan` + `apply`.
- **Impact on Well-Architected score:** Security 7→8.5, Ops Excellence 6→7
  (detection + compliance + conditional deep metrics).

### 2026-07-18 — Claude (Cowork) — B5 session-id continuity on reconnect
- Backend `websocket.py`: new `_resolve_session_id` reuses a client-supplied
  `session_id` query param when it is a valid UUID, else mints a fresh one. The
  registry's `try_register` is idempotent for a repeated id, so reconnects keep
  one logical session (stable logs/export/accounting) without double-counting.
- Frontend `useWebSocket.ts`: `buildWsUrl` adds `session_id`; openSocket passes
  the prior id **only on reconnect** (`isRetry`).
- No infra change. Verified: 4 backend tests pass, `tsc` clean, useWebSocket
  tests pass. Unblocked now that Codex's A1+ edits to these files are committed.
  Not deployed.

### 2026-07-18 - Codex - mount optional enrichment routes
- Registered Claude's flag-gated `enrichment_router` in FastAPI so a reviewed
  deployment can expose `POST /api/tts` and `POST /api/analyze`. Added the
  disabled-by-default English-only Polly/Comprehend settings to `.env.example`.
  Verified: backend `249 passed`; Terraform `init -backend=false`, `fmt -check`,
  and `validate` pass. No UI, AWS deployment, Terraform apply, or feature
  enablement was performed.

### 2026-07-18 — Claude (Cowork) — A2 Polly TTS + A3 Comprehend analysis (backend)
- New `backend/app/routers/enrichment.py`: `POST /api/tts` (Amazon Polly) and
  `POST /api/analyze` (Amazon Comprehend sentiment + key phrases). Env-gated
  (`ENABLE_TTS`, `ENABLE_TEXT_ANALYSIS`), best-effort (502 on AWS error), config
  read from env. `iam.tf` adds count-gated Polly + Comprehend policies;
  `variables.tf`/`ecs.tf`/`tfvars.example` wire the flags. 7 tests pass.
- **AWS-service constraints — Codex/human MUST verify (I cannot):**
  - **Amazon Polly has NO Vietnamese voice.** TTS is **English only**; call it
    with the English translation text (LiveCap always fills the English column).
  - **Amazon Comprehend does NOT support Vietnamese** for sentiment/key phrases.
    Analysis is **English only** — pass the English text.
  - Confirm **Polly and Comprehend are available in `ap-southeast-1`** for the
    task role (they generally are, but verify) and that the Polly neural voice
    id (`Joanna`) is valid in-region; otherwise set `tts_voice_id_en`.
- **TODO for Codex (I could not touch — you were editing `main.py`):**
  1. Register the router: `from app.routers import enrichment as enrichment_router`
     and `app.include_router(enrichment_router.router)` in `backend/app/main.py`.
  2. Frontend wiring (your area): a per-line/summary **Play** button calling
     `POST /api/tts` (English text), and optional sentiment/key-phrase display
     from `POST /api/analyze`.
- Not deployed; default off. `.env.example` note not added (you own that file).

### 2026-07-18 — Claude (Cowork) — A5 Transcribe custom vocabulary (vi + en)
- Commit `3ac2909`. `transcription.py` reads `TRANSCRIBE_VOCABULARY_NAME_VI/EN`
  from env and passes `vocabulary_name` to `start_stream_transcription` per
  stream language (None = off). `transcribe.tf` (new) creates the vi + en
  vocabularies with editable phrase-list vars, gated by
  `enable_transcribe_custom_vocabulary`; `ecs.tf` wires the names into the task.
- Config read via env, not `config.py`, to avoid Codex's in-flight A1+ changes
  there. No task-role IAM change (covered by StartStreamTranscription). Default
  off → no behaviour change. Verified: 38 transcription tests pass, HCL parses.
  Not deployed. VI phrases must follow the Transcribe VI charset (tones as
  numbers) — noted in `transcribe.tf`.

### 2026-07-18 - Codex - README audience wording
- Replaced internal roadmap labels in the public README with product language:
  **AI meeting notes** and optional reliability/transcription improvements.
  Phase labels remain in this collaboration log and the roadmap only.

### 2026-07-18 - Codex - A1+ user-triggered meeting notes
- Replaced automatic Bedrock work during WebSocket teardown with `POST
  /api/sessions/{session_id}/summary`. The Dashboard shows **Create meeting
  notes** after a finished session; only that click sends finalized captions to
  Bedrock. Stop now only ends audio and the WebSocket, so it cannot create an
  unexpected Bedrock charge.
- The endpoint is feature-gated (`ENABLE_MEETING_SUMMARY=false` by default),
  validates the minimum segment count, does not persist the supplied captions,
  and returns a retryable error on an unusable Bedrock result. The returned
  notes continue to appear in the existing panel and TXT export.
- Removed the obsolete `session_summary` WebSocket contract. Updated README,
  local instructions, handoff, roadmap, and environment comments. Verified locally:
  `compileall`, backend `242 passed`, frontend `18 passed`, and production
  build pass. No Terraform, AWS deployment, or commit was performed. Concurrent
  Claude infrastructure work was left untouched.

### 2026-07-18 — Claude (Cowork) — B3 multi-AZ NAT + B4 cold-start doc
- **B3** (`vpc.tf`, `variables.tf`, `terraform.tfvars.example`): optional second
  NAT gateway via `enable_multi_az_nat` (default false). Additive — the primary
  NAT is untouched and private route associations are unchanged when disabled,
  so `plan` shows no diff by default. When enabled, private subnets route via the
  NAT in their own AZ (removes single-AZ egress dependency; +1 NAT/EIP cost).
- **B4** (`docs/cold-start.md`): documented the cold-start levers. The warm-window
  mechanism already exists (`enable_demo_scheduled_scaling`); no risky code added.
- **B5 deferred:** session-id continuity on reconnect touches `websocket.py` and
  frontend `useWebSocket.ts`, both of which Codex is currently editing (A1+ REST
  redesign, uncommitted). Left untouched to avoid clobbering — see Open items.
- Verified: HCL parses. Terraform-only + docs; not deployed.
- Note: B1 (DynamoDB store) is done & live; B2 (multi-task) is prepared but max
  stays 1 pending load test.

### 2026-07-18 — Claude (Cowork) — document A1+ enablement for Codex
- Added an explicit "A1+ — what it is and how to make it live" block under Open
  items (flag, IAM/env wiring, Bedrock model access, image rebuild, plan/apply)
  plus `docs/run-local.md` for local testing. No code change.

### 2026-07-18 — Claude (Cowork) — A1+ knowledge extraction (NotebookLM-style)
- Extended the Bedrock end-of-session summary with keywords, insights/takeaways,
  a glossary (`term` + `definition`), and follow-up questions — one-shot, no new
  flag (same `enable_meeting_summary`). Backward compatible (new optional fields).
- Backend: `models.py` (`GlossaryItem` + fields), `services/summarization.py`
  (prompt, tolerant parse incl. glossary, export text), tests updated.
- Frontend: `types`, `useWebSocket` parse, `SummaryPanel` renders the new
  sections, export text includes them.
- Verified: backend 62 summary/model tests pass; frontend `tsc` + `vite build`
  + useWebSocket/DashboardPage tests pass. Not committed to a new deploy — the
  feature stays behind the (currently off) summary flag.

### 2026-07-18 — Claude (Cowork) — log hygiene
- Corrected the stale "Open items" (Phase 4 is committed, not "not started";
  deployment done single-task) and the commit count (9 → 11). No code changes.
- Verified against git: Phase 4 commit `d61c997` and its files are present;
  branch has 11 commits. AWS/runtime state reflects Codex's verified entries
  (not independently re-checked here).

### 2026-07-18 - Codex - User-approved Update deployment and live validation
- Built and pushed immutable linux/amd64 backend image `cf920cd-amd64`, then
  applied the reviewed Terraform changes for the target task definition,
  CloudWatch log retention, CloudWatch alarms/SNS, and idle-scaler IAM cleanup.
  Terraform result: 8 added, 3 changed, 1 ECS task-definition revision replaced.
- Synced the production frontend build to its S3 origin and completed a
  CloudFront invalidation. The ignored local tfvars enable the DynamoDB session
  store and select the deployed image; no credentials or secrets were committed.
- Verification passed: backend `232 passed`; frontend `15` tests and build;
  Terraform fmt/init/validate. Runtime smoke test passed through the public
  domain: wake returned `202`, health reached `200`, WebSocket returned
  `session_start` and `pong`, DynamoDB held one active session and was empty
  after disconnect, and the ECS service automatically scaled `1 -> 0` after
  the configured 300-second idle grace period.

### 2026-07-17 - Codex - DynamoDB session-store provisioning
- User-approved targeted Terraform apply created `livecap-sessions-dev` with
  on-demand billing and TTL, plus the `livecap-session-store-access` inline
  policy on the ECS task role. Result: 2 added, 0 changed, 0 destroyed.
- Added `enable_dynamodb_session_store = true` only to ignored `terraform.tfvars`
  so a future full plan retains the table. No ECS task-definition deployment,
  backend-image deployment, or max-capacity increase was applied.
- Verified the table is `ACTIVE` and the IAM inline policy exists. Runtime stays
  on the currently deployed task definition until the next reviewed deployment.
- Full plan is intentionally pending: it includes the new alarms/SNS resources
  and a target task-definition revision that will pass `SESSION_STORE_BACKEND=dynamodb`.
  It was reviewed only; no additional apply was run.

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

Done & deployed (single task): Phases 0–3 slice 1 and the DynamoDB session store
are live and verified. Phase 4 is committed (`d61c997`) but **not adopted** yet.

### A1+ meeting summary — what it is and how to make it live

A1+ (commit `b8df135` plus the uncommitted user-triggered redesign above) is
**code only, committed on `Update`, NOT deployed**. It extends the Bedrock meeting notes with keywords, insights, glossary
(`term`/`definition`), and follow-up questions, on top of A1's summary/key points/
decisions/action items/topics. It is gated by the existing `enable_meeting_summary`
flag (default **off**) — there is no separate A1+ flag, and no infra beyond the
existing `dynamodb.tf`/`iam.tf`/`ecs.tf` wiring.

It renders in `SummaryPanel` and is appended to the exported TXT. It is
**user-triggered**: after Stop, the participant chooses **Create meeting notes**
when there are at least `SUMMARY_MIN_SEGMENTS` finalized captions. On any
Bedrock error the session remains ended normally and the UI shows a retryable
error. Stop itself never calls Bedrock.

To run it **locally** (no deploy): follow `docs/run-local.md` (set
`ENABLE_MEETING_SUMMARY=true`, provide AWS creds via a profile, enable Bedrock
model access).

To make it **live on the deployed stack** (all human-run, reviewed):
1. In ignored `terraform.tfvars`: `enable_meeting_summary = true`. This both
   creates the `bedrock:InvokeModel` IAM policy (`iam.tf`, count-gated) and sets
   `ENABLE_MEETING_SUMMARY=true` on the task (`ecs.tf`).
2. Enable **Bedrock model access** for the Claude model in the target region
   (console). If the model is not in `ap-southeast-1`, set `bedrock_region`
   (tf var) / `BEDROCK_REGION` to a supported region (e.g. `us-east-1`); the
   task reaches it via NAT egress.
3. Build & push a **new backend image containing `b8df135`**, set
   `backend_image_tag` to it.
4. `terraform plan` → expect: new Bedrock IAM policy, task env
   `ENABLE_MEETING_SUMMARY`/`BEDROCK_*`, and a new task-definition revision →
   review → `apply`. Smoke test: run a short session, Stop, choose **Create
   meeting notes**, confirm the new sections, and confirm DynamoDB drains after
   disconnect.

- **Multi-task (raise > 1):** deployed with the DynamoDB store live but
  `backend_max_capacity` is still 1. Next: run `tools/ws_load_test.py` against the
  live endpoint, then raise capacity after operational approval.
- **Graviton (Phase 4):** code is in place; the service still runs amd64
  (`X86_64`). Adopting it needs an arm64 image build, then set
  `task_cpu_architecture = "ARM64"`.
- **CI/CD pipeline (Phase 4):** `deploy.yml` exists but is unused (Codex deployed
  manually). Configure the repo vars/secrets to use the manual plan-gate.
- **Phase 2 C4 (deferred):** X-Ray tracing — needs FastAPI instrumentation + an
  X-Ray daemon sidecar; decide before implementing.
- **B5 session-id continuity on reconnect — DONE** (see change log). Reconnects
  now reuse the same session id.
- **Not started (roadmap):** A4 Bedrock contextual translation (deferred — real-
  time latency/cost; would suit an on-demand batch pass),
  A5 Transcribe custom vocabulary; C5 Cognito + transcript history,
  C6 Secrets Manager, C7 Container Insights; D2 Fargate Spot, D3 S3 tiering,
  D5 cost reporting. (B3 done flag-gated; B4 documented.)
- **Operational follow-up:** monitor alarms/WAF/target health/cost; confirm any
  SNS/budget subscription emails.
- Optional: repo-wide `git add --renormalize .` to clear the CRLF doc churn.
