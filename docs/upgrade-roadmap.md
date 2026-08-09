# LiveCap Upgrade Roadmap

This is a living status and prioritization document for LiveCap. Current
deployment facts are in `as-deployed-architecture.md`; the Capability Status
table below reflects current feature-flag state.

## Current Baseline

The deployed target environment uses a custom VPC in `ap-southeast-1` with two
public and two private subnets across two Availability Zones. CloudFront and
two blocking WAF layers protect the browser path. An internet-facing ALB routes
to private Fargate tasks, and the backend uses Amazon Transcribe, Amazon
Translate, private S3 transcript export, and CloudWatch observability.

The service deliberately scales between zero and one task. This controls idle
cost but means the first session after idling has a cold start and a failed task
interrupts the active WebSocket session. One NAT Gateway remains a deliberate
cost versus availability tradeoff.

## Capability Status

| Area | Item | Status | Notes |
|---|---|---|---|
| AI | Meeting notes with DeepSeek | Implemented, off by default | Runs only after the participant explicitly selects Create meeting notes. Needs both `ENABLE_MEETING_SUMMARY=true` and a real `DEEPSEEK_API_KEY`. Switched from Amazon Bedrock 2026-08-06 — every Anthropic model quota in this account's Bedrock region was 0 (unapproved AWS quota, confirmed via a real InvokeModel call), so it never worked. |
| AI | Transcribe custom vocabulary | Implemented, off by default | Enable only after vocabulary content is reviewed. |
| AI | Polly, Comprehend, context-aware LLM translation | Planned | Keep the existing Translate path as the low-cost default. |
| Scale | DynamoDB session registry | Live | The shared registry and TTL cleanup remove the former in-process-only dependency. |
| Scale | More than one Fargate task | Prepared, not enabled | Requires the documented load-test and operational gate in `multi-task-runbook.md`. |
| Network | Second NAT Gateway | Live | `enable_multi_az_nat=true`; two NAT Gateways, one per AZ — confirmed live 2026-07-24. |
| Availability | Scale-to-zero and reconnect/session resume | Live | Wake `0 -> 1`, five-minute idle scale-down, bounded browser reconnect, and session restoration are available. Verified live 2026-07-24 (503 during cold start, healthy ~60-70s after wake). |
| Operations | CloudWatch alarms, dashboard, and SNS topic | Live | Confirm the subscriber email before treating alerts as a complete notification path. |
| Operations | AWS Budget notification subscriber | Pending human action | The `$50` budget exists; billing data is not real time. |
| Operations | X-Ray tracing | Live | `enable_xray=true`; the earlier uvloop `task_factory()` crash was fixed (removed `AsyncContext` from `tracing.py`). |
| Security | Cognito account and transcript history | Live, enforced by default | Google OAuth, user metadata in DynamoDB, and private 14-day transcript retention are enabled. `ENABLE_AUTH=true` by default now, not opt-in. |
| Security | Secrets Manager | Live | Stripe secret key + webhook secret; injected into the task via the execution role, not plaintext env vars. |
| Billing | Stripe subscription billing (Pro/Business) | Live, test mode | Checkout + Customer Portal + webhook; promo codes enabled on Checkout. Price IDs and secrets confirmed live 2026-07-24. |
| Billing | Per-user usage quotas | Live | Free/Pro/Business tiers enforced in the WebSocket session flow; an `unlimited` tier exists for manually-assigned internal/admin accounts (no Stripe price). |
| Admin | Admin dashboard (`/admin`) | Live, phased | Multi-page: user management (search/filter/mutate + audit log), usage analytics, revenue, system health. Gated on Cognito group `admin`. |
| Cost | Graviton and Fargate Spot | Implemented, off by default | Require an arm64 image and an interruption-tolerance review respectively. |
| Delivery | Validation-only CI/CD plan gate | Implemented | CI tests, builds, scans, and validates; it does not apply infrastructure. |

## Next Production Gates

1. Complete the multi-task load test before increasing `backend_max_capacity`
   above 1 (the DynamoDB session-registry precondition is already live).
2. Confirm SNS and Budget email subscriptions, then test an alert end to end.
3. Add frontend test coverage for the admin panel before relying on it in
   production — `AdminUsersPage`, `AdminUsagePage`, `AdminRevenuePage`,
   `AdminSystemPage`, etc. currently have none (backend has property + unit
   tests; the audit table and IAM are already live and correct).
4. Set a real `DEEPSEEK_API_KEY` (Secrets Manager, via `terraform.tfvars`)
   only after cost limits and user-facing consent are reviewed.
5. Move Stripe billing from test mode to live mode once checkout, webhook, and
   tier-sync are fully verified end to end (checkout → webhook → `UsagePanel`
   reflecting the new tier).
6. Inventory remaining legacy EC2, storage, and IAM resources before any
   decommissioning work.

## Operating Principles

- Use small, reviewable changes with focused tests.
- Keep optional features behind explicit feature flags.
- Do not auto-apply Terraform or destroy AWS resources from CI.
- Treat a full Terraform plan as a review gate, especially for active runtime
  resources.
- Prefer immutable ECR image tags and record rollout evidence in commit
  messages and the release history.
