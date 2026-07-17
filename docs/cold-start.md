# Cold start — causes and mitigations (B4)

Because the backend scales to zero when idle (to save cost), the first
**Start session** after an idle period waits ~30–60s while Fargate provisions a
task and it passes health checks. `/api/health` may return 503 during that
window; the UI shows "Starting backend" and retries. This is the intended
cost/latency trade-off, not a bug.

There is no single switch that removes the cold start without giving up
scale-to-zero. The levers below trade cost for latency; pick per environment.

## What actually takes the time

1. Wake: the wake Lambda sets ECS desired count `0 → 1` (fast).
2. Fargate provisioning: pull the image and start the task (the bulk of the
   time; broadly fixed).
3. Health checks: the container + ALB target must pass before traffic routes.

## Levers

- **Keep one task warm during known-busy hours (recommended).** The scheduled
  scaling already in `ecs.tf` (`enable_demo_scheduled_scaling`) sets the service
  to min/max 1 on `demo_scale_up_schedule_expression` and back to 0 on
  `demo_scale_down_schedule_expression` (in `demo_scaling_timezone`). Point the
  up/down crons at your business hours to avoid cold starts during them while
  still scaling to zero off-hours. Cost: one task running for the warm window.

- **Smaller / faster-starting image.** Adopting Graviton (see
  `docs/graviton-and-cicd.md`) plus keeping the image slim shaves provisioning
  time. Low, permanent gain.

- **Do not disable scale-to-zero unless you accept 24/7 task cost.** Setting
  `backend_min_capacity > 0` removes cold starts entirely but keeps a task (and
  its bill) running continuously.

## What is already in place

- Wake-on-demand (Lambda) so the first request triggers the scale-up.
- The frontend already handles the window gracefully: it polls health, shows
  "Starting backend", and retries for up to 120s, so users are not shown an
  error during a normal cold start.

## Recommendation

For a demo/MVP, keep scale-to-zero and, if cold starts during a session or demo
are a concern, enable scheduled scaling for that window. Reserve
`backend_min_capacity > 0` for a production tier that cannot tolerate the wait.
