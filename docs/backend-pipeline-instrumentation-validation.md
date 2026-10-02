# Backend instrumentation validation — 2026-10-02

This report covers code correctness and offline observations only. It contains
no production, preview, AWS service or real benchmark performance evidence.
Generated captions/audio, fake clock durations and mocked SDK results cannot
be used as CV numbers. HEAD stayed
`b8a51ad492d514252a0ff4e0ca6968d4c864b47e`; changes remain uncommitted/unstaged.

## Checks actually run

| Check | Result | Boundary |
|---|---|---|
| All backend tests via the offline runner | 480 passed, exit 0, application network attempts blocked: 0 | Mocked providers, in-process ASGI/in-memory sockets; does not validate AWS ingestion/provider performance |
| Instrumentation suite, including schema assertions on every observed new event | 54 passed, exit 0, application network attempts blocked: 0 | Correlation, clocks, payload privacy, failures, counters and message contract |
| Client unit discovery with warnings treated as errors | 68 discovered: 59 passed, 9 opt-in loopback tests skipped | No real loopback/public backend test run in this phase |
| Backend compileall | Passed with a fresh temporary `PYTHONPYCACHEPREFIX` | Default cache path initially failed due to access-denied replacement of existing unrelated `.pyc` files; no source compile error |
| Python 3.11 grammar/in-memory compile | Passed for all backend app modules and changed Python files | Actual installed test runtime is Python 3.14.2; this is not a Python 3.11 runtime test |
| Tracked and current-phase untracked diff whitespace checks | Passed | CRLF-normalization notices are Git warnings, not whitespace failures |
| AST comparison against HEAD | Arbitration/buffer/queue/timing constants and Transcribe/Translate SDK request arguments unchanged | Queue sizes/windows/SDK contract preservation, not a throughput test |
| Models/config and protected-file check | Models/config unchanged; protected collaboration log hash unchanged | No frontend, Terraform, auth implementation or database schema edit |
| Logging privacy review | Passed AST extra-field review and fixture assertions | Touched pipeline logging only; not a repo-wide third-party logging guarantee |

Backend warnings: the full run reported 1,669 dependency deprecations from
FastAPI/Starlette (`asyncio.iscoroutinefunction`), botocore (`utcnow`) and httpx
raw-content usage on Python 3.14. Dependencies were not changed. No application
test failed. No existing Python lint/formatter gate was found in the repository;
CI's backend gates are compileall and pytest. No new lint tool was installed.

The full-suite runner mocks existing app startup logging and one missing legacy
admin audit SDK fixture. Earlier exploratory checks caught Watchtower startup
and an unmocked audit read; both were blocked before network transmission and
the guard rejected those checks. The final successful run has zero attempted
application DNS/connect/sendto calls. No real credentials were used by the runner.

Commands (from `backend` unless stated otherwise):

```text
.venv/Scripts/python.exe -B tests/run_pipeline_offline.py tests -q -p no:cacheprovider
.venv/Scripts/python.exe -B tests/run_pipeline_offline.py tests/test_pipeline_instrumentation.py -q -p no:cacheprovider
```

From repository root, with `LIVECAP_RUN_LOCAL_VALIDATION` unset:

```text
backend/.venv/Scripts/python.exe -B -W error -m unittest discover -s tools/tests -v
git diff --check
git diff --cached --name-only
git rev-parse HEAD
```

Compileall uses a fresh temporary cache root to avoid replacing pre-existing
cache files. Python 3.11 syntax compatibility and the AST invariants are checked
in memory; those checks make no network requests or source edits.

## Requirement evidence

