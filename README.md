# LiveCap

LiveCap is a real-time speech caption and translation web application. It captures microphone audio in the browser, streams it to a FastAPI backend over a secure WebSocket (WSS), transcribes it with Amazon Transcribe Streaming, translates it with Amazon Translate, and displays bilingual captions side-by-side — Vietnamese on the left, English on the right. Sessions can be exported as TXT files and stored in Amazon S3 with a time-limited download link.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Environment Variables](#environment-variables)
3. [Backend Setup (EC2)](#backend-setup-ec2)
4. [Frontend Setup (S3 + CloudFront)](#frontend-setup-s3--cloudfront)
5. [Local Development](#local-development)
6. [Architecture Overview](#architecture-overview)

---

## Prerequisites

| Requirement | Version |
|-------------|---------|
| Python | 3.11 or later |
| Node.js | 18 LTS or later |
| npm | 9 or later |
| AWS account | — |
| AWS CLI | v2, configured with credentials that have access to EC2, S3, CloudFront, IAM, Transcribe, Translate, and CloudWatch |

---

## Environment Variables

Copy `backend/.env.example` to `backend/.env` and fill in the values for your environment.

```bash
cp backend/.env.example backend/.env
```

| Variable | Default | Description |
|----------|---------|-------------|
| `AWS_REGION` | `us-east-1` | AWS region used for Transcribe, Translate, and S3. |
| `S3_BUCKET` | — | Name of the S3 bucket where exported transcripts are stored. |
| `DOWNLOAD_LINK_EXPIRATION` | `86400` | Expiration in seconds for pre-signed download links (default: 24 hours). |
| `SESSION_TIMEOUT` | `1800` | Maximum session duration in seconds before the backend times out an active streaming session (default: 30 minutes). |
| `MAX_SPEAKERS` | `5` | Maximum number of speakers for Transcribe diarization. |
| `ALLOWED_ORIGIN` | `http://localhost:5173` | The single frontend origin allowed to call the backend (CORS). In production, set to your CloudFront URL, e.g. `https://d1234abcd.cloudfront.net`. |
| `CLOUDWATCH_LOG_GROUP` | `livecap` | CloudWatch log group for structured logging. Falls back to stdout when CloudWatch is unavailable. |

Frontend build-time variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `VITE_WS_URL` | current browser origin + `/ws/transcribe` | Backend WebSocket endpoint. In production, set this to the EC2/Nginx WSS endpoint, e.g. `wss://your-ec2-domain/ws/transcribe`. |
| `VITE_API_BASE_URL` | current browser origin | Backend REST API origin. In production, set this to the EC2/Nginx HTTPS origin, e.g. `https://your-ec2-domain`. |

> **Important:** On EC2, AWS credentials are supplied by the instance IAM role. Do **not** set `AWS_ACCESS_KEY_ID` or `AWS_SECRET_ACCESS_KEY` in `.env`.

---

## Backend Setup (EC2)

### 1. EC2 Instance Requirements

- **Instance type:** t3.small or larger (2 vCPU, 2 GB RAM recommended for MVP)
- **OS:** Amazon Linux 2023 or Ubuntu 22.04 LTS
- **Security group inbound rules:**
  - Port 22 (SSH) — from your IP only
  - Port 443 (HTTPS/WSS) — from `0.0.0.0/0`
- **Storage:** 8 GB gp3 root volume (minimum)

### 2. IAM Role

Create an IAM role named `livecap-ec2-role` (or similar) and attach the following AWS-managed and inline policies:

| Policy | Purpose |
|--------|---------|
| `AmazonTranscribeFullAccess` | Stream audio to Amazon Transcribe |
| `TranslateFullAccess` | Call Amazon Translate |
| `AmazonS3FullAccess` (or a scoped inline policy) | Upload transcripts and generate pre-signed URLs |
| `CloudWatchLogsFullAccess` (or a scoped inline policy) | Write structured logs to CloudWatch |

**Recommended scoped S3 inline policy** (replace `YOUR_BUCKET` with your actual bucket name):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:GetObject"
      ],
      "Resource": "arn:aws:s3:::YOUR_BUCKET/transcripts/*"
    }
  ]
}
```

Attach the role to your EC2 instance under **Actions → Security → Modify IAM Role**.

### 3. Install Dependencies

SSH into the instance and install Python 3.11+ and the project dependencies:

```bash
# Amazon Linux 2023
sudo dnf install -y python3.11 python3.11-pip git nginx

# Ubuntu 22.04
# sudo apt update && sudo apt install -y python3.11 python3.11-pip git nginx

# Clone the repository
git clone https://github.com/your-org/livecap.git
cd livecap/backend

# Install Python packages
pip3.11 install -r requirements.txt
```

### 4. Configure Environment

```bash
cp .env.example .env
# Edit .env — set S3_BUCKET, AWS_REGION, ALLOWED_ORIGIN (your CloudFront URL), etc.
nano .env
```

### 5. Run with Uvicorn (manual test)

```bash
cd livecap/backend
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Visit `http://127.0.0.1:8000/api/health` on the instance to confirm the backend is running.

### 6. systemd Service

A ready-made systemd unit is provided at `deploy/livecap.service`. Copy it to systemd and enable it:

```bash
# Adjust the WorkingDirectory and ExecStart paths in the file if needed
sudo cp deploy/livecap.service /etc/systemd/system/livecap.service
sudo systemctl daemon-reload
sudo systemctl enable livecap
sudo systemctl start livecap
sudo systemctl status livecap
```

Logs are available via:

```bash
sudo journalctl -u livecap -f
```

### 7. Nginx Reverse Proxy (TLS + WSS)

Nginx terminates TLS on port 443 and forwards both HTTPS and WSS connections to the Uvicorn process on `127.0.0.1:8000`.

A configuration template is provided at `deploy/nginx.conf`. Before applying it:

1. Obtain a TLS certificate (e.g., via Let's Encrypt / Certbot) for your EC2 domain.
2. Update the `server_name`, `ssl_certificate`, and `ssl_certificate_key` directives in `nginx.conf`.
3. Apply the configuration:

```bash
sudo cp deploy/nginx.conf /etc/nginx/conf.d/livecap.conf
sudo nginx -t          # verify config syntax
sudo systemctl reload nginx
```

The WebSocket endpoint is then reachable at `wss://your-ec2-domain/ws/transcribe`.

---

## Frontend Setup (S3 + CloudFront)

### 1. Install and Build

```bash
cd livecap/frontend
npm install

# Set the backend WebSocket and REST API URLs before building
# Replace the URL with your EC2 domain
VITE_WS_URL=wss://your-ec2-domain/ws/transcribe \
VITE_API_BASE_URL=https://your-ec2-domain \
npm run build
```

The static bundle is output to `frontend/dist/`.

### 2. Create and Configure the S3 Bucket

```bash
# Create the bucket (choose a unique name)
aws s3 mb s3://livecap-frontend --region us-east-1

# Disable public access block (CloudFront will control access via OAC)
aws s3api put-public-access-block \
  --bucket livecap-frontend \
  --public-access-block-configuration \
    "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"
```

### 3. Upload the Static Bundle

```bash
aws s3 sync frontend/dist/ s3://livecap-frontend/ \
  --delete \
  --cache-control "max-age=31536000,immutable" \
  --exclude "index.html"

# Upload index.html separately with no-cache so CloudFront always fetches the latest
aws s3 cp frontend/dist/index.html s3://livecap-frontend/index.html \
  --cache-control "no-cache,no-store,must-revalidate"
```

### 4. Create a CloudFront Distribution

1. In the AWS console, go to **CloudFront → Create distribution**.
2. **Origin domain:** select your S3 bucket (`livecap-frontend.s3.amazonaws.com`).
3. **Origin access:** choose **Origin access control (OAC)**. Create a new OAC and copy the generated bucket policy into your S3 bucket's **Permissions → Bucket policy**.
4. **Viewer protocol policy:** set to **Redirect HTTP to HTTPS**.
5. **Default root object:** enter `index.html`.
6. **Error pages:** add a custom error response — HTTP error code `403` → Response page `/index.html`, HTTP response code `200` (enables client-side routing).
7. Click **Create distribution** and wait for the status to change to **Deployed**.
8. Note the **Distribution domain name** (e.g., `d1234abcd.cloudfront.net`). This is your public HTTPS URL.

### 5. Update the Backend CORS Origin

Set `ALLOWED_ORIGIN` in `backend/.env` to your CloudFront URL:

```
ALLOWED_ORIGIN=https://d1234abcd.cloudfront.net
```

Then restart the backend service:

```bash
sudo systemctl restart livecap
```

---

## Local Development

Run the backend and frontend in separate terminals:

**Terminal 1 — Backend**

```bash
cd livecap/backend
cp .env.example .env
# Edit .env: set AWS_REGION, S3_BUCKET, ALLOWED_ORIGIN=http://localhost:5173
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The API is available at `http://localhost:8000`. Health check: `http://localhost:8000/api/health`.

**Terminal 2 — Frontend**

```bash
cd livecap/frontend
npm install
VITE_WS_URL=ws://localhost:8000/ws/transcribe \
VITE_API_BASE_URL=http://localhost:8000 \
npm run dev
```

The app opens at `http://localhost:5173`.

> **Note:** Local development uses plain `ws://` and `http://` (no TLS). Production deployments must use `wss://` and `https://`.

---

## Architecture Overview

```
Browser
  │
  ├── HTTPS ──► Amazon CloudFront ──► Amazon S3 (static React bundle)
  │
  └── WSS ───► Nginx (TLS termination) on EC2
                  └──► Uvicorn + FastAPI (WebSocket + REST)
                            ├──► Amazon Transcribe Streaming
                            ├──► Amazon Translate
                            ├──► Amazon S3 (transcript storage)
                            └──► Amazon CloudWatch (logging)
```

- **Frontend** — React + TypeScript, built with Vite, served globally over HTTPS via Amazon CloudFront backed by Amazon S3.
- **Backend** — FastAPI (Python 3.11+) running under Uvicorn on a single Amazon EC2 instance. Nginx on the same instance terminates TLS and upgrades WebSocket connections to WSS.
- **AWS credentials** — Provided exclusively by the EC2 instance IAM role. No credentials are stored in environment variables or source code.
- **Transcription** — Amazon Transcribe Streaming with automatic language identification (`vi-VN` / `en-US`) and speaker diarization.
- **Translation** — Amazon Translate, called per finalized segment (vi → en or en → vi).
- **Storage** — Exported TXT transcripts are uploaded to Amazon S3; time-limited pre-signed URLs are returned to the browser.
- **Logging** — Structured JSON logs sent to Amazon CloudWatch Logs via the `watchtower` library; falls back to stdout in development.
