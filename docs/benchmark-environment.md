# Isolated benchmark environment — Phase 4A design

Status: **P4A design prepared; P4B entry is assessed separately from service deployment**.
See `benchmark-phase4b-entry.md` for ordered bootstrap/service/smoke gates.
This is infrastructure evidence, not performance evidence. No image was deployed,
Cognito user created, wake endpoint called, benchmark run or apply performed in Phase 4A.
The user later authorized a local P4A checkpoint commit, without push and excluding
COLLAB_LOG.md. A separate clean checkout is used for release preparation.

## Evidence and boundaries

Repository: `D:\Project\LiveCap\livecap`.
Source checkpoint: `f5de16716e2ba4834972db44e770c9c25bcee032`.
AWS caller verified through STS: `arn:aws:iam::720459752315:user/camgiacntn`.
Application region: `ap-southeast-1`; CloudFront WAF region: `us-east-1`.

Phase 1–3 evidence is in `benchmark-harness.md`,
`benchmark-validation-phase2.md`,
`backend-pipeline-instrumentation.md` and
`backend-pipeline-instrumentation-validation.md`.
The Phase 2 manifest describes mock/loopback validation, not AWS performance.
Historical source hashes are not rewritten to match the later checkpoint.
Python 3.11 Docker base is pinned in `backend/Dockerfile`; a P4B build must
verify the actual image platform/runtime and instrumentation, not infer it from a tag.

Read-only AWS audit confirmed:
- stable task definition `livecap-target-backend-dev:53`;
- preview task definition `livecap-preview-backend-dev:22`;
- both services at desired/running `0/0`, and both current task definitions set `ENABLE_AUTH=true`;
- both task definitions use the same roles, registry, quota, history, transcript bucket,
  Cognito pool and application log group;
- production ALB has an HTTPS listener on 443, defaulting to stable;
- the ALB WAF defaults to block, with managed groups, rate limiting and an origin-verification rule;
- both CloudFront distributions reference the same CloudFront WAF and origin
  `api.livecap.logantai.com`; header VALUES were deliberately not exported.

Terraform/default comments and old docs are not authoritative live configuration.
For example, the stable anonymous default in IaC does not describe the current task.
The actual deployment workflow builds/pushes images and applies targeted ECS delivery
plans on main pushes. It cannot be reused for this benchmark root without a separate
review; no CI/CD changes are included here.

## Architecture and isolation matrix

New path: allowed benchmark client → separate CloudFront + edge WAF →
**new benchmark origin hostname and issued ACM certificate** → separate HTTPS ALB +
regional WAF → private benchmark Fargate task → separate application stores.
No frontend deployment, wake Lambda, production DNS edit or production CloudFront behavior.
Benchmark Uvicorn HTTP access logging is explicitly disabled to avoid peer-IP records.

The new root is `infrastructure/benchmark`, not a module invocation of the production root.
Only VPC/subnets and the CloudFront managed prefix list are Terraform DATA sources.
NAT, route tables and Internet Gateway are used through existing subnet routing and
are not managed, imported, moved or removed by benchmark state.

