# Phase 2: harness diff review and local/mock validation

Validated on 2026-10-02 (Asia/Saigon), against the uncommitted harness in the
`b8a51ad492d514252a0ff4e0ca6968d4c864b47e` checkout. This is a correctness report.
Generated PCM, mock captions, mock tokens and deliberately injected delays are
**not LiveCap performance evidence and must not be used as CV numbers**.

## Scope and review findings

Reviewed the tool diff, its tests and measurement definitions. Checked protocol
assumptions against `backend/app/routers/websocket.py`, `backend/app/models.py`,
`backend/app/services/transcription.py` and `backend/app/utils/audio.py`, without
starting the backend or changing it. Session UUIDs, segment IDs, language/text
fields, PCM shape and zero timestamp fallback match these current sources.

Three client issues were reproduced and corrected:

| Finding | Reproduction and impact | Correction |
|---|---|---|
| Deprecated close-exception attributes | Real abrupt localhost disconnect, with warnings treated as errors, produced `client_error` / `DeprecationWarning` instead of `unexpected_disconnect` | Use transport close information and the modern `rcvd` close frame; do not read deprecated WebSocket exception `code`/`reason` |
| Close verdict lost during drain/cleanup | Mock server sent final, `session_end`, then abnormal close code 1011; receiver cancellation could leave the attempt classified `success` | Retain the transport's abnormal close verdict during cleanup, plus safe close reason; preserve an already observed remote close snapshot |
| Refusal recorded as a disconnect | A `ConnectionRefusedError` before socket creation still populated close offsets and set `unexpected_disconnect` | Classify it as `admission_error`, retain the safe exception type, and leave socket-close observations absent |

All three have offline regression tests. The real loopback suite additionally
verifies abrupt disconnect, close-after-end and connection refusal. No unresolved
blocking measurement defect was observed within the coverage below.

## Independent checks

The new `tools/tests/test_ws_load_test_local.py` uses the installed WebSocket
library and real TCP on **127.0.0.1 only**, with ephemeral ports. Its connection
guards reject non-loopback destinations. It never imports or starts LiveCap's
backend, an AWS SDK, or a Cognito client, and never calls `/api/wake`.

| Area | Validation oracle | What remains outside this validation |
|---|---|---|
| Handshake and admission | Independently tap connect invocation/return and receipt of `session_start`; inject distinct handshake/admission delays and compare durations within 2 ms | TLS, public DNS/network, ALB, actual Cognito JWT verification |
| First partial/final | Independently record received messages; ignore empty source partial; prove the first partial and final arrive before server receipt of stop | Actual ASR, speech onset detection, browser rendering |
| PCM and pacing | Server counts/hashes received bytes; verify 3200/3200/1600-byte frames, complete 250 ms generated fixture, fixed 0/100/200 ms schedule and stop after sample span | A capacity or real-time guarantee under production contention |
| Finalized-caption lag | Check actual frame timeline at exact timestamp boundary; retain duplicate final rows; missing and zero end timestamps remain unavailable/invalid | Provider timestamp accuracy; separate translation/buffering/network durations |
| Outcomes and rates | Mixed success/auth/limit/quota/Transcribe/translation/drop cases; independently recount outcomes and attempted/admitted denominators | Real quota/limits policy or provider behavior |
| Barrier/concurrency | No admitted sender reaches server before all applicable admission verdicts; peak admitted sockets and final zero-active observation checked | Number of provider streams or backend registry entries |
| Deadlines and protocol failure | Admission timeout, first-caption timeout before full audio/stop, shutdown timeout after full audio/stop, missing final, early end, HTTP 503, malformed JSON, absent auth negotiation, refusal | Actual cold start or service readiness |
| Aggregation | Independently recompute count/missing/min/mean/max, nearest-rank percentiles, partial/final throughput and PCM byte throughput from raw results | Statistical confidence from representative performance samples |
| JSON/CSV and CLI | Round-trip JSON; verify attempt/segment CSV rows, warmup visibility, token/transcript absence; run actual CLI `main()` with anonymous silent and authenticated WAV success, plus auth rejection exit code 1 | Process interruption durability or a transaction covering all three output files |

Offline tests cover exact fake-clock pacing/timing/mapping values, bounded WAV
reads and mutation/format validation, output collisions, redaction and atomic
replacement failures. Local tests correlate admitted attempts using session UUIDs;
TCP accept order is not assumed to equal client launch order.

## Reproduce safely

Use the repository root and existing backend virtual environment. No package
installation, service deployment or real-provider account is needed. Runtime
tested here: Python 3.14.2, websockets 16.1.1. Python 3.11 grammar was checked;
execution on Python 3.11 was not tested. No Python lint/type configuration was
found for this tool; the repository's Python CI uses compile and pytest.

Offline-only default (all socket connections forbidden in offline tests):

```powershell
Remove-Item Env:LIVECAP_RUN_LOCAL_VALIDATION -ErrorAction SilentlyContinue
& backend/.venv/Scripts/python.exe -B -W error -m unittest discover -s tools/tests -q
```

Opt in explicitly to the mock server's local sockets:

```powershell
$env:LIVECAP_RUN_LOCAL_VALIDATION = '1'
& backend/.venv/Scripts/python.exe -B -m pytest tools/tests -q -p no:cacheprovider -W error
```

Optional `LIVECAP_LOCAL_VALIDATION_OUTPUT_DIR` saves redacted JSON/CSV extracts
under per-test folders; otherwise they are checked in disposable temporary
folders. Every saved run is labeled `mock-validation-not-performance` in metadata.
The CLI path uses a dedicated fake-token environment name and does not read a
real Cognito token. Timing tolerances allow local OS scheduling noise; raw reports
retain observed timing rather than substituting the deliberately injected delays.

## Verification result and remaining boundaries

Final result: **57 offline tests + 9 loopback tests passed, plus 13 pytest
subtests**, with `-W error`. Offline-only discovery passes with the 9 loopback
tests skipped. Source compilation, Python 3.11 grammar parsing and
`git diff --check` pass.

Client timestamps measure the documented client timeline: the audio origin is
the scheduled start of sample zero, including leading silence and any initial
sender/file-read delay; frame records separately retain actual send start and
pacing drift. Whole-frame interpolation is an approximation and can yield a
negative lag; no clamping or fake zero is applied. Throughput includes ramp,
admission, barrier, streaming, draining and cleanup. Warmups remain separate in
the measured summary and visible in overall results. Raw failures are retained.

This validates the measurement machinery under controlled cases, not actual
LiveCap/Cognito/ASR/translation correctness, reliability, throughput or capacity.
Real speech, representative fixtures, long sessions, deployment limits/quotas,
TLS/network behavior and statistical confidence still need a separately
authorized isolated benchmark. Translate API latency, backend queue/provider
timing, ECS CPU/memory and cold-start phases still require backend/AWS telemetry.

No production/preview/public connection, AWS request, wake, backend/Terraform
change, stage, commit or push occurred. `COLLAB_LOG.md` retains its initial
SHA-256 `F1529DD297787110A802D89E4F419F7076DBB616F75E612C80F0C430312DF5B5`.
