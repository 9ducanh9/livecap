# Aurel trial

Isolated LiveCap backend for a Vercel frontend. This Terraform root only allows
AWS account `050916357263` in Singapore and uses a separate local state. Do not
run it from the old production or benchmark Terraform roots.

One 0.5 vCPU / 1 GiB Fargate task, a TLS ALB, private transcript bucket, Cognito,
usage/history tables and logs. Public task subnets avoid a new NAT gateway;
the task accepts inbound traffic only from the ALB security group. Frontend
origin is `https://livecap-aurel.vercel.app`; backend DNS is
`api-livecap.logantai.com`. ACM and DNS validation are managed separately.

The trial requires login, caps recording at five minutes and concurrency at
two sessions (one per IP). Shared rooms, screen share, billing, meeting notes
and automatic wake/scale-to-zero are disabled in this first deployment.
Set `VITE_BACKEND_WAKE_ENABLED=false` in the frontend build.

Start with `desired_count=0`, push the reviewed image to ECR, then create and
review a fresh saved plan for `desired_count=1`. Keep the image digest and
Terraform state with deployment evidence. Never put AWS credentials into Vite
variables or image layers.

Cleanup: export logs/results and transcript objects before making a fresh
saved destroy plan in this directory. The transcript bucket intentionally
does not force-delete user data. Remove the trial API DNS record and separately
created ACM certificate after AWS cleanup. ALB and public IPv4 remain billable
even when task count is zero. Inactive ECS task definitions and service-linked
roles can remain as non-running metadata.