| Resource | Stable/preview sharing verified | Benchmark design | Destroy boundary |
|---|---|---|---|
| Terraform state | Main root uses `livecap/main/terraform.tfstate` | `livecap/benchmark/terraform.tfstate`, default workspace only | Only benchmark key; bucket remains shared infrastructure |
| State bucket | `livecap-terraform-state-dev-720459752315`, Singapore | Same existing bucket, independent key/lockfile | No bucket resource in benchmark root |
| VPC | `vpc-0d3a769b408f44be5` | Read-only reuse | No managed VPC |
| Public subnets | `subnet-0e7ac68941f5f6dbc`, `subnet-05b93952bdbc666fb` | Read-only reuse | No managed subnet |
| Private subnets | `subnet-0e6c54e39c800f12f`, `subnet-0260e958f366bdfb5` | Read-only reuse, no public task IP | No managed subnet |
| NAT/routes | Each private subnet has an active default route to its AZ NAT | Reuse egress; no route changes | No managed NAT/EIP/route |
| ALB/listener/TG/SG | ALB and task SG shared; separate stable/preview TG, preview header rule priority 100 in IaC | New ALB/listener/TG and two SGs | Cannot delete or modify existing listeners/rules/SGs |
| CloudFront/WAF | Distributions E39ADG0ES17RP1 and EXF7T06N8RPSP share `livecap-cloudfront-waf-dev`; ALB has `livecap-alb-waf-dev` | New distribution, two WAF ACLs and allowlists | No existing distribution/ACL association managed |
| ECS | Cluster `livecap-cluster-dev`; separate stable/preview services | New `livecap-benchmark-cluster/service/backend` | No stable/preview cluster/service managed |
| IAM | `livecap-ecs-task-dev`, `livecap-ecs-task-execution-dev` shared | `livecap-benchmark-task/execution`, scoped policies | No production task-role access to benchmark stores |
| Registry | `livecap-sessions-dev` shared | `livecap-benchmark-sessions` | Separate data |
| Quota | `livecap-usage-dev` shared | `livecap-benchmark-usage` | Separate allowance |
| History/admin/room | Shared history/admin tables; room table configured in preview | Separate history/admin/room tables with matching schemas | No production data references |
| Cognito | Pool `ap-southeast-1_uCz3Q7M9B` shared | New pool/public OAuth client/Hosted UI domain; admin-only user creation | No production identity/test account |
| S3/ECR | Shared transcript bucket and backend ECR in IaC | Separate transcript bucket and immutable ECR | Non-empty bucket/repository deliberately refuse deletion |
| Logs | `/ecs/livecap-backend-dev` shared, distinct ECS prefixes | `/ecs/livecap-benchmark-backend` + benchmark stream | Three-day retention, separate log group |
| Secrets/config | Existing Stripe/DeepSeek namespaces shared in IaC | `/livecap/benchmark/config/environment`; optional secret-based features OFF | No secret read/value in tfvars, plan or outputs |

Reusing ALB was rejected because its origin secret and rate-limit policy would couple
the benchmark to stable/preview. Additional fixed-cost resources were reported before
preparing the new-ALB proposal. **Cost approval for actual provisioning is still pending.**
Reuse of VPC/NAT reduces added fixed cost but shares egress contention, quotas, account
API limits and infrastructure security telemetry. This is application-state isolation,
not complete account/network isolation.

## Runtime, identity and instrumentation

Warm desired/min/max = **1/1/1**. On-demand Fargate, X86_64, 512 CPU units/1024 MiB,
platform 1.4.0; deployment can temporarily run two tasks (100/200 rollout settings).
Do not measure during deployment. `MAX_CONCURRENT_SESSIONS=4`,
`MAX_SESSIONS_PER_IP=4` initially; these are configured limits, not measured capacity.
Auth and DynamoDB registry are enabled; idle scale-down, Spot, rooms/IVS, summary,
billing, TTS, text analysis, X-Ray and Container Insights are off.

Quota is actually **five starts per week in Vietnam time** for normal users in current
backend code; names/comments mentioning monthly quota are stale. The WebSocket path
reserves quota when auth is on; `ENABLE_USAGE_QUOTA` is not a reliable bypass switch.
A single non-admin identity with one smoke and four admitted load sessions can exhaust
its allowance. Plan a separate non-admin identity cohort per run/scenario; do not reuse
production users, turn off auth, silently reset production quota, or use admin bypass
as baseline performance. Quota failures can fail open in current code: check
`quota_error_type` and invalidate such runs. Admin membership lookup is still part of admission.

Both Transcribe streams can run for one dual session. Four admitted dual sessions can
require eight concurrent Transcribe streams. Read-only Singapore quota is 25 concurrent
streams, 25 start requests/s for each start API; Fargate on-demand quota is 30 vCPU.
These are account limits, not measured capacity or guaranteed available headroom;
other consumers and current usage still require checking before a run.
Custom vocabularies are disabled here: this and disabled auxiliary features are
explicit fidelity differences to review, not benchmark conclusions.

Phase 3 instrumentation is always active in the checkpoint code; there is no invented
`ENABLE_INSTRUMENTATION` flag. The harness sends `benchmark_run_id` as a query parameter.
The logging group and stream are explicitly set for Watchtower, and stdout uses
benchmark awslogs. There are no custom high-cardinality metric dimensions.
Application events have metadata only; no token, user ID, email, IP, transcript or audio.
WAF request logging and sampling are disabled because request metadata can contain
credentials and IPs; inspect aggregated WAF metrics instead. Existing shared VPC flow
logs may still capture network metadata independently of application telemetry.

