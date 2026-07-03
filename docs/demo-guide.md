# LiveCap Demo Guide

Use this guide for a short reviewer-facing demonstration of the deployed MVP.

## Before the Demo

1. Open the [production health endpoint](https://dpeohr327wt9l.cloudfront.net/api/health).
   Confirm it returns `{"status":"healthy","version":"1.0.0"}`.
2. Open the [LiveCap landing page](https://dpeohr327wt9l.cloudfront.net).
3. Use a current Chrome or Edge browser and allow microphone access when asked.
4. Keep the demo sentence short and speak clearly in either English or
   Vietnamese.

## Three-Minute Walkthrough

1. **Landing page:** Explain that LiveCap provides real-time bilingual meeting
   captions and that the scroll sequence visualizes the product and runtime
   flow.
2. **Open app:** Select **Start captioning** or **Open app** to enter `/app`.
3. **Start session:** Select **Start** and allow microphone access. The browser
   opens a secure WebSocket through CloudFront and the ALB to the FastAPI task.
4. **Speak:** Use a sentence such as:
   `Live captions are working correctly for the final project demonstration.`
5. **Verify captions:** Wait for a finalized row. The original English text and
   Vietnamese translation should appear side by side. Partial text is not
   appended to the final transcript.
6. **Stop:** Select **Stop** and confirm the session returns to an idle state.
7. **Export:** Select **Export TXT**. LiveCap stores only the finalized transcript
   in the private transcript bucket and returns a time-limited download link.

## Architecture Talking Points

- The React/Vite frontend is stored in private S3 and served by CloudFront.
- CloudFront terminates the public HTTPS/WSS connection and routes API and
  WebSocket traffic to an ALB.
- The ALB forwards healthy traffic to a FastAPI container on ECS Fargate.
- The backend streams PCM audio to Amazon Transcribe and sends finalized text
  to Amazon Translate.
- Exported TXT transcripts use S3 retention of 14 days. Raw audio is not stored.
- CloudWatch receives backend logs and operational metrics; log retention is
  14 days.
- Images in ECR use immutable Git SHA tags. GitHub Actions verifies backend,
  frontend, Terraform formatting/validation, and secret scanning without
  deploying automatically.

## Current Deployment Versus Target

Be explicit during review:

- The current public demo runs one healthy Fargate task behind the existing ALB.
- CloudFront viewer traffic uses HTTPS/WSS, while its current ALB origin uses
  HTTP.
- The reviewed target Terraform adds private subnets, a NAT Gateway,
  scale-to-zero wake/idle behavior, WAF COUNT rules, a dashboard, and a budget.
- That target stack is not presented as deployed. It remains behind state
  import, Terraform plan review, and blue/green cutover gates to avoid damaging
  the working submission environment.

## Fast Recovery

- If the health endpoint is not healthy, do not start microphone capture.
- If microphone permission is denied, allow it in browser site settings and
  reload `/app`.
- If the WebSocket closes, LiveCap retries three times with 1, 2, and 4 second
  backoff. If all retries fail, stop and restart the session.
- If no finalized caption appears, stop the session, refresh the page, and retry
  with a shorter sentence in a quiet environment.

## Verified Baseline

On 2026-07-04, the production flow passed session start, real 16 kHz PCM
transcription, English-to-Vietnamese translation, ping/pong, clean session end,
S3 export, and presigned TXT download. The current CI pipeline also passed its
Backend, Frontend, Terraform, and Secret scan jobs.
