# LiveCap Recorded-Audio Benchmark — 2026-10-03

## Scope and method

An isolated Singapore environment ran one ECS Fargate task (0.5 vCPU, 1 GiB)
with Cognito authentication, dual English/Vietnamese Transcribe streams, and
Vietnamese translation. The client replayed a 33.623-second recorded Harvard
speech sample from the Open Speech Repository, resampled from 8 kHz to 16 kHz.
There were three measured runs at each concurrency level (1, 2, and 4), nine
runs and 21 attempted sessions in total. Each session sent the full recording.
There were no generated-speech sessions, warmup sessions, or session retries.

| Concurrent sessions | Successful / attempted | First partial p50 | Finalized-caption lag p50 | Translation operation p50 |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 3/3 | 1.676 s | 2.043 s | 35.51 ms |
| 2 | 6/6 | 1.686 s | 2.064 s | 95.50 ms |
| 4 | 12/12 | 1.686 s | 2.125 s | 93.95 ms |

First-partial and connection metrics use 3/6/12 session samples across these
stages. Finalized-caption lag uses 30/60/120 segment samples, and translation
operation uses 30/60/120 calls. Segments and calls within a session are
correlated, so those counts are not independent session samples. These are
nearest-rank percentiles; the small session sample does not establish a stable
p95 or p99.

First partial starts at the first PCM sample sent and includes leading silence.
Finalized-caption lag maps the provider segment end to the corresponding
client frame-send time. Translation operation includes SDK, network, and
executor work. The throughput window includes admission and caption drain.
ECS CPU/memory values are 60-second service aggregates, including idle overlap,
not resource usage attributed to individual sessions.

## Outcome and limits

All nine runs passed their client/backend gates. All 21 sessions completed,
with no unexpected disconnects observed in this bounded sample. At four
concurrent sessions, first-partial p50 was 1.69 s across 12 sessions and
finalized-caption lag p50 was 2.13 s across 120 correlated segments.

The coordinator was interrupted after run 2. The task was restarted before run
3 and again before run 7 after collector credentials expired. Every measured
session began after readiness, but the campaign covers **three warm task epochs**.
The original condition of one continuously warm task across all nine runs was
not met. The user accepted this disclosed deviation for the existing campaign.

This experiment does not measure cold starts, speech accuracy/WER, maximum
sustained capacity, production reliability, or incremental billed cost. It is
also not a before/after optimization study: changes between concurrency stages
must not be described as performance improvements.

The run-level client CSV/JSON, matched backend events, ECS minute metrics,
fixture/source provenance, and SHA256 manifest are retained in the private
benchmark archive. The same archive records teardown: 41 Terraform-managed
benchmark resources were destroyed, orphan checks passed, and benchmark DNS
records were removed. Archived state and raw evidence are intentionally not
published in this repository.

Source attribution: [Open Speech Repository, American English recordings](https://www.voiptroubleshooter.com/open_speech/american.html).