Logging is best effort: Watchtower batching, abrupt task exit and non-blocking awslogs
buffers can lose events. Stdout fallback may cause records to land under a different
stream. A missing event is missing evidence; do not silently equate it with a zero
duration or session failure. Check duplicate emissions/stream sources before aggregation.

WAF counts HTTP requests/handshakes, **not audio WebSocket messages**. Edge allowlisting
uses the actual viewer IP. Regional allowlisting checks the LAST X-Forwarded-For entry
and fails closed if absent; validate this boundary in P4B. Regional rate aggregation
uses FIRST per WAF behavior, so the edge source-IP rate rule remains necessary.
Rules do not reuse the production origin secret. Cognito and the narrow client
allowlist protect this separate endpoint; origin identity differs from production.

## P4B gates — bootstrap, service and smoke

This checklist spans several P4B steps. Issued TLS, ECR image and test users are outputs
of bootstrap/provisioning, not prerequisites that P4A can create. Use the ordered
Gate 0–3 table in `benchmark-phase4b-entry.md`.

- Review this root and fixed/usage costs. The user selected USD 20/month for alerts;
  this is **not a price estimate or enforced spending cap**. Configure the recipient
  privately in local `benchmark_alert_email`; never put it in the tracked example.
- Confirm ownership/absence of an existing record for
  `benchmark-origin.livecap.logantai.com`. Read-only DNS lookup returned NXDOMAIN;
  authoritative nameservers for logantai.com are launch1/launch2.spaceship.net.
  Route53 list-hosted-zones returned no zones in this account. These observations
  do not prove domain ownership or reserve the hostname; check the Spaceship zone
  and any private/split-horizon records again immediately before creating records.
  Create only new benchmark ACM validation records and a new benchmark origin CNAME
  to the NEW ALB in a separately authorized P4B step. Never repoint
  `api.livecap.logantai.com`, production frontend names or production listeners.
- Verify certificate ISSUED after bootstrap DNS validation, before full service apply.
  After full apply creates the new ALB, create only the benchmark origin CNAME and
  verify it targets exactly the benchmark ALB before any health/smoke request.
  An incorrect CNAME could route traffic to the existing ALB; no test may run before
  this check. No Route53/provider write is configured in this root.
- The tracked example retains `127.0.0.1/32`. Current machine public /32 was detected
  and saved only in ignored local tfvars; recheck VPN/runner/egress before a run and
  confirm both WAF boundaries in P4B. The example is intentionally unreachable.
- Review all tags; activate Environment as a cost allocation tag and confirm budget
  filtering. AWS cost attribution is delayed; a tag-filtered budget may omit untagged
  service API charges/shared NAT usage. Add an account-level guard separately if needed.
- A private recipient enables one email SNS subscription in the full plan. Its
  confirmation email is sent only on authorized P4B apply; confirm and verify delivery
  before smoke. No notification was sent in P4A. No running subscriber is assumed.
- Create the isolated ECR/certificate through a separately reviewed P4B bootstrap plan.
  Build/push the checkpoint image only into isolated ECR; record image digest, image
  runtime/platform, source SHA and Phase 3 presence before full service apply.
- Independently review a fresh full plan after bootstrap and real inputs. Never apply
  the Phase 4A design plan, or an old count/hash, after inputs change.
- Require clean worktree, matching image SHA and a reviewed P4A checkpoint. The
  original tree has pre-existing COLLAB_LOG.md changes. Use a separate clean checkout
  of the user-authorized P4A checkpoint. Do not revert, stage, stash or commit that
  protected file to satisfy the gate; do not exclude it from the clean-tree check.
- Create non-admin test identities only in the new pool after explicit P4B authorization.
  Use OAuth code + PKCE and the `aws.cognito.signin.user.admin` scope to obtain an
  access token; never use an ID token or put tokens in URLs/command arguments.
- Verify Transcribe account limits, egress connectivity and auth/quota behavior.
  Warm smoke precedes load; cold start is a separately authorized configuration/run.
  There is no wake endpoint or zero-capacity path in this warm design.

