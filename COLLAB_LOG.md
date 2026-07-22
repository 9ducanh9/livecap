# Collaboration Log — LiveCap

**Read before starting work. Append after every change.**

## Working agreement

- Active branch: **`Update`** (off `main`). Push → PR to `main`.
- **No auto-deploy from agents.** Agents write code/Terraform and run plan/validate; human runs apply.
- `git add <path>` only (never `git add -A`). LF line endings (`.gitattributes`).
- Backend needs Python 3.11. Frontend: `npm test` + `npm run build`.
- Feature work is flag-gated, defaults OFF.

---

## Current state (2026-07-23)

**Live image:** `90a92c6-amd64` (stable, `ENABLE_AUTH=false`, X-Ray disabled)
**Live domain:** `https://livecap.logantai.com` (anonymous public access restored by Codex 2026-07-21)
**Branch:** `Update` — diverged significantly from main. Many features committed, partially deployed.

### What is live on AWS (infra):
| Resource | State |
|---|---|
| ECS max capacity | 3 tasks, autoscaling on CPU/memory |
| NAT Gateways | 2 (multi-AZ) |
| DynamoDB tables | `sessions-dev`, `transcript-history-dev`, `usage-dev` |
| Cognito User Pool | `ap-southeast-1_uCz3Q7M9B`, domain `livecap`, Google OAuth enabled |
| VPC Flow Logs | Active |
| GuardDuty | Active |
| Security Hub | Active (Foundational Best Practices) |
| CloudWatch alarms → SNS | Active |
| Container Insights | Enabled |
| Transcribe vocabularies | `livecap-en-dev`, `livecap-vi-dev` READY |
| Stripe secrets | In Secrets Manager (test mode keys) |
| Stripe billing TF | Deployed — endpoints available when `ENABLE_AUTH=true` |

### What is in code but NOT deployed (needs new image + apply):
- `ENABLE_AUTH=true` — Codex restored anonymous mode; re-enable needs new image
- X-Ray tracing — image `8364911-amd64` crashed (uvloop incompatibility); needs fix before deploying
- Usage quota enforcement in WebSocket flow — scaffolded but not wired into `websocket.py`
- Stripe billing endpoints — **live and verified** (image `041a699-amd64`, auth enabled). Backend side works end-to-end; frontend checkout UI still needs a rebuild+redeploy (see below).

### Feature flags (current tfvars state):
| Flag | Value |
|---|---|
| `enable_cognito_auth` | true |
| `enable_auth_runtime` | true (image `041a699-amd64` has `ENABLE_AUTH=true` — verified live) |
| `enable_multi_az_nat` | true |
| `enable_meeting_summary` | true |
| `enable_xray` | true (in TF, but broken in last image) |
| `enable_tts`, `enable_text_analysis` | true |
| `enable_usage_quota` | true |
| `enable_stripe_billing` | true |
| `backend_max_capacity` | 3 |

### Known issues / pending actions:
1. ~~**uvloop crash**~~ — fixed, `041a699-amd64` deployed and healthy (see change log).
2. ~~**ENABLE_AUTH=false**~~ — re-enabled, verified live (see change log).
2a. **Frontend Stripe checkout UI not deployed** — the live frontend bundle (`index-c_BBj6Q8.js`) predates the `UsagePanel.tsx` tier-chooser code (commit `7d84056`). Confirmed via runtime DOM check: only a static "Upgrade" button exists, no "Pro/Business" buttons, no `/api/billing/*` calls fire on click. Needs `npm run build` + `aws s3 sync` + CloudFront invalidation from current `Update` HEAD. Commands given to the user; not yet run as of this entry.
3. **Bedrock model access** — must be enabled in AWS Console (us-east-1) before meeting notes work in production.
4. **Quota not enforced** in WebSocket — `increment_session`/`check_quota` not wired into `websocket.py`.
5. **`frontend/.env.production` is gitignored** — not in git history. Current Cognito domain: `https://livecap.auth.ap-southeast-1.amazoncognito.com`.

