# Backend pipeline instrumentation

This phase adds structured JSON log observations, not performance results.
No AWS, production, preview, wake endpoint or real benchmark is exercised by
this implementation or its validation. No Terraform, custom CloudWatch metrics,
EMF, metric dimensions, frontend, auth contract or database schema is changed.
The client harness change is limited to sending benchmark correlation metadata.

## Correlation and common schema

The harness sends `benchmark_run_id` as a WebSocket query parameter. `--run-id`
is authoritative over any value in the input URL. A missing CLI ID becomes one
UUID before all warmup/measured attempts. Only IDs matching
`[A-Za-z0-9._-]{1,64}` are sent; known token values/JWT-looking IDs are excluded.
Backend validation uses that exact regex without trimming. Missing/invalid IDs
become JSON null, without rejecting a session. Use an opaque nonsecret ID; a
format check cannot establish that a syntactically valid identifier is nonsecret.
The ID is never added to WebSocket responses or CloudWatch metric dimensions.

All seven new events include:

| Field | Meaning and nullability |
|---|---|
| `schema_version` | `1.0` |
| `event` | One of the seven names below |
| `timestamp` | Logger-created UTC wall-clock timestamp; never subtracted for duration |
| `benchmark_run_id` | Validated client run ID, otherwise null |
| `session_id` | Existing UUID session identifier, otherwise null before resolution |
| `segment_id` | Validated `seg-N` or `vi-seg-N`/`en-seg-N`; null for events without a segment; dual provider IDs are prefixed to match outgoing IDs |
| `stream_mode` | Actual backend `single`/`dual`, null when unavailable |
| `source_language`, `target_language` | Configured language mode, null when unavailable; dual stream events additionally identify the actual `stream_language` |
| `success` | Boolean event outcome, not an assertion that a client received a caption |
| `duration_ms` | Monotonic `time.perf_counter()` difference in milliseconds; null for receipt, skipped operations, aggregate partial sends and terminal events |
| `error_type` | Exception class only; null for success or a rejection/empty SDK result without an exception |
| `asyncio_task` | Existing default task name `Task-N`, null outside a task or for arbitrary custom names; local context, not an ECS task identifier |

The logger also supplies `level`, `logger` and a fixed event-name `message`.
No ECS task metadata is available in the existing logging context; no metadata
endpoint lookup or new AWS call is added. Run/session/segment IDs are log fields
only. Unknown extra fields and invalid enums/identifiers are omitted or nulled.
Nonfinite numeric values become null. No token, audio, transcript, confidence,
email, IP, Cognito user ID, arbitrary close reason, exception message or traceback
is added to these events. Legacy transcript/IP/user-ID/error-message logging in
the touched pipeline is removed. Existing JSON exception formatting and the
integration-error helper now retain exception classes instead of tracebacks.
This does not claim a privacy audit of unrelated routes or third-party logs.

## Events and measurement boundaries