`benchmark_preflight.py --mode release` requires clean worktree, source SHA, real /32
and a matching reviewed saved plan. Full service checks also read the immutable ECR
repository/image digest and exactly one issued certificate for the benchmark hostname.
Bootstrap checks omit prerequisites that bootstrap itself must create. Passing these
checks is only local/plan readiness: build provenance/platform, DNS authority, cost/plan
review and explicit P4B authorization remain manual gates. After provisioning, verify
exact CNAME/ALB routing and alert delivery before smoke; identities/quota before load.
The current tree, placeholder allowlist and nonexistent image do not pass release checks.

## Plan and apply commands

PowerShell, from repository root. No real credentials in files or Terraform variables:

```powershell
Copy-Item infrastructure/benchmark/backend.hcl.example infrastructure/benchmark/backend.hcl
Copy-Item infrastructure/benchmark/benchmark.tfvars.json.example infrastructure/benchmark/benchmark.tfvars.json
.\tools\plan_benchmark.ps1 -VarFile infrastructure/benchmark/benchmark.tfvars.json -BackendConfig infrastructure/benchmark/backend.hcl -Profile camgiacntn
# Independent plan ONLY for P4B bootstrap review; still no apply:
.\tools\plan_benchmark.ps1 -Scope bootstrap -VarFile infrastructure/benchmark/benchmark.tfvars.json -BackendConfig infrastructure/benchmark/backend.hcl -Profile camgiacntn
```

The wrapper has **no apply/destroy code**. It validates account/key/region/schema/SHA,
initializes the dedicated S3 backend, validates and saves a plan, then rejects managed
shared resources, production store references, unknown resource types and update/delete/
replacement actions. It rejects workspace redirection and compares plan variables with
the selected var-file. Phase4A design mode reports dirty tree; it does not grant release approval.
Implicit tfvars/override files, TF_VAR/TF_CLI_ARGS/TF_DATA_DIR/TF_WORKSPACE overrides
are rejected. The bootstrap guard permits only ECR and ACM; a targeted plan does not
certify the omitted full graph. Shared/network references are reviewed in the full plan.
The account/key are also guarded by Terraform backend/provider/preconditions.

AWS CLI login sessions are not directly supported by the older Terraform provider SDK.
The wrapper exports temporary credentials to its own process environment, never prints
or persists them, and restores the prior environment in finally. This is not an AWS
application deployment. For future standalone Terraform commands, use the same reviewed
ephemeral credential mechanism; do not manually paste credentials into the backend.

Future **P4B only**, after all gates pass and fresh plan review:
```powershell
$vars = (Resolve-Path infrastructure/benchmark/benchmark.tfvars.json).Path
$backend = (Resolve-Path infrastructure/benchmark/backend.hcl).Path
python tools/benchmark_preflight.py --mode release --profile camgiacntn --var-file $vars --backend-config $backend --plan-json infrastructure/benchmark/.terraform/benchmark-plan.json
if ($LASTEXITCODE -ne 0) { throw 'NO-GO: do not apply' }
terraform -chdir=infrastructure/benchmark apply -input=false "-var-file=$vars"
```
The var-file is mandatory in this procedure; environment/account/owner/image/hostname
also have no Terraform defaults. Review the interactive final plan; no auto-approve.
Direct Terraform invocation can bypass the Python guard, so enforcement requires the
reviewed procedure and scoped P4B IAM. Required JSON values must not be supplied through
ad-hoc TF_VAR overrides. Never use the production root, state import/mv/rm, `-migrate-state`
or `-reconfigure` to bypass a backend mismatch. Checkpoint/review authorization is
separate from actual apply authorization.

A fresh targeted P4B bootstrap may provision only ECR and ACM certificate. Exact
future command sequence, after cost/DNS/plan review and explicit P4B authorization:
```powershell
.\tools\plan_benchmark.ps1 -Scope bootstrap -VarFile $vars -BackendConfig $backend -Profile camgiacntn
python tools/benchmark_preflight.py --mode release --scope bootstrap --profile camgiacntn --var-file $vars --backend-config $backend --plan-json infrastructure/benchmark/.terraform/benchmark-bootstrap-plan.json
if ($LASTEXITCODE -ne 0) { throw 'Bootstrap NO-GO' }
# Use the same ephemeral credential setup described above. Review interactive plan:
terraform -chdir=infrastructure/benchmark apply -input=false "-var-file=$vars" -target=aws_ecr_repository.benchmark -target=aws_acm_certificate.benchmark
```
The command replans interactively, so review that actual plan as well; a previously
checked JSON alone does not bind an independently replanned apply. No auto-approve.
Targeting omits the full graph: generate/check the full isolation plan again afterward.
Retrieve the new certificate's DNS validation CNAME using `aws acm describe-certificate`
and add only that new record in the verified authoritative zone. Wait for ISSUED.
Build/push only the reviewed Linux amd64/Python 3.11 checkpoint into isolated ECR and
record its digest/provenance; the tag alone cannot prove image contents. A source
checkpoint after P4A changes needs its actual new SHA in the var-file and a fresh plan.
Full apply creates the ALB/distribution; only then set the new origin CNAME to its exact
ALB DNS output. Verify alert subscription/delivery, CNAME and auth before smoke.

