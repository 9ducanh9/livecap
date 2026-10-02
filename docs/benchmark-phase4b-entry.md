# Phase 4B entry and ordered gates

P4B starts with a review/authorized bootstrap; service deployment and measurement are
later gates. An image in ECR, issued certificate, running service and test users are
outputs of P4B, not prerequisites that P4A can create under its no-apply constraint.
No CV performance claim follows from infrastructure plans or offline image validation.

## Gate 0 — before entering P4B

| Requirement | Evidence / current handling |
|---|---|
| Account / region / state | STS account 720459752315, IAM user camgiacntn, ap-southeast-1; dedicated livecap/benchmark/terraform.tfstate key. Read-only listing found no object under benchmark prefix before provisioning. |
| Phase 1–3 source | Checkpoint f5de16716e2ba4834972db44e770c9c25bcee032; checkpoint the P4A files separately before creating a clean checkout. |
| P4A checkpoint authorization | User confirmed a checkpoint commit, no push; COLLAB_LOG.md remains excluded and unchanged. |
| Clean execution checkout | A separate checkout of the approved P4A checkpoint, with clean git status. Do not change, stage, stash or revert COLLAB_LOG.md in the original checkout. |
| Image source | Ignored local tfvars must use that checkout's actual full HEAD SHA. Build locally with the script below; ECR push remains a P4B action. |
| Client allowlist | Current machine public IPv4 read from checkip.amazonaws.com and stored only in ignored local tfvars. Check again before a real run; a different runner/VPN needs its own /32. Example remains 127.0.0.1/32. |
| DNS authority | Public NS are launch1/launch2.spaceship.net. Origin A lookup returned NXDOMAIN; no Route53 zones in this account. User confirmed DNS administration. No record written; recheck collision before adding new records in P4B. |
| Budget | User selected $20/month alert threshold; recipient must be supplied privately in local tfvars. Monthly warm base model is about $66.19 before variable charges, so $20 is an alert and cannot fund/enforce a month of continuously running resources. |
| Billing tag | Environment tag is currently Inactive. Activate/check it in authorized P4B before provisioning warm service. Activation affects all values of that tag key; it is deliberately not owned by benchmark destroy. |
| Audit | No custom trail returned by describe-trails; default CloudTrail Event History has an ECS DescribeTaskDefinition event. Use redacted management-event metadata as audit evidence. Do not infer durable trail storage from Event History. |
| Service quotas | Read-only Singapore quota: concurrent Transcribe streams 25; both start APIs 25 requests/s; Fargate on-demand vCPU quota 30. Four dual sessions can use eight streams; other account consumers remain unknown. No measured capacity claim. |
| IAM | Principal simulation returned allowed for sampled create actions, including ECR/ACM. Simulation is not proof of every resource/context/SCP permission; review the IAM inventory and fail closed on actual denial. |
| Plans and local validation | Fresh full and bootstrap plans from this clean checkout, exact var-file, initialized backend, isolation guard and local safety tests. Saved artifacts contain private configuration; never commit plan JSON/binary or real email/IP. |

From the clean checkout:

```powershell
$sha = (git rev-parse HEAD).Trim()
$vars = (Resolve-Path infrastructure/benchmark/benchmark.tfvars.json).Path
$backend = (Resolve-Path infrastructure/benchmark/backend.hcl).Path
.\tools\build_benchmark_image.ps1 -ImageGitSha $sha
.\tools\plan_benchmark.ps1 -Scope full -VarFile $vars -BackendConfig $backend -Profile camgiacntn
.\tools\plan_benchmark.ps1 -Scope bootstrap -VarFile $vars -BackendConfig $backend -Profile camgiacntn
python tools/benchmark_preflight.py --mode release --scope bootstrap --profile camgiacntn --var-file $vars --backend-config $backend --plan-json infrastructure/benchmark/.terraform/benchmark-bootstrap-plan.json
```

A passing bootstrap preflight proves local/plan checks, not permission to apply.
Review the exact two-resource bootstrap plan and authorize P4B apply separately.
Cost email subscription is part of the later full plan; bootstrap creates no subscriber
or running service. With a configured email, full plan includes one new SNS subscription
whose confirmation is sent only during authorized P4B provisioning.

## Gate 1 — authorized P4B bootstrap

Create only the isolated ECR repository and benchmark ACM certificate using the exact
targeted commands in benchmark-environment.md. Check the actual interactive plan again.
Then add only the new certificate validation CNAME in the confirmed Spaceship zone,
wait for ISSUED, tag/push the checkpoint image only into benchmark ECR, and record its
remote digest and provenance. A local image ID is not the remote ECR digest.
These actions are not executed by the P4A plan/build scripts.

## Gate 2 — before full service apply

After separate authorization, activate Environment cost allocation tag and verify Active:

```powershell
aws ce update-cost-allocation-tags-status --cost-allocation-tags-status TagKey=Environment,Status=Active --profile camgiacntn --region us-east-1 --no-cli-pager
aws ce list-cost-allocation-tags --tag-keys Environment --profile camgiacntn --region us-east-1 --query 'CostAllocationTags[].{Key:TagKey,Status:Status}' --output json --no-cli-pager
```

This account-wide billing action is outside benchmark Terraform state; never deactivate
it during benchmark teardown. Allow propagation before relying on the tag-filtered budget.
Re-check date before these billing API calls. Verify issued certificate and immutable ECR
image via full release preflight; independently verify Linux amd64/Python 3.11 and source
provenance. Review a fresh full plan after bootstrap, including the email subscription,
then authorize the fixed/variable costs and choose an explicit teardown deadline before
creating the warm service. No production listener/DNS/application-state edits.

## Gate 3 — before health/smoke

Use the newly provisioned ALB's exact DNS output for a new benchmark origin CNAME.
Verify that CNAME, certificate and CloudFront origin; confirm email subscription and
delivery and the budget filter. Provision only isolated non-admin Cognito identities;
verify token issuer, auth/quota behavior and both WAF boundaries. Retrieve only redacted
CloudTrail event metadata for mutations in Singapore/us-east-1. Then authorize warm
smoke; use a real consented speech fixture. Load and cold-start scenarios need their
separate subsequent configuration/run authorization. No production load test.

Sources: [cost tag activation](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/activating-tags.html),
[CloudTrail Event History](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/view-cloudtrail-events.html).
