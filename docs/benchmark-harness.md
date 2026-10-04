# Client benchmark harness (Phase 1)

`tools/ws_load_test.py` is a client measurement harness, not a capacity claim.
Phase 1 adds no backend instrumentation, Terraform, environment provisioning,
AWS collector, wake request, or production/preview benchmark. Tests use generated
PCM and fake WebSockets solely to verify correctness. Their output is not
performance evidence and must not be used in a CV.

Opt-in loopback WebSocket validation against a mock server is implemented in
[`tools/tests/test_ws_load_test_local.py`](../tools/tests/test_ws_load_test_local.py).
Those generated captions/audio and controlled delays remain validation fixtures.

## Run authorization and prerequisites

No real load test is authorized by this phase. Do not run this tool against
production, preview, or any public URL. Examples below describe future local
use only; they were not executed as part of implementation. A local backend may
itself call AWS, so separately approve any real-provider run and its resources.

For a future run, install the `websockets` package in the selected Python
environment (Python 3.11+). Record its version; the report includes it. Backend
readiness is the operator's responsibility: this tool does not call `/api/wake`,
poll health, query ECS or bypass limits. Preview currently shares session/quota
resources with the stable service, so a different URL alone is not isolation.

Legacy anonymous silent invocation remains supported:

```powershell
python tools/ws_load_test.py --url ws://localhost:8000/ws/transcribe --concurrency 1 --duration 8 --ramp 0.2 --no-auth
```

Future speech invocation, once the local run is separately authorized:

```powershell
python tools/ws_load_test.py --url ws://localhost:8000/ws/transcribe --auth --audio-file C:/fixtures/speech.wav --concurrency 1 --stream-mode dual --output-json C:/benchmark/run.json --output-csv C:/benchmark/run.csv --run-id local-speech --scenario warm-vi-dual
```

These are commands, not measured results. Choose concurrency and account usage
within the environment's limits. Do not spoof forwarded IPs or disable guards
to turn an admission-policy result into a capacity benchmark.

## Authentication and privacy

- Default token environment variable: `LIVECAP_ACCESS_TOKEN`. Override its name
  with `--token-env NAME`; obtain the access token through the normal authorized
  sign-in flow. No password/token value is accepted as a CLI option.
- A nonempty token enables auth automatically. `--auth` explicitly requires it
  and fails preflight if empty. `--no-auth` explicitly selects anonymous mode.
- The handshake passes `subprotocols=["livecap.v1", access_token]`. The token is
  never appended to a URL or exported in configuration metadata. Auth mode
  requires the server to negotiate `livecap.v1` before streaming; an anonymous
  server ignoring the protocols does not count as authenticated admission.
- CLI abbreviation is disabled (`--token` cannot alias `--token-env`), and
  parser errors do not echo arguments. URLs reject credentials, fragments and
  query keys other than `source`, `target`, `stream_mode`, `benchmark_run_id`. An exact environment
  token in the target URL also fails preflight.
- Output target URL drops credentials/query/fragment. Exact secrets, encoded
  forms and JWT-like strings are redacted recursively before JSON/CSV/console
  output. Exception diagnostics retain type only; arbitrary server error text,
  unknown error-code text, and transcripts are never retained in results.
- Segment IDs accept the current `seg-N`, `vi-seg-N`, `en-seg-N` contract.
  Session IDs must be UUIDs. Unknown ID text is not exported. Source/target
  columns become presence booleans, not text. Arbitrary close reasons are
  omitted (`[OMITTED]`); known protocol reasons or redaction markers are safe.
- A private disabled logger is passed to the transport library, so enabling
  debug logging elsewhere does not echo the subprotocol token in headers.

The access token is still transmitted to the WebSocket endpoint as a header.
Use an authorized endpoint and normal TLS verification. `--insecure` is retained
for compatibility and recorded in metadata; it changes the measurement setup.

## Audio validation and replay