| Event | Exact start | Exact end | Metadata and interpretation |
|---|---|---|---|
| `websocket_admission_completed` | Router entry, before settings/session/language parsing and WebSocket accept | Admission/rejection decision after auth/admin/registry/quota steps | `auth_duration_ms`: authentication call; `admin_check_duration_ms`: before `to_thread` until return, including its queue wait; `registry_duration_ms`: registry acquisition plus `try_register`; `quota_duration_ms`: quota reservation path; `total_admission_duration_ms` equals `duration_ms`. Unexecuted stages are null. Total includes other router work and need not equal the sum. |
| `transcribe_stream_started` | Immediately before constructing the existing Transcribe client | `start_stream_transcription` returns a ready stream, or raises | One observation per stream-open attempt; `stream_language` distinguishes vi/en in dual mode. Includes local client/open overhead; not pure AWS processing latency. |
| `transcribe_result_received` | Receipt/processing entry for a provider result | No duration endpoint: this is a receipt observation | Each usable final logs `aggregate=false`, `is_partial=false`, segment ID, audio-relative `timestamp_start/end` and `backend_received_offset_ms` since admitted session start. Partial revisions increment a counter and emit one `aggregate=true`, `is_partial=true`, `partial_count` summary per stream with partials; per-partial IDs/timestamps are unavailable. Empty alternatives/text follow existing filtering. |
| `translation_operation_completed` | Public translation operation entry; module wrapper includes lazy client acquisition; direct service calls start at service method entry | Async SDK result/error/cancellation observed, before logging and constructing the returned model | `direction`; `duration_ms` total operation. `executor_queue_duration_ms`: immediately before executor submission to worker entry. `sdk_call_duration_ms`: immediately before `translate_text` to return/raise, including SDK retries, serialization, network and response handling. Not AWS-only latency. Missing boundaries are null. |
| `arbitration_or_buffer_completed` | Dual candidate creation, or single fragment added to buffer | Candidate emitted/dropped by arbitration, or fragment included in a buffer flush/drop | `kind=dual_arbitration/single_buffer`, `outcome=emitted/dropped`; safe closed-enum drop `reason` where available. Duration includes residence/wait, not just CPU computation. A merged buffer output can correspond to several fragment observations. Selection, queues and windows are unchanged. No single-buffer observation exists when that buffer is bypassed. |
| `websocket_caption_send_completed` | Before caption serialization and `send_text` | Local send returns/raises | Finals: one `aggregate=false`, `kind=final` event with equal `duration_ms`/`send_duration_ms`. Partials: one terminal aggregate with attempt/success/failure counts, `duration_sum_ms` and `duration_max_ms`; `duration_ms` is null. No per-partial percentiles can be reconstructed. A successful send is not a delivery acknowledgement. |
| `websocket_session_outcome` | Just after admission logging, before `session_start` send | Router finally, after teardown, registry release/scheduling and socket close attempt | Exactly one emission attempt for each admitted router invocation; `session_duration_ms`, counters, terminal outcome, `session_end_send_success`, safe integer `close_code`; `close_reason` currently always null. Nonadmitted invocations emit no terminal event. |

Admission outcomes are `admitted`, `auth_rejected`, `limit_rejected`,
`quota_rejected`, `store_error`. Existing quota-store fail-open behavior is
preserved: its admission event has `outcome=store_error`, `success=false`,
`admitted=true`, and `quota_error_type`; it can still have a terminal event.
Other store errors propagate unchanged, without an admitted terminal event.
Early invalid-language or invalid-room responses occur before the observed
auth/registry/quota admission decision and currently have no new admission
event; the client harness remains the attempt/rejection denominator.

Translation outcomes are `translated`, `failed`, `skipped_empty`, `cancelled`.
Empty input performs no Translate call and has null durations. Empty SDK output
is `failed` with null `error_type` and the same returned payload as previously.
Cancellation propagates unchanged; a worker may continue an already-started
blocking SDK call. Its unfinished SDK duration is null at cancellation and is
not later reported as completed. Exclude skipped/cancelled events from completed
operation latency samples. Failures retain real elapsed durations when observed,
and should be reported separately from successful samples.

Terminal outcomes are exclusive, using this precedence when multiple failures
are observed: `internal_error`, `transcribe_failed`, `timeout`,
`client_disconnect`, `send_failed`, `translation_degraded`, otherwise `success`.
Disconnect wins over send failure caused by subsequent teardown. Invalid audio
uses `internal_error` in this taxonomy; its client error contract is unchanged.
Backend `success` means no failure was observed, even for an empty session. It
does not prove a meaningful caption was produced or received. Use the client
harness's audio/caption/completion criteria for a successful-session CV claim.

Counters are precisely:

- `audio_frames_received`/`audio_bytes_received`: binary frames/payload bytes
  observed by the reader before format validation, including rejected frames.
- `partial_count`/`final_count`: outbound caption send attempts, including
  failed sends; not unique segment counts or received captions.
- `translation_success_count`: completed nonempty-input translations with
  nonempty target output. `translation_failure_count`: completed nonempty
  attempts returning an empty target or raising. `translation_skipped_count`:
  completed empty-input operations. Canceled operations are excluded from these
  completed-operation counts and appear separately in translation events.
