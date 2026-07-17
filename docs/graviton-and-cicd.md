# Graviton (arm64) + CI/CD plan gate (Phase 4)

Two cost/operational improvements: run the backend on Graviton (arm64, ~20%
cheaper compute) and add a plan-gated deploy pipeline. Both are opt-in and do
not change current behaviour until adopted.

## Graviton (arm64)

`task_cpu_architecture` (default `X86_64`) drives the task definition's
`runtime_platform`. The pushed image architecture must match this value, so
switch them together.

Steps:

1. Build and push an arm64 image (immutable tag):

   ```bash
   docker buildx build --platform linux/arm64 \
     -t <account>.dkr.ecr.<region>.amazonaws.com/<repo>:<sha>-arm64 \
     --push backend
   ```

   Note: `backend/Dockerfile` pins the base image by digest. The official
   `python:3.11-slim-bookworm` publishes a multi-arch manifest list; confirm the
   pinned digest is the manifest-list digest (so buildx resolves arm64). If it is
   a single-arch (amd64) digest, update it to the manifest-list digest first.

2. Set in `terraform.tfvars`:

   ```hcl
   task_cpu_architecture = "ARM64"
   backend_image_tag     = "<sha>-arm64"
   ```

3. `terraform plan` → review (expect a new task definition revision) → `apply`.

Rollback: set `task_cpu_architecture = "X86_64"` and point `backend_image_tag`
back to an amd64 image, then `apply`.

## CI/CD plan gate — `.github/workflows/deploy.yml`

Manual-dispatch pipeline that builds/pushes an architecture-specific image and
produces a reviewed `terraform plan` as an artifact. **It never runs
`terraform apply`** — a human applies from a trusted environment. This keeps the
project rule "no apply/destroy from CI" intact while automating the slow, safe
parts.

Configure once (Settings → Actions):

- Variables: `AWS_REGION`, `AWS_DEPLOY_ROLE_ARN` (GitHub OIDC role, least
  privilege), `ECR_REPOSITORY`.
- Secrets: `TF_BACKEND_HCL` (contents of `backend.hcl`), `TF_VARS` (a
  `terraform.tfvars` for planning).

The OIDC role should allow ECR push and the read/plan actions Terraform needs;
it should **not** grant apply-level permissions used from CI. Run it from the
Actions tab, choose the architecture, then download the `terraform-plan`
artifact and apply it locally after review.
