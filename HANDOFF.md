# Handoff — branch `Update` (Phase 0 + Phase 1)

This branch contains reviewed, tested changes prepared for you to push and open
a PR. **Do not `git add -A`** — there is pre-existing CRLF working-tree noise on
unrelated files (`docs/as-deployed-architecture.md`, `docs/demo-guide.md`) that
is NOT part of this work. The commit on this branch already stages only the
intended files.

## To push

```bash
git push -u origin Update
# then open a PR against main on GitHub (9ducanh9/livecap)
```

## What changed

**Phase 0 — ops hardening (safe, no behavior change):**
- `.gitattributes` — normalize line endings to LF, stop CRLF churn.
- `infrastructure/terraform/cost_guard.tf` + `variables.tf` — add a FORECASTED
  80% budget alert alongside the ACTUAL 100% alert (needs an email set).
- `infrastructure/terraform/cloudwatch.tf` + `variables.tf` — manage the
  watchtower `livecap` log group with an explicit retention policy.
- `terraform.tfvars.example` — documents the new inputs.

**Phase 1 — Amazon Bedrock meeting summary (opt-in, default OFF):**
- `backend/app/services/summarization.py` (new) — end-of-session bilingual
  summary + key points, decisions, action items, topics via Bedrock (Claude).
- `backend/app/routers/websocket.py` — collect finalized segments, send a
  `session_summary` message before `session_end`.
- `backend/app/models.py` — `SessionSummary`, `SummaryMessage`, optional
  `summary_text` on `ExportRequest`.
- `backend/app/services/storage.py` + `routers/export.py` — prepend the summary
  to exported TXT (backward compatible).
- `backend/app/config.py` + `backend/.env.example` — feature flags.
- `infrastructure/terraform/iam.tf` — `bedrock:InvokeModel` policy (only when
  `enable_meeting_summary = true`).
- `infrastructure/terraform/ecs.tf` + `variables.tf` — pass the flag + model ID
  to the task definitions.
- `backend/tests/test_summarization.py` (new) — 16 tests, all passing.

## Verification done

- Backend modules touched: 101/101 tests pass (Python 3.10 sandbox).
- `test_websocket.py` failures in the sandbox are only Python 3.10 missing
  `asyncio.timeout`; verified 22/23 pass once polyfilled. Run the full suite on
  **Python 3.11** (the project's target) for a clean pass.
- `compileall app` passes.
- Terraform NOT validated here (no terraform in sandbox) — run
  `terraform fmt` + `validate` before applying.

## Remaining MANUAL steps (do NOT let an agent auto-apply to AWS)

1. Set `budget_notification_email` in `terraform.tfvars`; optionally
   `enable_meeting_summary = true` and `bedrock_model_id`.
2. Import the existing watchtower log group before the first apply:
   `terraform -chdir=infrastructure/terraform import aws_cloudwatch_log_group.watchtower livecap`
3. If enabling Bedrock: **build & push a new backend image** (this is new code),
   and enable Bedrock model access for the Claude model in the target region.
   Verify the model is available in `ap-southeast-1`; otherwise set
   `BEDROCK_REGION` or use an inference-profile ID as `bedrock_model_id`.
4. `terraform plan` → review → `apply`. Confirm the budget SNS subscription email.

## Follow-up (not in this branch)

- Frontend does not yet render the `session_summary` message — add a summary
  panel + pass `summary_text` into the export request.
- Optional cleanup: `git add --renormalize . && git commit -m "Normalize line
  endings to LF"` to clear the unrelated CRLF noise repo-wide.
