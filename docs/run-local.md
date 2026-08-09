# Run LiveCap locally (including optional meeting notes)

Two terminals (PowerShell on Windows). Captions and translation call real AWS
services, so you need AWS credentials with **Amazon Transcribe and Amazon
Translate** access. Meeting notes (summary) call **DeepSeek** instead of AWS —
you need a separate DeepSeek API key, not more AWS permissions.

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
- `DEEPSEEK_API_KEY=sk-...` — get one at
  [platform.deepseek.com](https://platform.deepseek.com/). Required; without
  it the feature gates itself off even when `ENABLE_MEETING_SUMMARY=true`.
- `DEEPSEEK_MODEL=deepseek-chat` (default, usually fine to leave as-is).

Provide AWS credentials **via a profile, not in `.env`** (for Transcribe/
Translate only — DeepSeek's key above is separate):

```powershell
$env:AWS_PROFILE = "your-profile"   # or run: aws configure
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Check: open `http://127.0.0.1:8000/api/health` → `{"status":"healthy",...}`.

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
3. After the session ends, choose **Create meeting notes**. This is the only
   action that calls DeepSeek.
4. The **AI meeting summary** panel appears with summary (VI/EN), key points,
   decisions, action items, plus the A1+ extraction: **keywords, insights,
   glossary, follow-up questions**. The Download TXT export includes them too.

## Troubleshooting

- The notes button is disabled: fewer than 3 finalized caption rows were captured.
- Backend logs a `DeepSeek` integration error and returns no summary: check
  `DEEPSEEK_API_KEY` is set and the key is active on
  [platform.deepseek.com](https://platform.deepseek.com/).
- Summary is best-effort: on any DeepSeek error (bad key, rate limit,
  timeout, malformed output) the session still ends normally, just without a
  summary — check backend logs for the actual cause.

## Historical note: why this isn't Amazon Bedrock anymore

Meeting notes originally called an Anthropic Claude model through Amazon
Bedrock. It never worked in production: `BEDROCK_MODEL_ID` was set to a
`us.`-prefixed cross-region inference profile, which only resolves from US
regions, while this project's Bedrock calls run from `ap-southeast-1` — every
call failed with `ValidationException("The provided model identifier is
invalid.")`. Fixing the model ID to the correct `global.` profile (confirmed
via `aws bedrock list-inference-profiles`) surfaced a second, deeper problem:
every Anthropic model quota in this AWS account's Bedrock region was `0`
(`aws service-quotas get-service-quota` confirmed `Adjustable: true, Value:
0.0`) — an unapproved AWS quota, not a code bug, and not something fixable
from the app side. Rather than wait on an AWS quota increase request with an
uncertain timeline, the integration was switched to DeepSeek's
OpenAI-compatible chat completions API, which needs its own key instead of
Bedrock quota approval. See `COLLAB_LOG.md` (local) for the full
investigation.
