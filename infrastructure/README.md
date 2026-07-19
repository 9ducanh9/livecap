# LiveCap Infrastructure

This directory contains the AWS infrastructure definitions and operating notes
for LiveCap's deployed custom-VPC target environment.

## Source Of Truth

- [`terraform/README.md`](terraform/README.md): current Terraform design,
  variables, cost tradeoffs, and verification workflow.
- [`../docs/livecap-target-architecture.png`](../docs/livecap-target-architecture.png): target architecture diagram.
- [`../docs/as-deployed-architecture.md`](../docs/as-deployed-architecture.md):
  verified live resource placement and runtime request paths.

The obsolete manual EC2/ECS templates and one-shot deployment guides were
removed from the submission branch. Historical versions remain available in
Git history; they must not be used for the current AWS environment.

## Live Environment

The deployed environment uses:

1. CloudFront serves the React/Vite frontend from a private S3 bucket through
   Origin Access Control.
2. CloudFront routes `/api/*` and `/ws/*` to the existing public ALB.
3. The ALB forwards healthy traffic to one ECS Fargate backend task.
4. The backend streams microphone PCM to Amazon Transcribe, translates
   finalized text with Amazon Translate, and exports transcript TXT files to a
   separate private S3 bucket.
5. ECS and application logs are written to CloudWatch.

The target architecture is deployed in `ap-southeast-1`:

- dedicated VPC with two public and two private subnets across two AZs;
- one NAT Gateway as the accepted cost-sensitive single-AZ tradeoff;
- multi-AZ public ALB and private Fargate task placement with
  `assign_public_ip = false`;
- maximum one backend task while session limits remain process-local;
- ECS scale `0 <-> 1`, CloudFront-authenticated wake Lambda, and five-minute
  idle scale-down;
- blocking CloudFront and ALB WAF Web ACLs with CloudFront-only ALB ingress;
- CloudWatch dashboard, 14-day logs, 14-day transcript retention, and a
  configurable monthly AWS Budget;
- immutable ECR Git SHA tags through `backend_image_tag`;
- no raw audio storage.

The migration used **Parallel Stack Migration with Blue/Green-style Cutover**.
The legacy ALB/ECS rollback stack was retired after validation. Remaining
legacy resources, if any, require their own inventory and approval before
decommissioning.

## State And Apply Safety

Do not run a main-stack apply from empty or incomplete state. Use the reviewed
S3 remote state and inspect a full plan before approving changes.

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
3. Push the backend image under an immutable Git SHA.
4. Set the same SHA in `backend_image_tag`.
5. Review the full Terraform plan, including replacements and destroys.
6. Apply only after explicit human approval.

Never run `terraform destroy`, state migration, or an unreviewed apply as part
of CI. The current GitHub Actions workflow validates Terraform with
`terraform init -backend=false` and does not deploy.

## Cost Notes

ECS scale-to-zero removes idle Fargate compute cost only after the target stack
is deployed. ALB, NAT Gateway, and WAF retain fixed or baseline charges while
provisioned. Transcribe and Translate are usage-based and mainly incur cost
during active capture. Transcript objects and CloudWatch logs use 14-day
retention to limit storage growth.
