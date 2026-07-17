# Run LiveCap locally (with the A1+ meeting summary)

Two terminals (PowerShell on Windows). The captions, translation and summary all
call real AWS services, so you need AWS credentials with **Amazon Transcribe,
Amazon Translate, and Amazon Bedrock (`bedrock:InvokeModel`)** access, and the
Bedrock model enabled for your region.

## 1. Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
```

Edit `.env`:

- `ENABLE_MEETING_SUMMARY=true`
- `BEDROCK_MODEL_ID=anthropic.claude-3-haiku-20240307-v1:0`
- If that model is not available in `AWS_REGION` (ap-southeast-1), set
  `BEDROCK_REGION=us-east-1` (or a region where you enabled it), or use an
  inference-profile ID as `BEDROCK_MODEL_ID`.

Provide AWS credentials **via a profile, not in `.env`**:

```powershell
$env:AWS_PROFILE = "your-profile"   # or run: aws configure
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Check: open `http://127.0.0.1:8000/api/health` → `{"status":"healthy",...}`.

Enable Bedrock model access once in the AWS console: **Bedrock → Model access →**
enable the Claude model in the region you point `BEDROCK_REGION` at.

## 2. Frontend

```powershell
cd frontend
npm ci
Copy-Item .env.example .env.local
npm run dev
```

`.env.example` already points at the local backend
(`ws://127.0.0.1:8000/ws/transcribe`) and leaves the wake URL empty, so no
cold-start wake is attempted locally.

Open `http://127.0.0.1:5173`, go to the caption workspace, allow the microphone.

## 3. See the summary

1. Speak a few sentences so **at least 3 finalized caption rows** appear
   (`SUMMARY_MIN_SEGMENTS=3`).
2. Press **Stop** while still connected.
3. The **AI meeting summary** panel appears with summary (VI/EN), key points,
   decisions, action items, plus the A1+ extraction: **keywords, insights,
   glossary, follow-up questions**. The Download TXT export includes them too.

## Troubleshooting

- No summary panel: fewer than 3 finalized rows, or you disconnected before Stop.
- Backend logs `Amazon Bedrock` integration error: model access not enabled, or
  the model id/region is wrong for your account. Check `BEDROCK_REGION`.
- 403/AccessDenied: the credentials lack `bedrock:InvokeModel` (or Transcribe/
  Translate) permissions.
- Summary is best-effort: on any Bedrock error the session still ends normally,
  just without a summary.
