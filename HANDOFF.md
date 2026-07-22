# LiveCap Operational Handoff

This is the concise operating handoff for the `Update` integration branch.
Read `COLLAB_LOG.md` first for the newest change, feature-flag state, and any
uncommitted work. It is the shared change log; do not duplicate its history
here.

## Guardrails

- Work on `Update` and stage only files you changed. Do not use `git add -A`.
- Never apply, destroy, or migrate Terraform state from CI or an agent session.
- Keep feature flags off until their rollout gate is approved.
- Use the reviewed remote state, untracked `backend.hcl`, and untracked
  `terraform.tfvars`. Never commit secrets, OAuth client secrets, or origin
  verification values.
- Run a full reviewed Terraform plan before any AWS change.

## Current Runtime

- The deployed target path is CloudFront -> public ALB -> private ECS Fargate
  in the custom two-AZ VPC.
- ECS runs between zero and one task. The wake endpoint scales the service to
  one, and the idle scaler returns it to zero after 300 seconds with no active
  sessions.
- CloudFront and ALB WAF Web ACLs use blocking managed and rate-based rules.
- DynamoDB-backed session storage is enabled on the target task; do not raise
  `backend_max_capacity` above one until the multi-task load-test gate passes.
- Cognito sign-in and user transcript history are enabled on the custom-domain
  target environment. Google OAuth callback and logout URLs must match the
  active frontend hostname exactly.
- Meeting notes, custom vocabulary, Polly, Comprehend, X-Ray, Graviton,
  Fargate Spot, and multi-AZ NAT remain opt-in features. Check `COLLAB_LOG.md`
  before changing any flag.

## Verification Before A Runtime Change

```powershell
python -m compileall backend/app
python -m pytest backend/tests
npm --prefix frontend test -- --run
npm --prefix frontend run build
terraform -chdir=infrastructure/terraform fmt -check
terraform -chdir=infrastructure/terraform init -backend=false
terraform -chdir=infrastructure/terraform validate
gitleaks detect --source . --redact
```

Use the project Python 3.11 environment for backend tests. If an optional
observability package is absent locally, record the exact failure in
`COLLAB_LOG.md`; do not treat it as a product regression without confirming the
dependency contract.

## Deployment Gate

1. Confirm the target branch, intended frontend environment, backend image tag,
   and AWS profile/region.
2. Build and push a backend image with an immutable Git-SHA-derived tag only
   when backend code changed.
3. Update untracked Terraform inputs and review `terraform plan` in full.
4. Stop when the plan replaces or destroys an active runtime resource unless a
   separately approved migration explicitly expects it.
5. After a human-approved apply, smoke-test health, wake, WebSocket,
   Transcribe/Translate, export, and the authenticated history path when auth
   is enabled.
6. Record the result, image tag, and any pending human action in
   `COLLAB_LOG.md`.

## Required Human Actions

- Confirm any SNS and AWS Budget subscription emails.
- Enable Bedrock model access in the intended region before enabling meeting
  notes.
- Configure GitHub Actions repository variables and secrets before using the
  manual deployment workflow.
- Review remaining legacy EC2, storage, and IAM resources independently before
  deleting them.
- Stripe subscription billing (commit `7d84056`, off by default): set
  `enable_stripe_billing`/`stripe_secret_key`/`stripe_webhook_secret`/
  `stripe_price_id_pro`/`stripe_price_id_business` in a local `.tfvars`,
  `terraform apply`, register a Stripe webhook endpoint at
  `/api/billing/webhook`, and build+push a new backend image before
  enabling. Two live-mode Stripe Products/Prices already exist on the
  connected account (LiveCap Pro $10/mo, LiveCap Business $30/mo) — details
  and price IDs in `COLLAB_LOG.md`.
- Admin dashboard (`infrastructure/terraform/admin.tf`, gated on the existing
  `enable_cognito_auth`): after `terraform apply`, add at least one admin with
  `aws cognito-idp admin-add-user-to-group --user-pool-id <id> --username
  <email> --group-name admin`, then sign in and visit `/admin`. No one is a
  member yet, so the dashboard is unreachable (403) until this is done.

## Supporting Documents

- `docs/as-deployed-architecture.md`: current public request path and security
  boundaries.
- `docs/upgrade-roadmap.md`: completed capabilities and remaining work.
- `docs/multi-task-runbook.md`: explicit gate for scaling beyond one task.
- `docs/cognito-history-rollout.md`: account/history rollout and rollback
  guidance.
- `infrastructure/terraform/README.md`: Terraform inputs and safe validation.
