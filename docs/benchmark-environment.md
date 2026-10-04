# Isolated benchmark environment

This document describes the isolated AWS environment used for the recorded-audio
benchmark. The measured results, sample sizes, task restarts and cleanup outcome
are in [the benchmark report](benchmark-phase5-results.md). Infrastructure plans
and offline tests are not performance measurements.

## Isolation

The dedicated Terraform root is `infrastructure/benchmark`. It uses a separate
`livecap/benchmark/terraform.tfstate` key and the default workspace. Production
state, listeners, application data and identities must not be mutated by this root.

The request path is:

```text
Allowed client -> CloudFront + edge WAF -> benchmark origin hostname
               -> HTTPS ALB + regional WAF -> private ECS Fargate task
               -> Transcribe / Translate / isolated application stores
```

| Resource | Benchmark boundary |
|---|---|
| VPC, public/private subnets, NAT and routing | Existing network reused read-only; no managed network resources or route changes |
| Terraform state bucket | Existing bucket reused with an independent state key and lockfile; never delete the shared bucket |
| ALB, listener, target group and security groups | Dedicated benchmark resources |
| CloudFront, origin certificate and WAF | Dedicated distribution, certificate, ACLs and client allowlists |
| ECS and IAM | Dedicated cluster, service, task definition and task/execution roles |
| Cognito | Dedicated pool, app client and non-admin test identities |
| DynamoDB | Separate session registry, usage, history, room and audit tables |
| S3 and ECR | Dedicated transcript bucket and immutable image repository |
| CloudWatch | Dedicated log group; Uvicorn access logs disabled to avoid peer-IP records |
| Optional services | Rooms/IVS, billing, meeting summary, TTS and text analysis disabled for this scenario |

This isolates application state, not the AWS account or network. Shared NAT,
service quotas, account API limits and competing workloads can still affect a run.

## Runtime and admission

The warm scenario uses one Linux X86_64 Fargate task with 512 CPU units and
1024 MiB memory. Desired/min/max capacity is 1/1/1 during measurement. Deployments
can temporarily create a second task; measurements must start after readiness
and deployment stability have been verified.

Configured admission limits are `MAX_CONCURRENT_SESSIONS=4` and
`MAX_SESSIONS_PER_IP=4`. These are limits, not demonstrated sustained capacity.
Cognito authentication and the DynamoDB session registry remain enabled.

Normal users have five session starts per week in Vietnam time. Admission
reserves usage quota; arrange enough isolated non-admin identities and preserve
usage evidence. Do not reset production quota or use admin bypass as the baseline.
Check quota error telemetry because a fail-open quota lookup invalidates the run.

Dual-language transcription opens two provider streams per session. Four dual
sessions can therefore require eight concurrent Transcribe streams. Verify
current account limits and competing usage before running; configured concurrency
is not a reservation of provider capacity.

## Preparation and measurement

1. Review fixed and variable costs and set a teardown deadline. Budget alerts
   are delayed notifications, not enforced spending caps.
2. Use ignored local `benchmark.tfvars.json` and `backend.hcl` files for real
   account, backend, recipient and client allowlist settings. Never publish real
   tokens, origin secrets, private IP allowlists or saved Terraform plans.
3. Review the dedicated ECR/certificate bootstrap plan. Verify certificate DNS
   ownership, the issued certificate, image source SHA, platform and image digest.
4. Review a fresh full plan with `tools/plan_benchmark.ps1` and the isolation
   checks in `tools/benchmark_preflight.py`. Old plan counts do not authorize a
   later plan with different inputs.
5. Verify the new benchmark origin CNAME points to the dedicated ALB. Confirm
   both WAF allowlists, Cognito issuer, non-admin identities and notification
   subscriptions before an explicitly authorized smoke test.
6. Complete smoke verification before load. Use real attributable speech,
   client monotonic timings and backend structured events. Preserve all attempts,
   errors and missing samples; never substitute mock output for measured results.
7. Use the [harness definitions](benchmark-harness.md) and
   [backend event reference](backend-pipeline-instrumentation.md) when aggregating.
   A handshake, health response or backend send is not proof of session success.

Run identifiers correlate client evidence with backend events. Export actual
CloudWatch logs and ECS CPU/memory bins. CloudWatch periods include neighboring
activity; backend translation durations include SDK/network and executor work.
WAF request counts measure HTTP requests and handshakes, not WebSocket messages.

Cold-start measurements require a separately authorized scale-to-zero scenario
with control-plane and readiness timestamps. Do not infer cold-start duration
from a warm caption test or from a health response alone.

## Cost and teardown

The dedicated ALB, its public IPv4 addresses and WAF retain charges even while
ECS is at zero. Provider usage, NAT processing, logs, storage and request charges
are additional. Check current [Fargate](https://aws.amazon.com/fargate/pricing/),
[ALB](https://aws.amazon.com/elasticloadbalancing/pricing/),
[VPC](https://aws.amazon.com/vpc/pricing/) and [WAF](https://aws.amazon.com/waf/pricing/)
prices; a price model is not an actual bill or a performance result.

After measurement, export logs, metrics, results, image provenance and Terraform
state before deleting any benchmark data. Scale ECS to zero while waiting for
cleanup. Review a fresh saved destroy plan containing benchmark resources only.
Empty the dedicated S3/ECR resources only after verifying their exports; non-empty
stores deliberately refuse deletion.

Remove benchmark DNS records, check for orphan resources, and preserve the
shared network, production resources and state bucket. A successful Terraform
destroy does not by itself prove DNS cleanup, complete billing settlement or an
immediate zero bill.
