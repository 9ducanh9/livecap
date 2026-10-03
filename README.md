# LiveCap

LiveCap turns spoken Vietnamese and English into live bilingual captions. A host
can share an audience room so viewers follow finalized captions on their own
devices, then keep a transcript after the session.

[Open the app](https://livecap.logantai.com/app) · [Measured benchmark](docs/benchmark-phase5-results.md)

## Demo

https://github.com/user-attachments/assets/54635702-5870-420d-b5a8-e14363bd9404

A 55-second silent walkthrough of the host starting captions, creating an
audience room, and sharing a browser tab.

## What it does

- Streams microphone or shared-tab audio for live captions and translation.
- Lets a host create an audience room and share its link, code, or QR code.
- Shares finalized captions with viewers and supports private TXT transcript export.

The shared tab contains third-party media. This is a UI demonstration; the
measured benchmark below used a separate recorded-audio fixture.

## How it works

The browser sends 16 kHz PCM over WebSocket to FastAPI on ECS Fargate. Amazon
Transcribe and Translate produce the bilingual caption stream; finalized text
can be stored in DynamoDB and private S3. Cognito handles sign-in, while a wake
Lambda starts the backend after idle scale-to-zero. Raw audio is not stored.

See the [as-deployed architecture](docs/as-deployed-architecture.md) for the
request path and security boundaries.

## Measured result

In an isolated Singapore warm benchmark, **21/21 recorded-audio sessions
completed** across nine runs at 1, 2, and 4 concurrent sessions on one
0.5-vCPU / 1-GiB Fargate task. At four concurrent sessions, median first-partial
latency was **1.69 s** (12 sessions) and median finalized-caption lag was
**2.13 s** (120 correlated segments).

The campaign had two task restarts and three warm task epochs. These numbers do
not establish production reliability or maximum sustained capacity. The
[benchmark report](docs/benchmark-phase5-results.md) records the method,
denominators, and limits.

## Run locally

The frontend uses React, TypeScript, and Vite; the backend uses Python and
FastAPI. Follow the [local run guide](docs/run-local.md) for setup and required
AWS configuration. Browse the [documentation index](docs/README.md) for the
demo guide, architecture, and operational notes.

Academic capstone project by [Lam Chi Tai](https://github.com/9ducanh9).