- Room partial translations contribute to translation counts; they are not
  necessarily paired one-to-one with finalized captions.

The guard provides one terminal emission attempt per admitted invocation, even
if send fails. Logging is best effort: disabled logging, handler failure, process
termination or lost ingestion can remove events. There is no delivery retry or
exactly-once CloudWatch ingestion guarantee. Reconnection can reuse the existing
session UUID; count terminal event rows, not distinct session IDs, for backend
invocations. Client attempt IDs remain necessary for attempt-level evidence.

## Metrics that remain client or infrastructure measurements

| Metric | Required observation |
|---|---|
| WebSocket connection latency | Client clock before connect to handshake completion; admission logging begins after routing and omits DNS/TLS/ALB/client work |
| Time to first partial caption | Client audio-send anchor to first received partial; provider aggregates cannot recover the first partial arrival |
| Finalized-caption lag | Client audio timeline and segment-end mapping to final receipt; never subtract backend/client monotonic clock values |
| Translation latency visible to users | SDK/queue/operation fields describe backend stages; receipt-to-receipt differences include other work and are not isolated translation measurements |
| Successful-session rate | Client attempt denominator and explicit expected audio/caption/session-end criteria; terminal `success` alone is weaker |
| Unexpected disconnect rate | Client close observation plus expected stop/deadline/intention; backend `client_disconnect` does not identify user intent |
| Message throughput | Client received messages/bytes over a specified interval; backend final-send attempts can be binned separately, but partial terminal aggregates lose within-session timing |
| ECS CPU/memory | ECS/Container Insights or explicitly authorized infrastructure collector, not these logs |
| Cold-start duration | Separate authorized lifecycle observation from zero capacity/wake trigger to defined readiness; these stage durations begin after a request reaches the backend |

No metric collector, wake request or benchmark is added here. No measurements
from the generated/mocked test fixtures qualify as performance results.

## CloudWatch Logs Insights examples

These are unexecuted Logs Insights QL examples. Select the correct log group and
a bounded run time window; replace `YOUR_RUN_ID`. Select one ingestion path if
the same event is shipped via both stdout/ecs `awslogs` and Watchtower, otherwise
counts can be duplicated. Inspect raw rows and completeness before computing
rates. Query syntax follows the official
[AWS stats reference](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/CWL_QuerySyntax-Stats.html).

Event inventory and outcome counts:

```text
fields event, outcome, success
| filter schema_version = "1.0" and benchmark_run_id = "YOUR_RUN_ID"
| stats count(*) as event_count by event, outcome, success
```

Completed successful operations/final sends, with per-event count and percentiles
(receipt, partial aggregate, skipped and canceled rows have no eligible duration):

```text
fields event, duration_ms, stream_mode
| filter schema_version = "1.0" and benchmark_run_id = "YOUR_RUN_ID"
| filter success = true and ispresent(duration_ms)
| stats count(*) as samples, avg(duration_ms) as avg_ms,
        pct(duration_ms, 50) as p50_ms, pct(duration_ms, 95) as p95_ms,
        pct(duration_ms, 99) as p99_ms by event, stream_mode
```

To isolate emitted arbitration/buffer residence, additionally filter
`event = "arbitration_or_buffer_completed" and outcome = "emitted"` and group
by `kind`. Dropped events currently also use `success=true` because the drop
decision completed normally; do not mix their durations with emitted candidates.
To isolate final sends, filter `event = "websocket_caption_send_completed" and
aggregate = false`. The same count/avg/pct pattern applies to each numeric
admission stage; filter out null/unexecuted stages first.

Translation split (completed successful calls only):

```text
filter schema_version = "1.0" and benchmark_run_id = "YOUR_RUN_ID"
| filter event = "translation_operation_completed" and outcome = "translated"
| filter success = true and ispresent(sdk_call_duration_ms)
| stats count(*) as calls, avg(duration_ms) as avg_operation_ms,
        pct(duration_ms, 50) as operation_p50_ms,
        pct(duration_ms, 95) as operation_p95_ms,
        pct(duration_ms, 99) as operation_p99_ms,
        avg(executor_queue_duration_ms) as avg_queue_ms,
        avg(sdk_call_duration_ms) as avg_sdk_ms,
        pct(sdk_call_duration_ms, 50) as sdk_p50_ms,
        pct(sdk_call_duration_ms, 95) as sdk_p95_ms,
        pct(sdk_call_duration_ms, 99) as sdk_p99_ms by direction
```

