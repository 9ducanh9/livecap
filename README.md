# LiveCap

> Real-time Vietnamese-English captions and shared meeting transcripts on AWS.

[![CI](https://github.com/9ducanh9/livecap/actions/workflows/ci.yml/badge.svg)](https://github.com/9ducanh9/livecap/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/9ducanh9/livecap)](https://github.com/9ducanh9/livecap/releases/latest)

[Live demo](https://livecap.logantai.com/) | [Open app](https://livecap.logantai.com/app) | [Demo guide](docs/demo-guide.md) | [Architecture](docs/as-deployed-architecture.md)

## Test Links

- [CloudFront preview workspace](https://dsxqvhsn58xk8.cloudfront.net/app)
- [CloudFront preview room join](https://dsxqvhsn58xk8.cloudfront.net/rooms)
- [Custom domain (same deployed frontend)](https://livecap.logantai.com/app)
- Windows: double-click [`open-livecap.bat`](open-livecap.bat) from the repository root.

`open-livecap.bat` opens the preview CloudFront distribution. The stable
CloudFront distribution (`dpeohr327wt9l.cloudfront.net`) serves a different
frontend build; do not use it to compare the current custom-domain UI. Local
uncommitted changes appear only in the local dev server until deployed.

![LiveCap caption workspace](docs/livecap-dashboard.png)

## Problem

Vietnamese-English meetings lose context when captions or translations arrive
late. LiveCap turns microphone audio into bilingual text while the conversation
is happening and keeps finalized transcripts available after the room closes.

## How It Works

The React client sends 16 kHz PCM through WebSocket to FastAPI on ECS Fargate.
Amazon Transcribe produces Vietnamese captions, Amazon Translate creates the
English text, and finalized records are stored in DynamoDB and private S3.
Hosts can share a viewer link, join code, or QR code; viewers receive live
captions without sending audio.

```text
Browser -> CloudFront/WAF -> S3 or ALB -> ECS Fargate
                                      -> Transcribe -> Translate
                                      -> DynamoDB / private S3
```

Cognito provides account access, SES sends branded account email, and a wake
Lambda starts the scale-to-zero backend. Raw audio is never stored.

## Current MVP

- Live Vietnamese captions with English translation
- Google and email sign-in through Cognito
- Shareable rooms with viewer link, six-character code, and QR code
- Finalized room transcript available after the host ends the meeting
- Five session starts per account each week, with no recording time limit
- Private TXT export and optional AI meeting notes through DeepSeek

## Quick Start

Requirements: Python 3.11+ and Node.js 20+.

```powershell
git clone https://github.com/9ducanh9/livecap.git
cd livecap\backend
python -m venv .venv; .\.venv\Scripts\python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env; .\.venv\Scripts\python -m uvicorn app.main:app --reload
```

```powershell
cd livecap\frontend
npm ci
Copy-Item .env.example .env
npm run dev
```

Open `http://127.0.0.1:5173`. AWS-backed features require the variables listed
in [the local run guide](docs/run-local.md); never put AWS access keys in `.env`.

## Stack

| Layer | Technology |
| --- | --- |
| Frontend | React, TypeScript, Vite, Tailwind CSS |
| Backend | Python, FastAPI, WebSocket |
| AWS | CloudFront, WAF, ALB, ECS Fargate, ECR, S3, DynamoDB, Cognito, SES, Transcribe, Translate |
| Delivery | Terraform, Docker, GitHub Actions OIDC |

Pushes to `main` run tests, publish an immutable backend image, update the ECS
task definition, deploy the frontend to S3, and invalidate CloudFront. General
infrastructure changes remain manual Terraform applies.

## Verify

```powershell
cd backend; .\.venv\Scripts\python -m pytest
cd ..\frontend; npm test; npm run build
cd ..\infrastructure\terraform; terraform fmt -check -recursive; terraform validate
```

See [docs](docs/README.md) for deployment evidence and operational notes.

## Author

Academic capstone project by [Lam Chi Tai](https://github.com/9ducanh9).