---

## Change log (newest first)

### 2026-07-23 — Kiro — Quota enforcement wired + frontend redeploy (96e06aa-amd64)
- **Quota enforcement wired** into `websocket.py`:
  - Pre-session: `check_quota()` — rejects with `QUOTA_EXCEEDED` if monthly limit exceeded
  - Post-accept: `increment_session()` — records new session
  - Post-teardown: `add_minutes()` — records elapsed minutes (fail open)
- `QUOTA_EXCEEDED` added to ErrorCode enum. 23 websocket tests pass.
- Built & pushed `96e06aa-amd64`, deployed via Terraform. Service healthy.
- **Frontend redeployed** (npm build → S3 sync → CloudFront invalidation) — fixes
  Claude's finding that the Upgrade button had no tier-chooser/billing integration.
- Still cosmetic-only: `illustrations/` PNGs missing (panel falls back to icon).

### 2026-07-23 — Claude (Cowork) — E2E test of login → session → usage → billing on production

Full manual test against `https://livecap.logantai.com` after auth was re-enabled and
`041a699-amd64` deployed (see entries below). Drove a real browser via Claude-in-Chrome;
the user performed sign-in themselves (Claude does not handle credentials).

**Passed:**
- Cognito sign-in (Hosted UI) completes and lands on `/app`.
- `GET /api/usage` correctly requires auth now (`401 Sign in is required...` with no
  token, vs the old anonymous `200 {tier: unlimited}` response) — confirms
  `ENABLE_AUTH=true` took effect.
- `UsagePanel` renders real data: `Free` tier, `Sessions 0/3`, `Minutes 0/45`, `Max 15
  min per session`.
- `TranscriptHistoryPanel` loads cleanly (`No transcripts yet`) — no more `503`s.
- Live session: `Start session` → `WAKING` → `ACTIVE`/`LIVE`, WebSocket connects, real
  Vietnamese/English captions stream in (`Đang lắng nghe...` / `Waiting for speech...`).
  `Stop session` ends cleanly.

**Failed — needs a frontend redeploy:**
- Clicking `Upgrade` does nothing observable. Root cause confirmed via
  `document.querySelectorAll('button')` in the live page: only a static `Upgrade`
  button exists in the DOM. No `Pro — $10/mo` / `Business — $30/mo` / `Manage
  subscription` buttons, and no `/api/billing/*` network call ever fires. The deployed
  bundle (`index-c_BBj6Q8.js`) predates the `UsagePanel.tsx` tier-chooser code from
  commit `7d84056` — same class of bug as the earlier `.env.production` domain drift:
  a manual frontend deploy step was missed after the code merged to `Update`.
- Gave the user the fix (not yet run as of this entry):
  ```powershell
  cd infrastructure/terraform
  $bucket = terraform output -raw frontend_bucket_name
  $distId = terraform output -raw cloudfront_distribution_id
  cd ../../frontend
  npm run build
  aws s3 sync dist/ "s3://$bucket/" --delete
  aws cloudfront create-invalidation --distribution-id $distId --paths "/*"
  ```