Backend terminal outcomes and durations (not client successful-session rate):

```text
filter schema_version = "1.0" and benchmark_run_id = "YOUR_RUN_ID"
| filter event = "websocket_session_outcome"
| stats count(*) as invocations, avg(session_duration_ms) as avg_ms,
        pct(session_duration_ms, 50) as p50_ms,
        pct(session_duration_ms, 95) as p95_ms,
        pct(session_duration_ms, 99) as p99_ms by outcome
```

Partial-send weighted average, not a distribution or percentile:

```text
filter schema_version = "1.0" and benchmark_run_id = "YOUR_RUN_ID"
| filter event = "websocket_caption_send_completed" and aggregate = true
| stats sum(attempt_count) as attempts, sum(success_count) as successful_sends,
        sum(failure_count) as failed_sends,
        sum(duration_sum_ms) / sum(attempt_count) as weighted_avg_ms,
        max(duration_max_ms) as max_ms
```

Final local send attempts and failures per minute:

```text
filter schema_version = "1.0" and benchmark_run_id = "YOUR_RUN_ID"
| filter event = "websocket_caption_send_completed" and aggregate = false
| stats count(*) as final_send_attempts by bin(1m), success
```

## Log volume and overhead estimate

For an admitted invocation, added event count is
`2 + S + P + Q + R + A + T + F`, where:

- `2`: admission plus terminal event;
- `S`: stream-open attempts (normally one single or two dual);
- `P`: streams with a partial-result summary (at most one per stream);
- `Q`: one partial-send summary if any partial send was attempted, otherwise zero;
- `R`: usable provider final results;
- `A`: arbitration/buffer emitted/dropped fragment decisions;
- `T`: translation operations, including skipped/canceled and room partials;
- `F`: final caption send attempts.

This is an implementation-derived count estimate, not measured performance.
There is no event proportional to audio-frame count or partial-revision count.
If using dual streams, `R` and `A` can exceed emitted captions because one
provider's candidate is dropped. Existing fixed lifecycle/integration error logs
are additional to the formula. Per-frame debug/fanout logs in this pipeline are
removed even when `audio_pipeline_debug` is enabled. No debug flag behavior
outside the pipeline is changed.

Hot-path overhead is counters per binary frame, clock/counter updates per partial,
and clock/schema/JSON/handler work per logged final or pipeline operation. The
existing logging transport is reused; no new client, SDK call, synchronous AWS
operation, metric upload, executor, queue or retry is introduced by telemetry.
Logging handlers still have real local cost and existing transport behavior.
Actual CPU overhead, added bytes/session, ingestion cost and latency overhead
remain unmeasured; quantifying them requires a separately authorized comparison.

## Offline validation

Run from `backend` with its installed dependencies:

```text
.venv/Scripts/python.exe -B tests/run_pipeline_offline.py tests -q -p no:cacheprovider
```

The runner substitutes dummy AWS credentials, disables metadata credentials,
blocks application DNS/connect/sendto and fails if a blocked attempt is observed,
even if an old test swallows the exception. It allows only Windows CPython's
internal `_fallback_socketpair` bootstrap. Tests use mocked providers and ASGI/
in-memory WebSockets, not a real backend or public/local WebSocket server.
Existing app startup Watchtower initialization is mocked. An SDK fixture supplies
an empty DynamoDB audit query in an unrelated legacy admin test that lacked a
mock; individual test mocks still override it. Neither substitution validates
CloudWatch ingestion or DynamoDB service behavior.

The default client unit suite may also run; its opt-in real loopback suite is
excluded in this phase because this objective forbids real network tests.
See the validation report for actual checks, outcomes and remaining limits.
