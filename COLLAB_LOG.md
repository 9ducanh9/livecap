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
- Stripe billing endpoints — deployed in TF, code in image `8364911-amd64` (crashed), need new stable image

### Feature flags (current tfvars state):
| Flag | Value |
|---|---|
| `enable_cognito_auth` | true |
| `enable_auth_runtime` | true (but image overrides with ENABLE_AUTH=false) |
| `enable_multi_az_nat` | true |
| `enable_meeting_summary` | true |
| `enable_xray` | true (in TF, but broken in last image) |
| `enable_tts`, `enable_text_analysis` | true |
| `enable_usage_quota` | true |
| `enable_stripe_billing` | true |
| `backend_max_capacity` | 3 |

### Known issues / pending actions:
1. **uvloop crash** — image `8364911-amd64` fails at startup (uvloop `task_factory()` incompatibility with X-Ray). Fix before next image build.
2. **ENABLE_AUTH=false** on running service — billing and quota endpoints need auth. Re-enable after fixing uvloop.
3. **Bedrock model access** — must be enabled in AWS Console (us-east-1) before meeting notes work in production.
4. **Quota not enforced** in WebSocket — `increment_session`/`check_quota` not wired into `websocket.py`.
5. **`frontend/.env.production` is gitignored** — not in git history. Current Cognito domain: `https://livecap.auth.ap-southeast-1.amazoncognito.com`.

---

## Change log (newest first)

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
