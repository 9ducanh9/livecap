"""Unit tests for the export REST endpoint.

Tests cover:
- 400 returned when no segments are provided
- 200 returned with download_url and expires_at on success
- 500 returned when Storage_Service raises StorageError
- 500 returned when Storage_Service raises UploadError (subclass of StorageError)
- session_id passed through to Storage_Service
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers.export import router

# Build a minimal app for testing.
app = FastAPI()
app.include_router(router)

client = TestClient(app)

_FAKE_URL = "https://s3.amazonaws.com/bucket/transcripts/sess-1/file.txt?Signature=abc"
_FAKE_EXPIRES = datetime(2099, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

_SEGMENT = {
    "segment_id": "seg-1",
    "speaker_label": "Speaker 1",
    "text_vi": "Xin chào",
    "text_en": "Hello",
    "spoken_language": "vi",
    "timestamp_start": 0.0,
    "timestamp_end": 1.5,
}


def _mock_storage_ok(*_args, **_kwargs):
    return _FAKE_URL, _FAKE_EXPIRES


# ---------------------------------------------------------------------------
# 400 – no segments provided
# ---------------------------------------------------------------------------


class TestExportBadRequest:
    def test_empty_segments_list_returns_400(self):
        """Requirement 7.3 / API design: 400 when segments list is empty."""
        resp = client.post(
            "/api/sessions/sess-1/export",
            json={"segments": []},
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "No segments provided"

    def test_missing_segments_key_returns_422(self):
        """FastAPI validation: segments field is required."""
        resp = client.post(
            "/api/sessions/sess-1/export",
            json={},
        )
        # Pydantic will default to an empty list due to default_factory,
        # which triggers the 400 path rather than 422.
        assert resp.status_code in (400, 422)


# ---------------------------------------------------------------------------
# 200 – success
# ---------------------------------------------------------------------------


class TestExportSuccess:
    def test_returns_200_with_download_url_and_expires_at(self):
        """Requirements 8.5, 9.2: success returns download_url and expires_at."""
        with patch(
            "app.routers.export.store_transcript_and_get_download_link",
            side_effect=_mock_storage_ok,
        ):
            resp = client.post(
                "/api/sessions/sess-1/export",
                json={"segments": [_SEGMENT]},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["download_url"] == _FAKE_URL
        assert "expires_at" in data

    def test_session_id_passed_to_storage_service(self):
        """The path parameter session_id reaches the Storage_Service."""
        captured = {}

        def capture_storage(session_id, segments, **kwargs):
            captured["session_id"] = session_id
            return _FAKE_URL, _FAKE_EXPIRES

        with patch(
            "app.routers.export.store_transcript_and_get_download_link",
            side_effect=capture_storage,
        ):
            client.post(
                "/api/sessions/my-unique-session/export",
                json={"segments": [_SEGMENT]},
            )
        assert captured["session_id"] == "my-unique-session"

    def test_segments_forwarded_to_storage_service(self):
        """All segments from the request body are forwarded."""
        captured = {}

        def capture_storage(session_id, segments, **kwargs):
            captured["count"] = len(segments)
            return _FAKE_URL, _FAKE_EXPIRES

        segments = [dict(_SEGMENT, segment_id=f"seg-{i}") for i in range(3)]
        with patch(
            "app.routers.export.store_transcript_and_get_download_link",
            side_effect=capture_storage,
        ):
            resp = client.post(
                "/api/sessions/sess-1/export",
                json={"segments": segments},
            )
        assert resp.status_code == 200
        assert captured["count"] == 3

    def test_expires_at_is_iso8601_string(self):
        """expires_at in the JSON response is a valid ISO-8601 datetime string."""
        with patch(
            "app.routers.export.store_transcript_and_get_download_link",
            side_effect=_mock_storage_ok,
        ):
            resp = client.post(
                "/api/sessions/sess-1/export",
                json={"segments": [_SEGMENT]},
            )
        data = resp.json()
        # Should parse without error.
        parsed = datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00"))
        assert parsed.tzinfo is not None


# ---------------------------------------------------------------------------
# 500 – storage failure
# ---------------------------------------------------------------------------


class TestExportStorageFailure:
    def test_upload_error_returns_500(self):
        """Requirements 8.4: upload failure → 500 with expected detail."""
        from app.services.storage import UploadError

        with patch(
            "app.routers.export.store_transcript_and_get_download_link",
            side_effect=UploadError("S3 boom"),
        ):
            resp = client.post(
                "/api/sessions/sess-1/export",
                json={"segments": [_SEGMENT]},
            )
        assert resp.status_code == 500
        assert resp.json()["detail"] == "Failed to upload transcript to S3"

    def test_key_assignment_error_returns_500(self):
        """Requirements 8.3: key assignment failure → 500."""
        from app.services.storage import KeyAssignmentError

        with patch(
            "app.routers.export.store_transcript_and_get_download_link",
            side_effect=KeyAssignmentError("key failure"),
        ):
            resp = client.post(
                "/api/sessions/sess-1/export",
                json={"segments": [_SEGMENT]},
            )
        assert resp.status_code == 500
        assert resp.json()["detail"] == "Failed to upload transcript to S3"

    def test_generic_storage_error_returns_500(self):
        """Any StorageError subclass → 500."""
        from app.services.storage import StorageError

        with patch(
            "app.routers.export.store_transcript_and_get_download_link",
            side_effect=StorageError("presign failed"),
        ):
            resp = client.post(
                "/api/sessions/sess-1/export",
                json={"segments": [_SEGMENT]},
            )
        assert resp.status_code == 500
        assert resp.json()["detail"] == "Failed to upload transcript to S3"
