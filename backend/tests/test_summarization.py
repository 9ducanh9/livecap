"""Tests for the Amazon Bedrock meeting-summary Summarization_Service.

The pure helpers (transcript building, prompt building, response parsing,
export rendering) are tested directly. The network path in
``summarize_session`` is exercised with ``_invoke_bedrock_sync`` patched, so no
AWS calls are made.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import patch

from app.config import Settings
from app.models import FinalizedSegmentMessage, SessionSummary
from app.services import summarization
from app.services.summarization import (
    build_prompt,
    build_transcript_text,
    parse_summary_response,
    summarize_session,
    summary_to_text,
)


def _seg(
    segment_id: str,
    speaker: str,
    spoken_language: str,
    text_vi: str = "",
    text_en: str = "",
) -> FinalizedSegmentMessage:
    return FinalizedSegmentMessage(
        segment_id=segment_id,
        speaker_label=speaker,
        text_vi=text_vi,
        text_en=text_en,
        spoken_language=spoken_language,
    )


# ---------------------------------------------------------------------------
# build_transcript_text
# ---------------------------------------------------------------------------


def test_build_transcript_uses_spoken_language_column():
    segs = [
        _seg("s1", "Speaker 1", "vi", text_vi="Xin chào", text_en="Hello"),
        _seg("s2", "Speaker 2", "en", text_vi="Cảm ơn", text_en="Thank you"),
    ]
    out = build_transcript_text(segs, max_chars=1000)
    assert out == "Speaker 1: Xin chào\nSpeaker 2: Thank you"


def test_build_transcript_falls_back_to_other_column_when_spoken_empty():
    segs = [_seg("s1", "Speaker 1", "vi", text_vi="", text_en="Hello")]
    out = build_transcript_text(segs, max_chars=1000)
    assert out == "Speaker 1: Hello"


def test_build_transcript_skips_empty_segments():
    segs = [
        _seg("s1", "Speaker 1", "vi", text_vi="  ", text_en=""),
        _seg("s2", "Speaker 2", "en", text_en="Real line"),
    ]
    out = build_transcript_text(segs, max_chars=1000)
    assert out == "Speaker 2: Real line"


def test_build_transcript_truncates_to_max_chars():
    segs = [_seg(f"s{i}", "Speaker 1", "en", text_en="x" * 50) for i in range(20)]
    out = build_transcript_text(segs, max_chars=100)
    assert "[...truncated...]" in out
    assert len(out) <= 100 + len("\n[...truncated...]")


# ---------------------------------------------------------------------------
# build_prompt
# ---------------------------------------------------------------------------


def test_build_prompt_embeds_transcript_and_json_keys():
    prompt = build_prompt("Speaker 1: hi")
    assert "Speaker 1: hi" in prompt
    assert "summary_vi" in prompt
    assert "action_items" in prompt


# ---------------------------------------------------------------------------
# parse_summary_response
# ---------------------------------------------------------------------------


def test_parse_valid_json():
    raw = json.dumps(
        {
            "summary_vi": "Tóm tắt",
            "summary_en": "Summary",
            "key_points": ["a", "b"],
            "decisions": [],
            "action_items": ["do x"],
            "topics": ["t1"],
        }
    )
    summary = parse_summary_response(raw)
    assert summary is not None
    assert summary.summary_en == "Summary"
    assert summary.key_points == ["a", "b"]
    assert summary.action_items == ["do x"]
    assert summary.decisions == []


def test_parse_json_with_surrounding_prose_and_fences():
    raw = 'Here you go:\n```json\n{"summary_en": "S", "topics": ["x"]}\n```\nThanks!'
    summary = parse_summary_response(raw)
    assert summary is not None
    assert summary.summary_en == "S"
    assert summary.topics == ["x"]


def test_parse_coerces_non_list_values():
    raw = '{"key_points": "single point", "action_items": [1, 2, ""]}'
    summary = parse_summary_response(raw)
    assert summary is not None
    assert summary.key_points == ["single point"]
    assert summary.action_items == ["1", "2"]


def test_parse_returns_none_for_no_json():
    assert parse_summary_response("no json here") is None
    assert parse_summary_response("") is None


def test_parse_returns_none_for_invalid_json():
    assert parse_summary_response("{not valid json,,,}") is None


# ---------------------------------------------------------------------------
# summary_to_text
# ---------------------------------------------------------------------------


def test_summary_to_text_renders_sections():
    summary = SessionSummary(
        summary_en="An English summary.",
        summary_vi="Bản tóm tắt.",
        key_points=["point one"],
        action_items=["follow up"],
        topics=["budget", "timeline"],
    )
    text = summary_to_text(summary)
    assert "MEETING SUMMARY" in text
    assert "An English summary." in text
    assert "Bản tóm tắt." in text
    assert "- point one" in text
    assert "- follow up" in text
    assert "budget, timeline" in text


# ---------------------------------------------------------------------------
# summarize_session (network path patched)
# ---------------------------------------------------------------------------


def test_summarize_session_disabled_returns_none():
    settings = Settings(enable_meeting_summary=False)
    segs = [_seg(f"s{i}", "Speaker 1", "en", text_en="hi there") for i in range(5)]
    result = asyncio.run(summarize_session("sess", segs, settings))
    assert result is None


def test_summarize_session_too_few_segments_returns_none():
    settings = Settings(enable_meeting_summary=True, summary_min_segments=3)
    segs = [_seg("s1", "Speaker 1", "en", text_en="hi")]
    with patch.object(summarization, "_invoke_bedrock_sync") as mocked:
        result = asyncio.run(summarize_session("sess", segs, settings))
    assert result is None
    mocked.assert_not_called()


def test_summarize_session_success_path():
    settings = Settings(enable_meeting_summary=True, summary_min_segments=2)
    segs = [
        _seg("s1", "Speaker 1", "en", text_en="We should ship Friday."),
        _seg("s2", "Speaker 2", "vi", text_vi="Đồng ý."),
    ]
    model_json = json.dumps(
        {
            "summary_en": "Team agreed to ship Friday.",
            "summary_vi": "Nhóm đồng ý phát hành thứ Sáu.",
            "action_items": ["Ship on Friday"],
            "topics": ["release"],
        }
    )
    with patch.object(
        summarization, "_invoke_bedrock_sync", return_value=model_json
    ) as mocked:
        result = asyncio.run(summarize_session("sess", segs, settings))
    assert result is not None
    assert result.summary_en == "Team agreed to ship Friday."
    assert result.action_items == ["Ship on Friday"]
    mocked.assert_called_once()


def test_summarize_session_swallows_bedrock_error():
    settings = Settings(enable_meeting_summary=True, summary_min_segments=1)
    segs = [_seg("s1", "Speaker 1", "en", text_en="hello world")]
    with patch.object(
        summarization, "_invoke_bedrock_sync", side_effect=RuntimeError("boom")
    ):
        result = asyncio.run(summarize_session("sess", segs, settings))
    assert result is None


def test_summarize_session_empty_model_output_returns_none():
    settings = Settings(enable_meeting_summary=True, summary_min_segments=1)
    segs = [_seg("s1", "Speaker 1", "en", text_en="hello world")]
    with patch.object(
        summarization, "_invoke_bedrock_sync", return_value="{}"
    ):
        result = asyncio.run(summarize_session("sess", segs, settings))
    assert result is None
