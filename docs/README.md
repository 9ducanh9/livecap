# LiveCap Documentation

Use this directory for reviewer-facing product and architecture evidence.

| File | Purpose |
|---|---|
| [`demo-guide.md`](demo-guide.md) | Three-minute production demonstration and recovery steps |
| [`as-deployed-architecture.md`](as-deployed-architecture.md) | Verified live AWS topology, security boundaries, and runtime request paths |
| [`post-v1.5-requirements-design-flow.md`](post-v1.5-requirements-design-flow.md) | Requirements, implementation design, migration history, and verification baseline |
| [`livecap-target-architecture.png`](livecap-target-architecture.png) | Custom-VPC architecture diagram used for the deployed blue/green cutover |
| [`livecap-landing.png`](livecap-landing.png) | Production landing-page evidence |
| [`livecap-dashboard.png`](livecap-dashboard.png) | Current production caption-workspace UI |

The as-deployed document is authoritative for the current public request path.
The post-v1.5 document preserves design decisions and migration history; where
historical target wording differs from the deployed state, use the as-deployed
document and current Terraform as the source of truth.