With no audio file the default is `silent`. It sends zero-filled signed 16-bit
mono PCM at 16 kHz. `--duration` controls its audio sample span (rounded up by at
most one sample), with 100 ms frames and a shorter final frame when necessary.
Silent success tests admission/stream lifecycle; no caption latency statistics
are reported. Uniform raw attempt fields for caption metrics remain null.

`--audio-file` infers `wav`; explicit `--audio-mode wav` also requires that file.
`--audio-mode silent` cannot be combined with a WAV file. WAV preflight rejects
non-mono, non-PCM, non-16-bit, non-16-kHz, empty and truncated input. It hashes
the full file with SHA-256 and validates the entire payload using bounded reads.
Each session opens its own streaming reader; the complete WAV is not loaded
into memory. PCM is hashed during replay too: a changed payload cannot pass the
full-audio contract. WAV mode always replays the entire fixture; `--duration`
does not truncate it. Metadata distinguishes actual duration and requested
silent duration. Only the audio basename, not its absolute path, is exported.

For frame beginning at sample `s`, the fixed schedule is:

```text
scheduled_send = audio_origin + s / 16000
sleep = max(0, scheduled_send - monotonic_now)
pacing_drift_ms = (actual_send_start - scheduled_send) * 1000
```

There is no cumulative `send-time + sleep(0.1)` drift. Late send attempts use
the original schedule, so backlog can cause closely spaced sends; reported
drift reveals that replay did not keep real time. The sender waits until the
last frame's scheduled sample span ends before sending stop. Every attempted
frame records sample range, scheduled/actual send start, send completion and
whether the send succeeded. Pacing drift includes observed failed send attempts;
byte/frame throughput counts only sends that completed. No timing is invented
for frames never attempted. Per-attempt max/p95 and global sample counts are
included. Frame timing records grow with duration, but PCM buffering is bounded.

## Concurrency, lifecycle and deadlines

`--concurrency` is the number of measured attempts. `--ramp` spaces connection
attempts for admission-policy scenarios. After admission, each receiver starts
immediately, including while waiting at the start barrier. Audio senders start
after every measured attempt has either been admitted or failed admission.
Rejected/timed-out attempts still arrive at the barrier, so they cannot strand
successful peers. Actual starts are close, not guaranteed simultaneous; raw
audio-start offsets disclose scheduling skew.

`observed_active_sessions` is a time series of admitted sockets still observed
open by the client, including sockets waiting at the barrier. Its maximum is
`peak_observed_concurrency`. This is not the number of coroutines, a backend
registry count, a streaming-only gauge or a capacity guarantee. Decrements occur
on observed close or local cleanup. Each attempt retains its own terminal result
even if another connection fails. No automatic retry/reconnect occurs.

`--warmup-sessions N` runs N sequential full sessions using the same audio and
auth settings before measured attempts. It does not wake ECS. Warmups can consume
quota and real-provider cost. Raw warmup records and `warmup_summary` are kept;
the measured `summary` excludes warmup samples deliberately. `overall_summary`
includes **all** attempts and failures. CSV records include a `phase` column.

Deadlines (seconds, finite and positive):

| Option | Scope |
|---|---|
| `--connect-timeout` | One total deadline for transport handshake plus first admission message |
| `--first-caption-timeout` | WAV only, from audio start to first nonempty source partial or valid final; unrelated/control messages do not reset it |
| `--send-timeout` | Each audio/stop send, including backpressure after a first caption |
| `--shutdown-timeout` | Total stop-to-session-end wait; incoming messages do not reset it. Also bounds socket cleanup |

Per-attempt offsets expose attempt start, handshake completion, `session_start`,
audio start/end (including canceled streams), completed stop send, `session_end`
and socket close. Stop initiation is recorded separately from send completion;
the end-after-stop flag uses initiation, allowing a fast backend reply while
the send is still completing. `attempt_start_offset_ms` is relative to the measured or warmup
phase origin. All other attempt/frame/segment offsets are relative to that
attempt's start. UTC timestamps provide run-level wall-clock correlation;
durations use `time.monotonic()`.

