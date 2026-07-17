"""Tests for the user-triggered AI meeting-notes endpoint."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings
from app.models import SessionSummary
from app.routers.summary import router

app = FastAPI()
app.include_router(router)
client = TestClient(app)

_SEGMENT = {
    "segment_id": "seg-1",
    "speaker_label": "Speaker 1",
    "text_vi": "Xin chao",
    "text_en": "Hello",
    "spoken_language": "vi",
    "timestamp_start": 0.0,
    "timestamp_end": 1.0,
}


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "enable_meeting_summary": True,
        "summary_min_segments": 3,
    }
    values.update(overrides)
    return Settings(**values)


class TestGenerateSummary:
    def test_rejects_when_feature_is_disabled(self) -> None:
        with patch("app.routers.summary.get_settings", return_value=_settings(enable_meeting_summary=False)), patch(
            "app.routers.summary.summarize_session", new_callable=AsyncMock
        ) as summarize:
            response = client.post("/api/sessions/sess-1/summary", json={"segments": [_SEGMENT] * 3})

        assert response.status_code == 409
        assert response.json()["detail"] == "AI meeting notes are not enabled"
        summarize.assert_not_awaited()

    def test_rejects_when_too_few_finalized_segments_are_supplied(self) -> None:
        with patch("app.routers.summary.get_settings", return_value=_settings()), patch(
            "app.routers.summary.summarize_session", new_callable=AsyncMock
        ) as summarize:
            response = client.post("/api/sessions/sess-1/summary", json={"segments": [_SEGMENT] * 2})

        assert response.status_code == 400
        assert "3 finalized captions" in response.json()["detail"]
        summarize.assert_not_awaited()

    def test_generates_notes_only_for_explicit_summary_request(self) -> None:
        expected = SessionSummary(
            summary_en="The team agreed on a launch date.",
            keywords=["launch"],
        )
        with patch("app.routers.summary.get_settings", return_value=_settings()), patch(
            "app.routers.summary.summarize_session",
            new=AsyncMock(return_value=expected),
        ) as summarize:
            response = client.post(
                "/api/sessions/sess-42/summary",
                json={"segments": [dict(_SEGMENT, segment_id=f"seg-{index}") for index in range(3)]},
            )

        assert response.status_code == 200
        assert response.json()["keywords"] == ["launch"]
        assert summarize.await_count == 1
        assert summarize.await_args.kwargs["session_id"] == "sess-42"
        assert len(summarize.await_args.kwargs["segments"]) == 3

    def test_returns_retryable_error_when_bedrock_has_no_usable_response(self) -> None:
        with patch("app.routers.summary.get_settings", return_value=_settings()), patch(
            "app.routers.summary.summarize_session", new=AsyncMock(return_value=None)
        ):
            response = client.post("/api/sessions/sess-1/summary", json={"segments": [_SEGMENT] * 3})

        assert response.status_code == 502
        assert "Please try again" in response.json()["detail"]
