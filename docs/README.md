# LiveCap Documentation

Use this directory for reviewer-facing product, architecture, and operational
evidence. Current deployment facts belong in the as-deployed document;
runbooks describe feature-specific operation.

| File | Purpose |
|---|---|
| [`demo-guide.md`](demo-guide.md) | Three-minute production demonstration and recovery steps |
| [`as-deployed-architecture.md`](as-deployed-architecture.md) | Verified live AWS topology, security boundaries, and runtime request paths |
| [`upgrade-roadmap.md`](upgrade-roadmap.md) | Implemented capability status and next production-oriented work |
| [`shared-rooms-product-direction.md`](shared-rooms-product-direction.md) | Proposed LiveCap Rooms product direction, user problem, rollout gates, and target architecture |
| [`cognito-history-rollout.md`](cognito-history-rollout.md) | Cognito account and transcript-history rollout and rollback notes |
| [`multi-task-runbook.md`](multi-task-runbook.md) | Preconditions and gate for scaling beyond one backend task |
| [`cold-start.md`](cold-start.md) | Scale-to-zero cold-start behavior and mitigations |
| [`cost-optimization.md`](cost-optimization.md) | Cost controls and optional efficiency improvements |
| [`graviton-and-cicd.md`](graviton-and-cicd.md) | Arm64 option and validation-only CI/CD plan gate |
| [`run-local.md`](run-local.md) | Local backend, frontend, and opt-in meeting-notes testing |
| [`frontend-runtime-environments.md`](frontend-runtime-environments.md) | Isolated Stable (`main`) / Preview (`Update`) frontend and backend runtime split |
| [`livecap-target-architecture.png`](livecap-target-architecture.png) | Custom-VPC architecture diagram used for the deployed blue/green cutover |
| [`livecap-shared-rooms-architecture.png`](livecap-shared-rooms-architecture.png) | Proposed shared-room architecture using official AWS Q2 2026 icons; proposed resources are marked explicitly |
| [`livecap-landing.png`](livecap-landing.png) | Production landing-page evidence |
| [`livecap-dashboard.png`](livecap-dashboard.png) | Current production caption-workspace UI |

The as-deployed document is authoritative for the current public request path.
Cross-check current Terraform state and the git history when a feature flag or
runtime image may have changed since the architecture document was last
verified.