## Client metric definitions

| Metric | Definition |
|---|---|
| `transport_handshake_ms` | Immediately before connect invocation to socket returned; includes DNS/TCP/TLS/upgrade |
| `session_admission_ms` | Handshake complete to receipt of `session_start` |
| `connect_to_session_start_ms` | Attempt start to receipt of `session_start`; preserves the old combined "connect" meaning under an accurate name |
| `time_to_first_partial_ms` | Audio timeline origin to first partial with nonempty source text |
| `time_to_first_final_ms` | Audio timeline origin to first valid final |
| `finalized_caption_lag_ms` | Final receipt minus mapped end of its audio; mapping below |
| `bytes_sent` | Completed PCM payload bytes only, excluding stop, TLS and WebSocket framing |
| `audio_seconds_sent` | Completed PCM bytes / 32000; measures submitted audio, not backend processing |
| `audio_seconds_scheduled` | Planned complete fixture/silence sample span, even if the attempt later fails |
| message counts | All received application messages: partials + finals + control; handshake frame is not an application message |
| unique finals | Distinct valid-format segment IDs per attempt; duplicate final messages still have separate raw rows |
| throughput | Partial/final message counts and PCM bytes divided by the measured phase wall time, including ramp, admission, barrier, stream, drain and cleanup |

Audio origin is the **first PCM sample**, not automatically detected speech onset.
Leading silence is included in first-caption metrics. Use a fixture with a known
speech onset, or report this as time from audio start. Python receive time does
not include browser rendering or microphone capture latency.

### Finalized-caption lag mapping

For end offset `u` seconds, find the completed send frame that contains that
sample and whose actual send began before receipt of the final. At an exact
boundary choose the preceding frame. Reconstruct its actual replay timeline:

```text
mapped_audio_end = frame.actual_send_start + (u - frame.sample_start / 16000)
client_observed_lag = client_receive_final - mapped_audio_end
```

This is a **client-observed finalized-caption lag** using the actual frame-send
timeline, including ASR, buffering/arbitration, translation and network. It is
not Translate API latency or an independent backend duration. Sending whole
100 ms chunks is not a physical sample-by-sample microphone clock; within-frame
timing is reconstructed. Send queue delay, scheduling drift and server buffering
affect it. Negative values remain visible rather than being clamped to zero.

Missing/null/non-numeric/non-finite end timestamps produce `unavailable`. Zero,
negative, out-of-fixture offsets and invalid start/end ordering produce `invalid`.
A frame not sent at receipt produces `unavailable`. No missing value becomes zero lag.
Each final row retains ID, start/end, receipt offset, mapped end offset, lag,
lag status/reason, text-presence booleans and message validity. Timestamp validity
for lag is separate from caption message validity; neither is an accuracy score.

## Success and mutually exclusive terminal outcomes

Every attempt has exactly one final outcome, assigned after cleanup:
`success`, `auth_rejected`, `limit_rejected`, `quota_rejected`, `admission_error`,
`transcribe_failed`, `translation_degraded`, `unexpected_disconnect`, `timeout`,
or `client_error`. Admission remains an independent boolean; an admitted failure
is not counted twice. All measured failures remain in the measured denominator.

Silent success requires handshake, admission, full silence sample span, completed
stop and session-end receipt after stop within its deadline. WAV requires those
conditions plus at least one valid final (current ID format, nonempty source,
supported spoken language, finalized flag). Finals with source text but absent
target text, or an explicit `TRANSLATE_ERROR`, result in `translation_degraded`.
They are never successful bilingual sessions. This cannot measure translation
accuracy, full transcript coverage, WER or word-level correctness.

