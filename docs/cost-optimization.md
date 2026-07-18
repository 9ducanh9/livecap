# Cost optimization (Group D)

Status of the D-group levers and how to use them. Everything is opt-in and
default-off; the deployed baseline is unchanged until enabled.

## D1 — Graviton (arm64) — available

`task_cpu_architecture = "ARM64"` runs the backend on Graviton (~20% cheaper
compute). Must be paired with an arm64 image. See `docs/graviton-and-cicd.md`.

## D2 — Fargate Spot — available (`fargate_spot.tf`)

`enable_fargate_spot = true` runs the target service on FARGATE_SPOT (up to ~70%
cheaper) via a capacity-provider strategy.

- **Trade-off:** Spot tasks can be reclaimed with a 2-minute warning, which drops
  an in-flight WebSocket session. Best for dev/demo.
- To keep a guaranteed on-demand baseline while bursting on Spot, set
  `fargate_on_demand_base > 0`.
- Requires the plan to associate FARGATE + FARGATE_SPOT with the cluster (done in
  `fargate_spot.tf`) before the service strategy applies; review the plan.

```hcl
enable_fargate_spot    = true
fargate_spot_weight    = 1
fargate_on_demand_base = 0   # 1 keeps one on-demand task, extra on Spot
```

## D3 — S3 lifecycle / tiering — already satisfied

The transcript bucket already has a **14-day lifecycle expiration**
(`aws_s3_bucket_lifecycle_configuration.transcript_retention`), plus
noncurrent-version expiration. S3 Intelligent-Tiering only transitions objects
after 30+ days, so it does **not** apply to 14-day transcripts — adding it would
have no effect. No change needed. If retention is ever extended well beyond 30
days, add an `aws_s3_bucket_intelligent_tiering_configuration` then.

## D4 — CI/CD plan gate — available

`.github/workflows/deploy.yml` builds/pushes an image and produces a reviewed
`terraform plan` (no apply from CI). See `docs/graviton-and-cicd.md`.

## D5 — Cost visibility — use existing tools

A full automated cost report (Lambda + Cost Explorer + email) is intentionally
not built — low value for this scale. Use what already exists:

- **AWS Budget** (`monthly_budget_limit_usd`, default $50) with FORECASTED 80%
  and ACTUAL 100% alerts once `budget_notification_email` is set.
- **CloudWatch dashboard** for ECS/ALB usage.
- **Cost allocation tags:** all resources carry `var.tags`
  (Project/Environment). Activate those tag keys once in
  **Billing → Cost allocation tags**, then filter/group by them in **Cost
  Explorer** for per-project/-environment spend.

## Quick wins ranking

1. Scale-to-zero (already on) — biggest idle saving.
2. Graviton (D1) — permanent ~20% compute cut, low risk.
3. Fargate Spot (D2) — largest cut for dev/demo, accepts interruption.
