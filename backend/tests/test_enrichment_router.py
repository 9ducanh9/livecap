"""Tests for the enrichment endpoints (A2 Polly TTS, A3 Comprehend analysis).

The router is mounted on a standalone app so these tests do not depend on
main.py wiring. The AWS calls are patched, so no boto3/AWS access is needed.
"""

from __future__ import annotations

from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import enrichment
from app.routers.enrichment import AnalyzeResponse, router


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


# --- A2: TTS ---------------------------------------------------------------


def test_tts_disabled_returns_404(monkeypatch):
    monkeypatch.delenv("ENABLE_TTS", raising=False)
    resp = _client().post("/api/tts", json={"text": "hello"})
    assert resp.status_code == 404


def test_tts_returns_audio_when_enabled(monkeypatch):
    monkeypatch.setenv("ENABLE_TTS", "true")
    with patch.object(enrichment, "_synthesize_speech_en", return_value=b"ID3MP3") as m:
        resp = _client().post("/api/tts", json={"text": "hello world"})
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "audio/mpeg"
    assert resp.content == b"ID3MP3"
    m.assert_called_once()


def test_tts_maps_polly_error_to_502(monkeypatch):
    monkeypatch.setenv("ENABLE_TTS", "true")
    with patch.object(enrichment, "_synthesize_speech_en", side_effect=RuntimeError("boom")):
        resp = _client().post("/api/tts", json={"text": "hello"})
    assert resp.status_code == 502


def test_tts_rejects_empty_text(monkeypatch):
    monkeypatch.setenv("ENABLE_TTS", "true")
    resp = _client().post("/api/tts", json={"text": ""})
    assert resp.status_code == 422  # pydantic min_length


# --- A3: analyze -----------------------------------------------------------


def test_analyze_disabled_returns_404(monkeypatch):
    monkeypatch.delenv("ENABLE_TEXT_ANALYSIS", raising=False)
    resp = _client().post("/api/analyze", json={"text": "hello"})
    assert resp.status_code == 404


def test_analyze_returns_result_when_enabled(monkeypatch):
    monkeypatch.setenv("ENABLE_TEXT_ANALYSIS", "true")
    fake = AnalyzeResponse(
        sentiment="POSITIVE",
        sentiment_scores={"positive": 0.9, "negative": 0.01},
        key_phrases=["the project", "Friday"],
    )
    with patch.object(enrichment, "_analyze_text_en", return_value=fake) as m:
        resp = _client().post("/api/analyze", json={"text": "We ship Friday."})
    assert resp.status_code == 200
    body = resp.json()
    assert body["sentiment"] == "POSITIVE"
    assert body["key_phrases"] == ["the project", "Friday"]
    assert body["sentiment_scores"]["positive"] == 0.9
    m.assert_called_once()


def test_analyze_maps_comprehend_error_to_502(monkeypatch):
    monkeypatch.setenv("ENABLE_TEXT_ANALYSIS", "true")
    with patch.object(enrichment, "_analyze_text_en", side_effect=RuntimeError("boom")):
        resp = _client().post("/api/analyze", json={"text": "hello"})
    assert resp.status_code == 502
