"""Summarization_Service: DeepSeek meeting summary integration.

Turns a finished Session's finalized transcript into a structured, bilingual
wrap-up (summary, key points, decisions, action items, topics) by calling the
DeepSeek chat completions API (OpenAI-compatible).

Previously called an Anthropic Claude model through Amazon Bedrock, but every
Anthropic model quota in the account's Bedrock region was 0 (unrelated to any
code bug -- confirmed with a real InvokeModel call, see COLLAB_LOG.md), so
the feature never actually worked. DeepSeek needs its own API key
(``DEEPSEEK_API_KEY``) rather than the AWS credentials already on the task
role, but has no dependency on Bedrock quota approval.

Design notes
------------
* **Opt-in.** Controlled by ``settings.enable_meeting_summary`` (default off)
  *and* requires ``settings.deepseek_api_key`` to be set; when either is
  missing the WebSocket handler never calls this service, so there is no
  DeepSeek cost.
* **Best effort.** Any failure (API unavailable, rate limiting, malformed
  model output) returns ``None`` and is logged; it never breaks session
  teardown.
* **Bounded.** The transcript sent to the model is capped by
  ``settings.summary_max_input_chars`` to bound token cost and latency.
* **Testable.** The pure helpers :func:`build_transcript_text`,
  :func:`build_prompt`, and :func:`parse_summary_response` are network-free
  and unit tested; the network call lives only in :func:`summarize_session`.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Sequence

from app.config import Settings, get_settings
from app.models import FinalizedSegmentMessage, GlossaryItem, SessionSummary
from app.services.logging_service import get_logger, log_integration_error

_SERVICE_NAME = "DeepSeek"
_DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
_MAX_OUTPUT_TOKENS = 1536

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
        "Summarize and extract knowledge from the following transcript.\n\n"
        "Return ONLY a JSON object with exactly these keys:\n"
        '  "summary_vi": string  // 2-4 sentence summary in Vietnamese\n'
        '  "summary_en": string  // 2-4 sentence summary in English\n'
        '  "key_points": string[]   // main points, meeting\'s main language\n'
        '  "decisions": string[]    // decisions made, or empty array\n'
        '  "action_items": string[] // concrete follow-up tasks, or empty array\n'
        '  "topics": string[]       // short topic tags\n'
        '  "keywords": string[]     // salient keywords/terms from the content\n'
        '  "insights": string[]     // takeaways/conclusions drawn from the text\n'
        '  "glossary": object[]     // [{"term": string, "definition": string}] '
        "for notable terms/concepts, short definitions\n"
        '  "follow_up_questions": string[] // open questions to explore further\n\n'
        "Base everything strictly on the transcript; do not invent facts. Use "
        "empty strings or empty arrays when a field does not apply. Do not wrap "
        "the JSON in markdown fences.\n\n"
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


def _coerce_glossary(value: object) -> list[GlossaryItem]:
    """Coerce a model-provided glossary into a list of GlossaryItem.

    Accepts a list of ``{"term", "definition"}`` objects; tolerates strings
    shaped like ``"term: definition"`` as a fallback.
    """
    items: list[GlossaryItem] = []
    if not isinstance(value, list):
        return items
    for entry in value:
        if isinstance(entry, dict):
            term = str(entry.get("term", "")).strip()
            definition = str(entry.get("definition", "")).strip()
        elif isinstance(entry, str) and ":" in entry:
            term, definition = (part.strip() for part in entry.split(":", 1))
        else:
            term, definition = str(entry).strip(), ""
        if term:
            items.append(GlossaryItem(term=term, definition=definition))
    return items


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
        keywords=_coerce_str_list(data.get("keywords")),
        insights=_coerce_str_list(data.get("insights")),
        glossary=_coerce_glossary(data.get("glossary")),
        follow_up_questions=_coerce_str_list(data.get("follow_up_questions")),
    )


def _invoke_deepseek_sync(
    *,
    api_key: str,
    model: str,
    prompt: str,
    timeout_seconds: int,
) -> str:
    """Synchronous DeepSeek chat-completions call. Runs in a worker thread.

    Imported lazily so environments without httpx still import this module.
    ``timeout_seconds`` bounds the httpx call itself (not just the
    ``asyncio.wait_for`` around the calling thread) -- ``asyncio.to_thread``
    can't actually interrupt a real OS thread on cancellation, so without
    this the request would keep running in the background past the
    caller's deadline.
    """
    import httpx  # noqa: PLC0415

    body = {
        "model": model,
        "max_tokens": _MAX_OUTPUT_TOKENS,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    }
    response = httpx.post(
        _DEEPSEEK_API_URL,
        json=body,
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    payload = response.json()
    # OpenAI-compatible: {"choices": [{"message": {"content": "..."}}]}.
    choices = payload.get("choices", [])
    if not choices:
        return ""
    return choices[0].get("message", {}).get("content", "")


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

    if not settings.deepseek_api_key:
        logger.warning(
            "summary_skipped_no_api_key",
            extra={"event": "summary_skipped_no_api_key", "session_id": session_id},
        )
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
                _invoke_deepseek_sync,
                api_key=settings.deepseek_api_key,
                model=settings.deepseek_model,
                prompt=prompt,
                timeout_seconds=settings.summary_timeout_seconds,
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
    if summary.insights:
        parts.append("\nInsights:")
        parts.extend(f"  - {item}" for item in summary.insights)
    if summary.glossary:
        parts.append("\nGlossary:")
        parts.extend(
            f"  - {g.term}: {g.definition}" if g.definition else f"  - {g.term}"
            for g in summary.glossary
        )
    if summary.follow_up_questions:
        parts.append("\nFollow-up questions:")
        parts.extend(f"  - {q}" for q in summary.follow_up_questions)
    if summary.keywords:
        parts.append("\nKeywords: " + ", ".join(summary.keywords))
    if summary.topics:
        parts.append("\nTopics: " + ", ".join(summary.topics))
    parts.append("\n" + "=" * 24)
    return "\n".join(parts)
