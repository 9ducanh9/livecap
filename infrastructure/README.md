# LiveCap Infrastructure

This directory contains the AWS infrastructure definitions and migration notes
for LiveCap. It intentionally distinguishes the environment that is live today
from the private-subnet target architecture that is ready for a reviewed
blue/green migration.

## Source Of Truth

- [`terraform/README.md`](terraform/README.md): current Terraform design,
  variables, cost tradeoffs, and verification workflow.
- [`terraform/IMPORT_PLAN.md`](terraform/IMPORT_PLAN.md): existing-resource
  imports and state-recovery gate.
- [`../docs/post-v1.5-requirements-design-flow.md`](../docs/post-v1.5-requirements-design-flow.md): requirements, runtime flows,
  security controls, and migration decisions.
- [`../docs/livecap-target-architecture.png`](../docs/livecap-target-architecture.png): target architecture diagram.

The files under [`../deploy`](../deploy) and the older
[`DEPLOYMENT_GUIDE.md`](DEPLOYMENT_GUIDE.md) and
[`QUICK_REFERENCE.md`](QUICK_REFERENCE.md) are legacy references. Their
one-shot apply and mutable-tag examples must not be used for the current AWS
environment.

## Live Environment

The submission deployment currently uses:

1. CloudFront serves the React/Vite frontend from a private S3 bucket through
   Origin Access Control.
2. CloudFront routes `/api/*` and `/ws/*` to the existing public ALB.
3. The ALB forwards healthy traffic to one ECS Fargate backend task.
4. The backend streams microphone PCM to Amazon Transcribe, translates
   finalized text with Amazon Translate, and exports transcript TXT files to a
   separate private S3 bucket.
5. ECS and application logs are written to CloudWatch.

The live backend was verified on 2026-07-03 with immutable image tag
`a86fc1e`. Health, WebSocket heartbeat, real Transcribe/Translate output, clean
session shutdown, S3 export, and presigned download all passed production smoke
tests.

The current live environment still uses the pre-migration network path:

- default VPC subnets;
- Fargate task public IP enabled;
- ECS desired count fixed at one;
- immutable ECR Git SHA tags with scan-on-push enabled;
- no deployed wake Lambda;
- no deployed target WAF, dashboard, LiveCap `$50` Budget, NAT Gateway, or
  private-subnet stack.

These facts are documented explicitly so the target architecture is not
misrepresented as already deployed.

## Target Architecture

Terraform defines a parallel target stack in `ap-southeast-1`:

- dedicated VPC with two public and two private subnets across two AZs;
- one NAT Gateway as the accepted cost-sensitive single-AZ tradeoff;
- multi-AZ public ALB and private Fargate task placement with
  `assign_public_ip = false`;
- maximum one backend task while session limits remain process-local;
- ECS scale `0 <-> 1`, CloudFront-authenticated wake Lambda, and five-minute
  idle scale-down;
- CloudFront and ALB WAF Web ACLs in COUNT mode;
- CloudWatch dashboard, 14-day logs, 14-day transcript retention, and a
  configurable monthly AWS Budget;
- immutable ECR Git SHA tags through `backend_image_tag`;
- no raw audio storage.

The migration strategy is **Parallel Stack Migration with Blue/Green-style
Cutover**. The existing ALB/service remains available for rollback until the
target path has passed smoke tests and ownership of legacy resources is
confirmed.

## State And Apply Safety

Do not run a main-stack apply from empty or incomplete state. The existing AWS
resources must first be represented in the reviewed S3 remote state.

Safe validation commands:

```bash
cd infrastructure/terraform
terraform fmt -check
terraform init -backend=false
terraform validate
```

Before any real apply:

1. Confirm the AWS profile and `ap-southeast-1` region.
2. Confirm the remote-state bootstrap bucket and lockfile configuration.
3. Complete and review the imports in `IMPORT_PLAN.md`.
4. Push the backend image under an immutable Git SHA.
5. Set the same SHA in `backend_image_tag`.
6. Review the full Terraform plan, including replacements and destroys.
7. Apply only after explicit human approval.

Never run `terraform destroy`, state migration, or an unreviewed apply as part
of CI. The current GitHub Actions workflow validates Terraform with
`terraform init -backend=false` and does not deploy.

## Cost Notes

ECS scale-to-zero removes idle Fargate compute cost only after the target stack
is deployed. ALB, NAT Gateway, and WAF retain fixed or baseline charges while
provisioned. Transcribe and Translate are usage-based and mainly incur cost
during active capture. Transcript objects and CloudWatch logs use 14-day
retention to limit storage growth.