## Future warm smoke — commands prepared, NOT executed

Only after release gates and exact output/DNS/resource verification:
```powershell
$health = terraform -chdir=infrastructure/benchmark output -raw benchmark_health_url
$ws = terraform -chdir=infrastructure/benchmark output -raw benchmark_websocket_url
Invoke-WebRequest -Uri $health
# Supply LIVECAP_ACCESS_TOKEN privately through the environment, never paste into a command.
python tools/ws_load_test.py --url $ws --auth --audio-mode wav --audio-file samples/benchmark.wav --concurrency 1 --warmup-sessions 0 --stream-mode dual --source vi-VN --target en --run-id benchmark-warm-smoke-001 --scenario benchmark-warm-smoke --output-json artifacts/benchmark-warm-smoke-001.json --output-csv artifacts/benchmark-warm-smoke-001.csv
```
`samples/benchmark.wav` is a placeholder path, not an existing or fabricated fixture.
Use a consented speech fixture meeting the harness WAV format checks, keep it local,
and record its real hash/duration. Silence cannot establish time to first caption.
Check token issuer equals the benchmark pool, the target URL is its distribution and
the result manifest records intended configuration. No `--insecure`, production URL
or wake fallback. Load/cold commands require subsequent scenario authorization.

## Logs Insights and raw exports after a real run

Seven supported events:
`websocket_admission_completed`, `transcribe_stream_started`,
`transcribe_result_received`, `translation_operation_completed`,
`arbitration_or_buffer_completed`, `websocket_caption_send_completed`,
`websocket_session_outcome`.

Inventory query (not every session must emit all events on rejection/error paths):
```sql
filter schema_version = "1.0" and benchmark_run_id = "YOUR_RUN_ID"
| stats count(*) as records by event
| sort event asc
```
Translation breakdown; skip/cancel/failure outcomes must be separately accounted for:
```sql
filter schema_version = "1.0" and benchmark_run_id = "YOUR_RUN_ID"
  and event = "translation_operation_completed" and success = true
| stats count(*) as operations, pct(duration_ms, 50) as operation_p50,
  pct(duration_ms, 95) as operation_p95, pct(executor_queue_duration_ms, 95) as queue_p95,
  pct(sdk_call_duration_ms, 95) as sdk_p95 by direction
```
Session reconciliation:
```sql
filter schema_version = "1.0" and benchmark_run_id = "YOUR_RUN_ID"
  and event = "websocket_session_outcome"
| stats count(*) as records by outcome, admitted, session_end_send_success
```
Client connection/first-caption/final-lag/success/disconnect/throughput definitions
remain those in `benchmark-harness.md`. Backend operation/SDK durations are not
AWS-only compute time. ALB RequestCount/TargetResponseTime are not caption message
throughput or final caption lag.

