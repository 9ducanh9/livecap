# LiveCap Upgrade Roadmap

This is a living status and prioritization document for LiveCap. Current
deployment facts are in `as-deployed-architecture.md`; current change history
and feature flags are in `../COLLAB_LOG.md`.

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
| AI | Meeting notes with Amazon Bedrock | Implemented, off by default | Runs only after the participant explicitly selects Create meeting notes. Bedrock model access and the flag are human-controlled. |
| AI | Transcribe custom vocabulary | Implemented, off by default | Enable only after vocabulary content is reviewed. |
| AI | Polly, Comprehend, context-aware LLM translation | Planned | Keep the existing Translate path as the low-cost default. |
| Scale | DynamoDB session registry | Live | The shared registry and TTL cleanup remove the former in-process-only dependency. |
| Scale | More than one Fargate task | Prepared, not enabled | Requires the documented load-test and operational gate in `multi-task-runbook.md`. |
| Network | Second NAT Gateway | Implemented, off by default | Available for a higher-availability environment; the deployed MVP uses one NAT Gateway. |
| Availability | Scale-to-zero and reconnect/session resume | Live | Wake `0 -> 1`, five-minute idle scale-down, bounded browser reconnect, and session restoration are available. |
| Operations | CloudWatch alarms, dashboard, and SNS topic | Live | Confirm the subscriber email before treating alerts as a complete notification path. |
| Operations | AWS Budget notification subscriber | Pending human action | The `$50` budget exists; billing data is not real time. |
| Operations | X-Ray tracing | Planned | Keep disabled until the daemon/sidecar and live WebSocket impact are reviewed. |
| Security | Cognito account and transcript history | Live on the target environment | Google OAuth, user metadata in DynamoDB, and private 14-day transcript retention are enabled. |
| Security | Secrets Manager | Planned | Add only when a runtime secret cannot be replaced by IAM roles or public configuration. |
| Cost | Graviton and Fargate Spot | Implemented, off by default | Require an arm64 image and an interruption-tolerance review respectively. |
| Delivery | Validation-only CI/CD plan gate | Implemented | CI tests, builds, scans, and validates; it does not apply infrastructure. |

## Next Production Gates

1. Complete the multi-task load test before increasing `backend_max_capacity`.
2. Confirm SNS and Budget email subscriptions, then test an alert end to end.
3. Decide whether the availability benefit of a second NAT Gateway justifies
   its fixed cost for the production environment.
4. Enable Bedrock only after model access, cost limits, and user-facing consent
   are reviewed.
5. Add X-Ray only with a measured tracing design for the WebSocket path.
6. Inventory remaining legacy EC2, storage, and IAM resources before any
   decommissioning work.

## Operating Principles

- Use small, reviewable changes with focused tests.
- Keep optional features behind explicit feature flags.
- Do not auto-apply Terraform or destroy AWS resources from CI.
- Treat a full Terraform plan as a review gate, especially for active runtime
  resources.
- Prefer immutable ECR image tags and record rollout evidence in
  `COLLAB_LOG.md`.