Explicit server causes take precedence: auth/limit/quota rejection, Transcribe
error, server session timeout, then other server error. Pre-admission generic
errors are `admission_error`; post-admission unclassified server/protocol errors
are `client_error` because this fixed taxonomy has no generic server-error label.
Known `server_error_codes` remain available to distinguish them. Local deadlines
and exceptions follow, then unexpected close, then the completion contract and
translation degradation. Early `session_end` before stop fails the contract.

A remote close before expected session-end or with abnormal code is unexpected,
including code 1000 before completion. A local deadline/cleanup is not fabricated
as a remote disconnect. `close_initiator`, code, safe reason and flags disclose
what was observed. A backend error can be the primary outcome while a separately
observed unexpected disconnect flag remains true. `expected_close` additionally
requires normal close code (1000/1001) after application completion.

Rates are fractions, not percentages: successful / attempted, successful /
admitted, unexpected admitted disconnects / admitted. Zero denominators yield
null. For each latency: valid/missing counts, min, mean, p50/p95/p99/max. Quantiles
use nearest rank: sort n valid values, take zero-based `ceil(p/100*n)-1`. Nulls
and non-finite values never enter statistics as zero. Small samples still expose
n; percentiles alone cannot establish reliability or a capacity limit.

## Evidence output and offline verification

`--output-json PATH` writes metadata, measured/warmup/overall summaries, raw
attempts with frame/segment records, and observed concurrency events.
`--output-csv results.csv` writes `results-attempts.csv` (one row per attempt,
including warmups) and `results-segments.csv` (one row per final message).
Missing numeric values are JSON null / CSV empty cells. `--run-id` and `--scenario`
correlate rows. JSON is the authoritative source for metadata and frame timings;
the two CSVs are flattened extracts, not complete replacements for JSON.

Backend instrumentation additionally correlates via the `benchmark_run_id`
WebSocket query parameter. `--run-id` overrides any value already in the URL;
if absent, a single UUID is generated before warmup and measured attempts.
Only `[A-Za-z0-9._-]{1,64}` IDs without the known token/JWT pattern are sent.
An invalid explicit run ID remains report metadata (subject to existing output
redaction) but is omitted from the connection query, so backend correlation is
null. Use opaque, nonsecret run IDs. URL evidence still excludes all query values.
No response fields are added. See
[backend event definitions and query examples](backend-pipeline-instrumentation.md).

Metadata includes schema version, UTC run start/end, Git SHA/dirty state (null
when unavailable), sanitized URL, languages/requested stream mode, auth mode,
requested/observed concurrency, ramp/duration/timeouts, audio basename/hash/
format, Python/websockets versions, platform and percentile/timeline methods.
Requested stream mode is not confirmation of the backend's runtime configuration.

Each file is written to a sibling temporary file, flushed/fsynced and atomically
replaced. The three-file bundle is not one filesystem transaction: keep the run
ID and report a write failure; don't silently mix files from different runs.
Output paths that collide with each other or the input WAV fail preflight.
Exit codes: 0 all measured/warmup sessions successful; 1 any session unsuccessful;
2 preflight/output error; 130 interruption. A canceled run has no claim of a
complete evidence bundle. Review dirty state before treating results as tied
to a published commit.

Offline tests (no AWS, socket connect/connect_ex/create_connection forbidden):

```powershell
python -B -m unittest discover -s tools/tests -v
```

They verify WAV format/truncation/duration/bounded replay/hash, fake-clock pacing,
percentiles and missing values, auth/redaction, simultaneous send/receive,
barrier/failure isolation, lifecycle/timeouts/outcomes, timestamp mapping,
success contracts, atomic writes and JSON/CSV privacy. They do not run the tool
against a server and their timing/caption fixtures are never benchmark evidence.

Phase 1 cannot separately measure Translate SDK/executor latency, Transcribe
provider startup, backend queue/arbitration/buffering durations, backend receive/
send throughput or failed sends, ECS CPU/memory, or cold-start provisioning/
readiness phases. Those need subsequent backend/AWS telemetry and an authorized
isolated environment. No CV performance number is established by this phase.
