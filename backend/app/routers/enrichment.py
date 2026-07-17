"""Enrichment endpoints: text-to-speech (A2) and text analysis (A3).

Both operate on **English** text. This is deliberate and required by the AWS
services involved:

* **Amazon Polly (A2)** has **no Vietnamese voice**, so TTS is offered for
  English only.
* **Amazon Comprehend (A3)** does **not support Vietnamese** for sentiment or
  key-phrase detection.

LiveCap always produces an English translation for every finalized segment
(the dual-stream pipeline fills the English column regardless of the spoken
language), so callers should pass that English text. Both endpoints are
opt-in via environment flags and are best-effort: on any AWS error they return
a 502 and the caller can continue without the enrichment.

Config (environment):
    ENABLE_TTS               "true" to enable POST /api/tts
    TTS_VOICE_ID_EN          Polly English voice id (default "Joanna")
    ENABLE_TEXT_ANALYSIS     "true" to enable POST /api/analyze
"""

from __future__ import annotations

import logging
import os

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

from app.config import get_settings
from app.services.logging_service import get_logger, log_integration_error

router = APIRouter()
_logger: logging.Logger = get_logger()

_MAX_TEXT_CHARS = 3000


def _env_true(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


# ---------------------------------------------------------------------------
# A2: Text-to-speech (Amazon Polly) — English only
# ---------------------------------------------------------------------------


class TtsRequest(BaseModel):
    text: str = Field(..., min_length=1)


def _synthesize_speech_en(text: str, voice_id: str, region: str) -> bytes:
    """Synthesize English speech with Amazon Polly. Runs boto3 (lazy import)."""
    import boto3  # noqa: PLC0415

    client = boto3.client("polly", region_name=region)
    resp = client.synthesize_speech(
        Text=text,
        OutputFormat="mp3",
        VoiceId=voice_id,
        Engine="neural",
        LanguageCode="en-US",
    )
    return resp["AudioStream"].read()


@router.post(
    "/api/tts",
    summary="Synthesize English speech (Amazon Polly)",
    responses={
        200: {"content": {"audio/mpeg": {}}, "description": "MP3 audio"},
        404: {"description": "TTS disabled."},
        502: {"description": "Amazon Polly error."},
    },
)
async def text_to_speech(body: TtsRequest) -> Response:
    if not _env_true("ENABLE_TTS"):
        raise HTTPException(status_code=404, detail="TTS is disabled")

    text = body.text.strip()[:_MAX_TEXT_CHARS]
    settings = get_settings()
    voice_id = os.getenv("TTS_VOICE_ID_EN", "Joanna").strip() or "Joanna"

    try:
        audio = _synthesize_speech_en(text, voice_id, settings.aws_region)
    except Exception as exc:  # noqa: BLE001 — best effort
        log_integration_error(
            session_id="-", service_name="Amazon Polly", error=exc
        )
        raise HTTPException(status_code=502, detail="Text-to-speech failed") from exc

    return Response(content=audio, media_type="audio/mpeg")


# ---------------------------------------------------------------------------
# A3: Text analysis (Amazon Comprehend) — English only
# ---------------------------------------------------------------------------


class AnalyzeRequest(BaseModel):
    text: str = Field(..., min_length=1)


class AnalyzeResponse(BaseModel):
    sentiment: str = ""
    sentiment_scores: dict[str, float] = Field(default_factory=dict)
    key_phrases: list[str] = Field(default_factory=list)


def _analyze_text_en(text: str, region: str) -> AnalyzeResponse:
    """Detect sentiment + key phrases on English text via Amazon Comprehend."""
    import boto3  # noqa: PLC0415

    client = boto3.client("comprehend", region_name=region)
    sentiment = client.detect_sentiment(Text=text, LanguageCode="en")
    phrases = client.detect_key_phrases(Text=text, LanguageCode="en")

    scores = {
        k.lower(): float(v)
        for k, v in (sentiment.get("SentimentScore") or {}).items()
    }
    key_phrases: list[str] = []
    seen: set[str] = set()
    for item in phrases.get("KeyPhrases", []):
        phrase = str(item.get("Text", "")).strip()
        if phrase and phrase.lower() not in seen:
            seen.add(phrase.lower())
            key_phrases.append(phrase)

    return AnalyzeResponse(
        sentiment=str(sentiment.get("Sentiment", "")),
        sentiment_scores=scores,
        key_phrases=key_phrases,
    )


@router.post(
    "/api/analyze",
    response_model=AnalyzeResponse,
    summary="Sentiment + key phrases on English text (Amazon Comprehend)",
    responses={
        200: {"description": "Analysis result."},
        404: {"description": "Text analysis disabled."},
        502: {"description": "Amazon Comprehend error."},
    },
)
async def analyze_text(body: AnalyzeRequest) -> AnalyzeResponse:
    if not _env_true("ENABLE_TEXT_ANALYSIS"):
        raise HTTPException(status_code=404, detail="Text analysis is disabled")

    text = body.text.strip()[:_MAX_TEXT_CHARS]
    settings = get_settings()

    try:
        return _analyze_text_en(text, settings.aws_region)
    except Exception as exc:  # noqa: BLE001 — best effort
        log_integration_error(
            session_id="-", service_name="Amazon Comprehend", error=exc
        )
        raise HTTPException(status_code=502, detail="Text analysis failed") from exc