- Stripe Checkout itself (page render, test-card flow, webhook → tier update) is
  **still unverified** — blocked on the frontend redeploy above. Next session should
  pick up from there: rebuild, then Upgrade → Pro → complete Checkout with Stripe test
  card `4242 4242 4242 4242` (safe, Stripe is in test mode per Kiro's entry below), then
  confirm `UsagePanel` flips to `Pro` after the webhook fires.

**Aside:** added `run-backend.bat` / `run-frontend.bat` launcher scripts at the repo
root (untracked, no secrets) to make local dev testing repeatable by double-click
instead of typing into a terminal. An earlier local-only test run hit a transient
backend crash (`503` on `/api/usage` and `/api/transcripts`, cause not isolated — team
member's own AWS credentials/DynamoDB reachability is the top suspect); abandoned in
favor of testing directly against the deployed dev environment instead, which is why
this entry's results are against production, not localhost.

### 2026-07-23 — Kiro — Fix uvloop crash + deploy full-feature image 041a699-amd64
- **Root cause:** `AsyncContext()` in `tracing.py` called `loop.set_task_factory()` which uvloop rejects.
- **Fix:** removed `AsyncContext` import and usage. Use default threading.local context instead — correct for HTTP tracing with uvicorn+uvloop.
- Built and pushed `041a699-amd64`. Applied via Terraform with `enable_xray=true`.
- Verified: service healthy at `https://livecap.logantai.com/api/health` (status: healthy, version: 1.0.0).
- **This image contains:** usage quota, billing router, Stripe, auth, history, TTS, Comprehend, meeting notes, custom vocabulary, X-Ray (fixed).

### 2026-07-23 — Kiro — Re-enable ENABLE_AUTH=true on stable image
- Applied Terraform with `backend_image_tag=90a92c6-amd64` (stable, X-Ray disabled) + `enable_auth_runtime=true` + `enable_xray=false`.
- Result: 1 added, 1 changed, 2 destroyed. New task definition deployed.
- Verified: service stable, wake → healthy, `https://livecap.logantai.com/api/health` returns 200.
- **Auth is now enforced** on production. Billing + quota endpoints active.
- Note: image `90a92c6-amd64` does NOT contain usage_quota.py, quota router, billing router (those are in `8364911-amd64` which crashed). New stable image needed to get those features.

### 2026-07-23 — Kiro — Stripe billing applied to AWS (test mode)
- `terraform apply` with `enable_stripe_billing=true` and Stripe test credentials.
- Created: 2 Secrets Manager secrets (sk + whsec), IAM policy (execution role → GetSecretValue), new task def revision.
- Stripe config: Pro `price_1TvzYjIbuCi99Y2WtYIbF2p5`, Business `price_1TvzXSIbuCi99Y2W6Pcz05EF`, webhook `https://livecap.logantai.com/api/billing/webhook`.
- Billing endpoints not yet functional (blocked by ENABLE_AUTH=false + uvloop crash in latest image).

### 2026-07-21 — Codex — Restored anonymous stable service
- Registered task def revision 16 with `ENABLE_AUTH=false` from stable revision 15.
- Verified: health 200, anonymous WebSocket works. Auth disabled until preview/stable split resolved.

### 2026-07-21 — Codex — Restored CloudFront after uvloop crash
- Image `8364911-amd64` (X-Ray enabled) crashed at startup — uvloop `task_factory()` incompatibility.
- Rolled back to `90a92c6-amd64` (revision 15, X-Ray off). Health restored.

### 2026-07-20 — Codex — Fixed Google OAuth PKCE + Cognito scope
- Added `aws.cognito.signin.user.admin` scope to Cognito client and frontend PKCE.
- Google sign-in now completes full flow; transcript history API returns 200.

### 2026-07-19 — Kiro/Claude/Codex — Feature rollout batch
- Multi-task (max=3), usage quota DynamoDB table, UsagePanel frontend, Stripe billing code (Claude), all feature flags enabled on infra, backend image `8364911-amd64` built (later crashed, rolled back), as-deployed-architecture.md updated.

### 2026-07-18 — Kiro/Claude/Codex — Security + Auth baseline
- VPC Flow Logs, GuardDuty, Security Hub deployed. Cognito + Google OAuth live. Custom login form (React, no Hosted UI redirect). Multi-AZ NAT. All AI/ML flags enabled. Image `2e00a0b-amd64` → later superseded.

### (baseline) — main @ b1347f7
- v1.5.2: real-time VI/EN captions, ECS Fargate, CloudFront/WAF, Transcribe/Translate, scale-to-zero.