PowerShell export, with time bounds from the real client manifest:
```powershell
$run = Get-Content artifacts/benchmark-warm-smoke-001.json -Raw | ConvertFrom-Json
$runId = $run.run_id
if ($runId -notmatch '^[A-Za-z0-9._-]{1,64}$') { throw 'Invalid run id' }
$start = ([DateTimeOffset]::Parse($run.started_at)).AddMinutes(-2)
$end = ([DateTimeOffset]::Parse($run.ended_at)).AddMinutes(2)
$query = 'fields @timestamp, @message | filter schema_version = "1.0" and benchmark_run_id = "' + $runId + '" | sort @timestamp asc | limit 10000'
$queryId = aws logs start-query --log-group-name /ecs/livecap-benchmark-backend --start-time $start.ToUnixTimeSeconds() --end-time $end.ToUnixTimeSeconds() --query-string $query --query queryId --output text --profile camgiacntn --region ap-southeast-1 --no-cli-pager
aws logs get-query-results --query-id $queryId --profile camgiacntn --region ap-southeast-1 --no-cli-pager > artifacts/benchmark-warm-smoke-001-logs.json
foreach ($metric in @('CPUUtilization', 'MemoryUtilization')) {
  aws cloudwatch get-metric-statistics --namespace AWS/ECS --metric-name $metric --dimensions Name=ClusterName,Value=livecap-benchmark-cluster Name=ServiceName,Value=livecap-benchmark-service --start-time $start.ToString('o') --end-time $end.ToString('o') --period 60 --statistics Average Maximum SampleCount --profile camgiacntn --region ap-southeast-1 --no-cli-pager > "artifacts/benchmark-warm-smoke-001-$metric.json"
}
```
Verify manifest field names/schema before export; current harness uses `run_id`.
Wait/poll get-query-results until status Complete, preserve failures/cancellation.
Allow Watchtower ingestion to settle; export again only if late records change results.
If 10,000 records are reached, split time intervals and reconcile counts; results are
not automatically complete/paginated. CPU/memory use standard AWS/ECS dimensions:
missing datapoints at zero tasks are not 0% utilization; one-minute sampling cannot
resolve subsecond peaks. Preserve raw JSON, client report, source/image/config hashes
and run timestamps. Backend durations use monotonic clocks, not cross-host clock subtraction.

Cold-start later: separately review capacity 0→1 controls scoped to benchmark service.
Measure trigger acceptance → healthy ALB target → client admission and first caption as
separate boundaries. Preserve task createdAt/pullStartedAt/pullStoppedAt/startedAt and
control-plane timestamps; polling intervals add uncertainty. Do not call production wake
or present a health endpoint returning 200 as proof a caption session is ready.

## Costs — current public prices, not bills or CV metrics

Read-only AWS Price List lookup on 2026-10-03 (Vietnam time), Singapore on-demand;
SKUs/effective dates and Decimal calculations are in `benchmark-environment-pricing.json`.
No Free Tier, credit, tax or discount assumed. This is a cost model, not measured usage.

| Driver | Added benchmark resources/usage | Hourly/monthly estimate |
|---|---|---|
| ALB | One ALB, plus LCU | $0.0252/hour base; $0.008/LCU-hour; base $18.396 per 730 hours |
| Public IPv4 | Internet-facing ALB in two AZs; model assumes two addresses, actual count can increase | $0.005/address-hour; modeled $7.30 per 730 hours |
| Fargate | One Linux X86 on-demand 0.5-vCPU/1-GiB warm task; rollout can temporarily double tasks | vCPU $0.05056/hour + GiB $0.00553/hour; task $0.03081/hour, $22.4913 per 730 hours |
| WAF | Two ACLs, four rule/group entries per ACL, plus request usage | $5/ACL-month + $1/rule-or-group-month; fixed $18/month, prorated hourly; requests extra |
| CloudFront | Separate distribution, request/transfer usage | TBD |
| NAT | No added NAT/EIP; additional bytes use existing NATs; shared fixed charges remain | $0.059/GB processed, plus applicable transfer; shared fixed cost not assigned entirely to benchmark |
| Transcribe | Single vs two streams per session; stream duration/minimum billing must be checked | TBD |
| Translate | Character volume and retry/workload effects | TBD |
| Cognito | Isolated users/auth flow usage; verify applicable tier/MAU charging | TBD |
| DynamoDB | Five PAY_PER_REQUEST tables, request/storage/TTL activity | TBD |
| S3/ECR | Storage and API/data-transfer usage; retention does not eliminate all residual cost immediately | TBD |
| Logs/Insights/SNS/Budgets/SSM/ACM/DNS | Ingestion/storage/query and applicable service charges; confirm current plans/free tiers | TBD |
| Optional APIs | DeepSeek/Stripe/Polly/Comprehend/IVS/X-Ray not enabled/called in this design | No usage assumption until a run proves actual calls |

