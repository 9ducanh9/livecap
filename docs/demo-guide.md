# LiveCap Demo Guide

Use this guide for a short reviewer-facing demonstration of the deployed MVP.

## Before the Demo

1. Open the [LiveCap production site](https://livecap.logantai.com/).
2. Select **Open workspace** or open
   [the caption workspace](https://livecap.logantai.com/app) directly.
3. Use a current Chrome or Edge browser and allow microphone access when asked.
4. Keep the first sentence short and speak clearly in either English or
   Vietnamese.

The backend normally scales to zero while idle. The first **Start session**
after an idle period invokes `/api/wake`, waits for ECS health, and can take
roughly 30-60 seconds. A direct health request may return `503` until wake-up is
complete; that is expected during scale-to-zero.

## Three-Minute Walkthrough

1. **Landing page:** Explain that LiveCap provides real-time bilingual meeting
   captions and that the page introduces the product and runtime flow.
2. **Open workspace:** Enter `/app` and confirm the header reports `READY`.
3. **Start session:** Select **Start session**. The UI reports `WAKING` while the
   Lambda sets the ECS service desired count to one and the frontend polls
   `/api/health`. Allow microphone access when prompted.
4. **Speak:** Use a sentence such as:
   `Live captions are working correctly for the final project demonstration.`
5. **Verify captions:** Wait for a finalized row. The original English text and
   Vietnamese translation should appear side by side. Partial text is shown in
   the live area but is not appended to the final transcript.
6. **Stop:** Select **Stop session** and confirm the session returns to an idle
   state.
7. **Download:** Select **Download text**. LiveCap stores only the finalized
   transcript in the private transcript bucket and downloads the time-limited
   TXT export.

## Architecture Talking Points

- Use the [as-deployed architecture](as-deployed-architecture.md) for the live
  request path.
- The React/Vite frontend is stored in private S3 and served by CloudFront
  through Origin Access Control.
- CloudFront WAF protects the public edge. CloudFront routes `/api/wake` to an
  IAM-protected wake Lambda and routes `/api/*` plus `/ws/*` to the ALB.
- The public ALB spans two Availability Zones, uses HTTPS, and has a separate
  regional WAF. Direct ALB access is restricted.
- The FastAPI task runs on ECS Fargate in one of two private subnets without a
  public IP. Outbound AWS calls use the NAT Gateway.
- The backend streams PCM audio to Amazon Transcribe and sends finalized text
  to Amazon Translate.
- Exported TXT transcripts use S3 retention of 14 days. Raw audio is not stored.
- CloudWatch receives backend logs and operational metrics; the dashboard
  covers ECS, ALB, Lambda, and WAF activity. Terraform-managed log groups use
  14-day retention, while the direct Watchtower log group still needs a
  retention policy.
- ECR images use immutable Git SHA-derived tags. GitHub Actions verifies the
  backend, frontend, Terraform, and secret scan without deploying automatically.

## Scale and Availability

- Wake Lambda changes ECS desired count from zero to one.
- Five minutes after the last active session ends, the backend requests scale
  down from one to zero unless a new session starts.
- Maximum capacity is one because the active-session registry is in memory.
- ECS replaces a failed task and the ALB waits for a healthy target before
  routing. This is self-healing, not active-active high availability; a task
  failure interrupts the current WebSocket session.
- The single NAT Gateway is a deliberate cost/availability tradeoff. ALB, NAT,
  and WAF continue to incur baseline cost when ECS is at zero.

## Fast Recovery

- If `WAKING` exceeds the configured 120-second timeout, reload `/app` and retry.
- If microphone permission is denied, allow it in browser site settings and
  reload `/app`.
- If the WebSocket closes, LiveCap retries three times with 1, 2, and 4 second
  backoff. If all retries fail, stop and restart the session.
- If no finalized caption appears, stop the session and retry with a shorter
  sentence in a quiet environment.

## Verified Baseline

On 2026-07-14, the production path passed wake `0 -> 1`, health polling, real
16 kHz PCM transcription, English-to-Vietnamese translation, ping/pong, clean
session end, S3 export, presigned TXT download, idle `1 -> 0`, and ECS task
replacement. GitHub CI also passed its Backend, Frontend, Terraform, and Secret
scan jobs.
