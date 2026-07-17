"""Summarization_Service: Amazon Bedrock meeting summary integration.

Turns a finished Session's finalized transcript into a structured, bilingual
wrap-up (summary, key points, decisions, action items, topics) by invoking an
Anthropic Claude model through Amazon Bedrock.

Design notes
------------
* **Opt-in.** Controlled by ``settings.enable_meeting_summary`` (default off);
  when disabled the WebSocket handler never imports or calls this service, so
  there is no Bedrock cost.
* **Best effort.** Any failure (Bedrock unavailable, throttling, malformed
  model output) returns ``None`` and is logged; it never breaks session
  teardown.
* **Bounded.** The transcript sent to Bedrock is capped by
  ``settings.summary_max_input_chars`` to bound token cost and latency.
* **Testable.** The pure helpers :func:`build_transcript_text`,
  :func:`build_prompt`, and :func:`parse_summary_response` are AWS-free and
  unit tested; the network call lives only in :func:`summarize_session`.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Sequence

from app.config import Settings, get_settings
from app.models import FinalizedSegmentMessage, SessionSummary
from app.services.logging_service import get_logger, log_integration_error

_SERVICE_NAME = "Amazon Bedrock"
_ANTHROPIC_VERSION = "bedrock-2023-05-31"
_MAX_OUTPUT_TOKENS = 1024

_SYSTEM_PROMPT = (
    "You are a meeting-notes assistant for a bilingual Vietnamese-English "
    "captioning app. You receive a raw transcript with speaker labels and must "
    "produce a concise, faithful wrap-up. Never invent facts that are not in "
    "the transcript. Respond with a single JSON object and nothing else."
)


def build_transcript_text(
    segments: Sequence[FinalizedSegmentMessage],
    max_chars: int,
) -> str:
    """Render finalized segments into a plain-text transcript for the model.

    Each line is ``<speaker>: <originally spoken text>``. The originally spoken
    text is chosen by ``spoken_language`` and falls back to whichever column is
    non-empty. The result is truncated to *max_chars* (keeping the beginning).
    """
    lines: list[str] = []
    for seg in segments:
        if seg.spoken_language == "vi":
            spoken = seg.text_vi or seg.text_en
        else:
            spoken = seg.text_en or seg.text_vi
        spoken = spoken.strip()
        if not spoken:
            continue
        lines.append(f"{seg.speaker_label}: {spoken}")

    transcript = "\n".join(lines)
    if max_chars > 0 and len(transcript) > max_chars:
        transcript = transcript[:max_chars].rsplit("\n", 1)[0] + "\n[...truncated...]"
    return transcript


def build_prompt(transcript: str) -> str:
    """Build the user prompt instructing the model to return summary JSON."""
    return (
        "Summarize the following meeting transcript.\n\n"
        "Return ONLY a JSON object with exactly these keys:\n"
        '  "summary_vi": string  // 2-4 sentence summary in Vietnamese\n'
        '  "summary_en": string  // 2-4 sentence summary in English\n'
        '  "key_points": string[]   // main points, meeting\'s main language\n'
        '  "decisions": string[]    // decisions made, or empty array\n'
        '  "action_items": string[] // concrete follow-up tasks, or empty array\n'
        '  "topics": string[]       // short topic tags\n\n'
        "Use empty strings or empty arrays when a field does not apply. Do not "
        "wrap the JSON in markdown fences.\n\n"
        "Transcript:\n"
        f"{transcript}\n"
    )


def _coerce_str_list(value: object) -> list[str]:
    """Coerce a model-provided value into a clean list of non-empty strings."""
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def parse_summary_response(raw_text: str) -> SessionSummary | None:
    """Parse the model's text output into a :class:`SessionSummary`.

    Tolerant of surrounding prose or markdown fences: extracts the outermost
    ``{ ... }`` block before parsing. Returns ``None`` if no JSON object is
    found or it cannot be parsed.
    """
    if not raw_text:
        return None

    start = raw_text.find("{")
    end = raw_text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None

    try:
        data = json.loads(raw_text[start : end + 1])
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None

    return SessionSummary(
        summary_vi=str(data.get("summary_vi", "") or "").strip(),
        summary_en=str(data.get("summary_en", "") or "").strip(),
        key_points=_coerce_str_list(data.get("key_points")),
        decisions=_coerce_str_list(data.get("decisions")),
        action_items=_coerce_str_list(data.get("action_items")),
        topics=_coerce_str_list(data.get("topics")),
    )


def _invoke_bedrock_sync(
    *,
    model_id: str,
    region: str,
    prompt: str,
) -> str:
    """Synchronous Bedrock invoke_model call. Runs in a worker thread.

    Imported lazily so environments without botocore still import this module.
    """
    import boto3  # noqa: PLC0415

    client = boto3.client("bedrock-runtime", region_name=region)
    body = {
        "anthropic_version": _ANTHROPIC_VERSION,
        "max_tokens": _MAX_OUTPUT_TOKENS,
        "temperature": 0.2,
        "system": _SYSTEM_PROMPT,
        "messages": [
            {"role": "user", "content": [{"type": "text", "text": prompt}]}
        ],
    }
    response = client.invoke_model(modelId=model_id, body=json.dumps(body))
    payload = json.loads(response["body"].read())
    # Anthropic-on-Bedrock returns {"content": [{"type": "text", "text": ...}]}.
    parts = payload.get("content", [])
    return "".join(
        part.get("text", "")
        for part in parts
        if isinstance(part, dict) and part.get("type") == "text"
    )


async def summarize_session(
    session_id: str,
    segments: Sequence[FinalizedSegmentMessage],
    settings: Settings | None = None,
) -> SessionSummary | None:
    """Generate a :class:`SessionSummary` for a finished Session.

    Returns ``None`` (and logs) on any failure or when there is too little
    content to summarize. Never raises — safe to call during teardown.
    """
    settings = settings or get_settings()
    logger: logging.Logger = get_logger()

    if not settings.enable_meeting_summary:
        return None

    if len(segments) < settings.summary_min_segments:
        logger.info(
            "summary_skipped_too_short",
            extra={
                "event": "summary_skipped_too_short",
                "session_id": session_id,
                "segment_count": len(segments),
                "min_required": settings.summary_min_segments,
            },
        )
        return None

    transcript = build_transcript_text(segments, settings.summary_max_input_chars)
    if not transcript.strip():
        return None

    prompt = build_prompt(transcript)

    try:
        raw_text = await asyncio.wait_for(
            asyncio.to_thread(
                _invoke_bedrock_sync,
                model_id=settings.bedrock_model_id,
                region=settings.resolved_bedrock_region,
                prompt=prompt,
            ),
            timeout=settings.summary_timeout_seconds,
        )
    except Exception as exc:  # noqa: BLE001 — best effort; never break teardown
        log_integration_error(
            session_id=session_id,
            service_name=_SERVICE_NAME,
            error=exc,
        )
        return None

    summary = parse_summary_response(raw_text)
    if summary is None or summary.is_empty():
        logger.warning(
            "summary_unparseable_or_empty",
            extra={
                "event": "summary_unparseable_or_empty",
                "session_id": session_id,
            },
        )
        return None

    logger.info(
        "summary_generated",
        extra={
            "event": "summary_generated",
            "session_id": session_id,
            "action_item_count": len(summary.action_items),
            "key_point_count": len(summary.key_points),
        },
    )
    return summary


def summary_to_text(summary: SessionSummary) -> str:
    """Render a :class:`SessionSummary` into a plain-text block for export."""
    parts: list[str] = ["=== MEETING SUMMARY ==="]
    if summary.summary_en:
        parts.append(f"\nSummary (EN):\n{summary.summary_en}")
    if summary.summary_vi:
        parts.append(f"\nTóm tắt (VI):\n{summary.summary_vi}")
    if summary.key_points:
        parts.append("\nKey points:")
        parts.extend(f"  - {item}" for item in summary.key_points)
    if summary.decisions:
        parts.append("\nDecisions:")
        parts.extend(f"  - {item}" for item in summary.decisions)
    if summary.action_items:
        parts.append("\nAction items:")
        parts.extend(f"  - {item}" for item in summary.action_items)
    if summary.topics:
        parts.append("\nTopics: " + ", ".join(summary.topics))
    parts.append("\n" + "=" * 24)
    return "\n".join(parts)