No new NAT, hosted zone, VPC endpoint or Container Insights resource is chosen.
Modeled warm base = **$66.1873 for 730 hours plus a full month of WAF fixed fees**,
excluding LCU and every usage/storage/API charge. An illustrative eight-hour window
with WAF modeled at 8/730 of monthly fees gives **$0.72534 base**, with the same exclusions.
These are explicitly assumed durations, not observed runtimes or total-cost quotes.
AWS actual billing granularity/month length and additional ALB IPs can change the result.
The $20 alert threshold is below this always-on monthly model; alerts cannot enforce a cap.
Set a planned teardown time in P4B and export actual usage/cost after the run.
Sources: [Fargate](https://aws.amazon.com/fargate/pricing/),
[ALB](https://aws.amazon.com/elasticloadbalancing/pricing/),
[IPv4/NAT](https://aws.amazon.com/vpc/pricing/), [WAF](https://aws.amazon.com/waf/pricing/).
Shared NAT contention
may affect both traffic and cost. Budget alerts are delayed and do not stop services.
Resource tags are not proof every AWS API cost is attributed to benchmark.

## IAM for P4B

Use a reviewed benchmark deployment principal, not the existing GitHub delivery role.
Required permissions depend on the final graph; this is a permission inventory, not a
new broad policy applied to the current user:

- Read shared EC2 VPC/subnet/prefix-list/routes/NAT metadata; no write on shared network.
- Read/write benchmark state key; ListBucket restricted prefix; Get/Put/Delete on only
  benchmark `.tflock`. No production state object write/read requirement.
- Create/describe/update/delete/tag only benchmark ALB/listener/TG/SG, ECS cluster/service/
  task definitions/scaling targets, ECR, S3, DynamoDB, Cognito, logs, SSM, ACM, WAF, SNS
  and Budgets as needed. Creation/list operations without resource scoping need condition
  controls (account/region/request tags/name) where supported.
- IAM create/read/tag/delete benchmark roles/inline policies; PassRole limited to those
  two roles and ecs-tasks.amazonaws.com; no reuse of production task-role permissions.
- ECR auth/token plus layer/image push into only livecap-benchmark-backend; no image push
  in P4A. Verify scoped service-linked role creation prerequisites for first ECS/ALB/scaling/WAF use.
- Later Cognito user provisioning only in the benchmark pool, and test access-token flow.
- Logs StartQuery/GetQueryResults and CloudWatch reads for benchmark exports; some
  CloudWatch/list actions cannot be resource-scoped.
- External DNS ownership/validation/new-record capability only for benchmark names, via
  its actual DNS provider after explicit P4B review.

Task execution role can pull only benchmark ECR and write only benchmark logs.
Application role can access only benchmark stores/pool for supported resource-scoped
operations; streaming Transcribe, Translate and token-authorized Cognito GetUser require
wildcard resources. No idle ECS UpdateService, Stripe/DeepSeek secret access, Cost Explorer
or admin mutation privileges are granted.

## Teardown and rollback — future commands, not executed

Before destroy: stop benchmark runs; preserve real reports/raw logs/metrics/image digest.
Review a fresh destroy plan using the same var-file/backend, then validate it with
`benchmark_preflight.py --mode design --destroy-plan --plan-json <destroy-json>`.
Only benchmark addresses may be deleted. Empty/delete ONLY benchmark bucket objects and
ECR images after archive/review; force_destroy/force_delete remain false. Do not modify
shared NAT/VPC/routes/state bucket, production buckets or identities.

```powershell
$vars = (Resolve-Path infrastructure/benchmark/benchmark.tfvars.json).Path
$backend = (Resolve-Path infrastructure/benchmark/backend.hcl).Path
python tools/benchmark_preflight.py --mode design --profile camgiacntn --var-file $vars --backend-config $backend
if ($LASTEXITCODE -ne 0) { throw 'Wrong state/identity: stop' }
terraform -chdir=infrastructure/benchmark plan -destroy -input=false "-var-file=$vars" -out=.terraform/benchmark-destroy.tfplan
if ($LASTEXITCODE -ne 0) { throw 'Destroy plan failed' }
$destroyJson = terraform -chdir=infrastructure/benchmark show -json .terraform/benchmark-destroy.tfplan
if ($LASTEXITCODE -ne 0) { throw 'Destroy plan export failed' }
[IO.File]::WriteAllText((Join-Path (Get-Location).Path 'infrastructure/benchmark/.terraform/benchmark-destroy-plan.json'), ($destroyJson -join "`n"), [Text.UTF8Encoding]::new($false))
$destroyJson = $null
python tools/benchmark_preflight.py --mode release --profile camgiacntn --var-file $vars --backend-config $backend --destroy-plan --plan-json infrastructure/benchmark/.terraform/benchmark-destroy-plan.json
if ($LASTEXITCODE -ne 0) { throw 'Destroy isolation checks failed' }
# After authorized teardown and verified benchmark-only plan:
terraform -chdir=infrastructure/benchmark destroy -input=false "-var-file=$vars"
```
No auto-approve. Clean worktree/source matching and temporary credential setup still apply.
Never apply the stale create plan to roll back a partially failed deployment.
If image/auth/health/DNS fails, stop traffic and use a fresh benchmark-only recovery or
destroy plan; do not change stable/preview routing to compensate. Circuit-breaker rollback
is best effort and cannot guarantee an initial deployment with no previous healthy revision.

After destroy, verify benchmark ECS/services/task revisions/ECR/buckets/tables/pools/
domains/ACLs/distribution/ALB/TG/SG/IAM/logs/SSM/SNS/Budget/certificate resources are absent.
Check Singapore and us-east-1, including untaggable children; Resource Groups Tagging API
alone is incomplete. Confirm benchmark state list is empty, new external DNS records are
removed through their provider, subscriptions/queued usage do not persist, and shared
resources retain their baseline. Keep backend state versions/audit evidence; do not delete
the shared state bucket. CloudFront disable/delete can take time. Review billing later;
a resource deletion check does not prove an immediate zero bill.

## Phase 4A validation result

Fresh final plan: **40 create / 0 update / 0 delete**. Production/stable/preview managed
resource counts: **0 / 0 / 0**. There are 39 AWS-provider managed instances (including
ACM certificate-validation workflow) and one local terraform_data guard. These are
Terraform plan instances, not forty deployed/billable services.

The initial HTTP-origin design plan (38 creates) was superseded before completion;
the final reviewed design includes new TLS certificate/validation and HTTPS origin.
No production listener/certificate/DNS was changed. Only the final plan is current.
Provider hashicorp/aws 5.100.0 is locked. fmt-check recursive, benchmark validate,
17 safety tests and git diff --check passed. Relevant tests target wrong state/workspace,
account/region, unsafe mutation, production references and accidental credential output.
An injected TF_CLI_ARGS_plan=-destroy was rejected by the PowerShell wrapper before init.
Backend/client performance behavior was not changed or benchmarked in P4A. A local
Linux amd64 image built from the unchanged backend checkpoint verified Python 3.11.15,
compileall, dependency imports, pip check and presence of seven Phase 3 event names.
Validation containers had no network or credentials. This is not pipeline execution
evidence; Docker cache may supply build dependencies. The local-only build script
repeats these checks from a clean checkpoint and records private evidence under .terraform.
The separate targeted bootstrap design plan creates two resources (isolated ECR and
ACM certificate), with zero update/delete. It does not deploy an image, validate DNS,
create an ALB or prove readiness of the omitted service graph.

Plan files are local/gitignored under `infrastructure/benchmark/.terraform`.
A tracked validation manifest records exact plan hashes, counts and source hashes
with CRLF normalized to LF, so Windows script checkout endings do not create false drift.
Secret scan is a bounded pattern check plus schema/resource review, not a guarantee
against every possible credential format. No real credential values appear in prepared
tfvars/config/plan outputs; source scan prints only match counts.

COLLAB_LOG.md retained its prior SHA256:
`F1529DD297787110A802D89E4F419F7076DBB616F75E612C80F0C430312DF5B5`.
Local checkpoint commit is now user-authorized; no push/apply/deploy/test user/benchmark.
P4B entry requires clean checkpoint, real local configuration/recipient and reviewed
plans. Service/smoke gates additionally require issued TLS, pushed image/provenance,
exact new origin CNAME, activated billing tag, confirmed alerts and isolated identities.
See `benchmark-phase4b-entry.md`; no CV numbers are supported yet.

References for protocol boundaries:
[AWS WebSockets with CloudFront](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/distribution-working-with.websockets.html),
[AWS managed origin request policies](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/using-managed-origin-request-policies.html),
[AWS forwarded-IP configuration](https://docs.aws.amazon.com/waf/latest/APIReference/API_IPSetForwardedIPConfig.html).