| Requirement | Implementation/evidence |
|---|---|
| Exact optional run-ID regex; invalid -> null, no rejection/response change | `validate_benchmark_run_id`, router ContextVar, harness query; boundary/invalid-ID/session-message tests |
| Consistent seven-event JSON schema, monotonic durations | Allowlisted `PipelineTelemetry.emit`, logger UTC timestamp, fake perf/wall clocks and all-event schema assertions |
| Admission stage timings and rejection denominators | Router stage timers; auth, limit, quota, registry-store and quota fail-open tests; nonadmitted invocations have no terminal event |
| Transcribe open and result receipt metadata | Both service open paths and `_SegmentHandler`; provider open/failure, final receipt and partial aggregate test |
| Translation operation, queue and SDK splits | Context-local operation timing, executor worker boundary and SDK finally; success/error/empty/cancel/init/concurrent-correlation tests |
| Arbitration/buffer residence without algorithm changes | Separate perf timestamps; emitted/dropped tests and constant comparison with HEAD |
| Send failure observed without changing teardown | Private `_send` returns a status while retaining swallowed failures; partial/final/session-end failure tests and partial aggregation |
| One terminal emission attempt per admitted invocation | Wrapper finally plus `finished` guard; send-failure, timeout/disconnect, provider/internal error and rejection tests |
| Counters with defined semantics | Binary frame totals before validation; outbound send attempts and completed translation outcomes; normal/invalid-frame/degradation tests |
| Logging failure cannot break success/error paths | Best-effort event emit and legacy logger adapter; logger exceptions tested on success, Transcribe failure and translation failure |
| No payload leakage | Fixed messages, safe exception classes/IDs/enums; tests contain private token/audio/transcript/email/IP/user fixtures and assert they do not appear in logs |
| No synchronous AWS hot-path telemetry, custom metrics, per-frame logs | stdlib telemetry helper; source/diff review; partials aggregate; existing transport reused; no PutMetricData/EMF/Terraform additions |
| Docs, nullable fields, examples and overhead estimate | `backend-pipeline-instrumentation.md`: exact boundaries, outcomes, client/infra limitations, count formula and unexecuted query examples |
| Preserve protected dirty changes and no publication | Protected hash below; empty staged-file listing; unchanged HEAD; no stage/commit/push/deploy operation |

## Events implemented

All seven are present in live code and exercised by offline tests:

1. `websocket_admission_completed`
2. `transcribe_stream_started`
3. `transcribe_result_received`
4. `translation_operation_completed`
5. `arbitration_or_buffer_completed`
6. `websocket_caption_send_completed`
7. `websocket_session_outcome`

Partial provider results and partial sends are summaries, not individual latency
samples. Final metadata is logged individually. Translation duration includes
lazy client acquisition through the public wrapper; the executor and SDK split
does not claim AWS-only service time. Outcome precedence and exact count/nullable
semantics are documented in the event reference.

## Files changed in this phase

Repository paths below are relative to `D:/Project/LiveCap/livecap`:

- `backend/app/routers/websocket.py`
- `backend/app/services/transcription.py`
- `backend/app/services/translation.py`
- `backend/app/services/logging_service.py`
- `backend/app/services/pipeline_instrumentation.py` (new)
- `backend/tests/test_logging_service.py`
- `backend/tests/test_pipeline_instrumentation.py` (new)
- `backend/tests/run_pipeline_offline.py` (new)
- `tools/ws_load_test.py` (run-ID query addition to the prior harness work)
- `tools/tests/test_ws_load_test.py` (two correlation tests added to prior work)
- `docs/benchmark-harness.md` (correlation documentation added to prior work)
- `docs/backend-pipeline-instrumentation.md` (new)
- `docs/backend-pipeline-instrumentation-validation.md` (this report)

Tracked backend diff at validation: 5 files, 352 insertions, 156 deletions.
Git diff --stat excludes the new untracked helper/tests/docs and includes earlier
phase work if run over the whole repository; it is not a phase-only line count.
Whole-worktree tracked stat: 7 files, 1,386 insertions, 291 deletions, including
earlier harness work and the unrelated pre-existing `COLLAB_LOG.md` diff.
New helper/runner/instrumentation tests have 201/96/679 lines respectively;
event documentation has 259 lines. These untracked files are absent from Git's
tracked stat. They are pending local work, not committed/deployed changes.
Earlier `tools/tests/test_ws_load_test_local.py` and Phase 2 validation report
were not edited. Neither were earlier Phase 2 reports/manifest artifacts.

`COLLAB_LOG.md` was already dirty and is excluded from this phase. Its SHA-256
before/after remains:
`F1529DD297787110A802D89E4F419F7076DBB616F75E612C80F0C430312DF5B5`.

## Not measured or verified

No real benchmark, AWS request, wake, infrastructure collector or Logs Insights
query execution occurred. WebSocket connection latency, first partial/final
caption arrival, meaningful client successful-session rate, unexpected disconnect
rate and received throughput still require client measurements. ECS CPU/memory,
scale-to-zero lifecycle and cold-start duration require separately authorized
infrastructure observations. Logging CPU/latency/cost overhead is unmeasured.

CloudWatch ingestion/deduplication and percentile results remain unverified.
Existing dual stdout/Watchtower ingestion can require choosing one source.
Logging is best effort, with no durable event guarantee. Backend success and send
completion are not acknowledgements of client delivery. Early invalid language/
room responses have no new admission row; use client attempts as the denominator.
These limits are documented rather than replaced with invented measurements.
