"""Unit tests for backend/app/services/storage.py.

Covers:
- Transcript TXT serialization: format, ordering, empty case
- S3 object key generation: format, uniqueness, includes session_id
- High-level storage workflow integration (with mocked S3)
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.models import ExportSegment
from app.services.storage import (
    KeyAssignmentError,
    StorageError,
    UploadError,
    generate_presigned_download_link,
    generate_s3_object_key,
    serialize_transcript_to_txt,
    store_transcript_and_get_download_link,
    upload_transcript_to_s3,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_segment(
    speaker_label: str = "Speaker 1",
    text_vi: str = "Xin chào",
    text_en: str = "Hello",
    spoken_language: str = "vi",
    segment_id: str = "seg-1",
) -> ExportSegment:
    return ExportSegment(
        segment_id=segment_id,
        speaker_label=speaker_label,
        text_vi=text_vi,
        text_en=text_en,
        spoken_language=spoken_language,
    )


# ---------------------------------------------------------------------------
# serialize_transcript_to_txt
# ---------------------------------------------------------------------------


class TestSerializeTranscriptToTxt:
    def test_empty_transcript_returns_empty_string(self):
        """Requirement 7.3: empty transcript produces empty TXT."""
        result = serialize_transcript_to_txt([])
        assert result == ""

    def test_single_segment_format(self):
        """Requirement 7.1: format is [Speaker Label] VI: ... | EN: ..."""
        seg = make_segment(
            speaker_label="Speaker 1",
            text_vi="Xin chào",
            text_en="Hello",
        )
        result = serialize_transcript_to_txt([seg])
        assert result == "[Speaker 1] VI: Xin chào | EN: Hello"

    def test_multiple_segments_one_per_line(self):
        """Requirement 7.1: one line per segment."""
        segments = [
            make_segment(
                speaker_label="Speaker 1",
                text_vi="Xin chào",
                text_en="Hello",
                segment_id="seg-1",
            ),
            make_segment(
                speaker_label="Speaker 2",
                text_vi="Tạm biệt",
                text_en="Goodbye",
                segment_id="seg-2",
            ),
        ]
        result = serialize_transcript_to_txt(segments)
        lines = result.split("\n")
        assert len(lines) == 2
        assert lines[0] == "[Speaker 1] VI: Xin chào | EN: Hello"
        assert lines[1] == "[Speaker 2] VI: Tạm biệt | EN: Goodbye"

    def test_ordering_matches_input_order(self):
        """Requirement 7.2: ordered by finalization sequence (input order)."""
        segments = [
            make_segment(
                speaker_label="Speaker 2",
                text_vi="B",
                text_en="B_en",
                segment_id="seg-2",
            ),
            make_segment(
                speaker_label="Speaker 1",
                text_vi="A",
                text_en="A_en",
                segment_id="seg-1",
            ),
        ]
        result = serialize_transcript_to_txt(segments)
        lines = result.split("\n")
        assert lines[0] == "[Speaker 2] VI: B | EN: B_en"
        assert lines[1] == "[Speaker 1] VI: A | EN: A_en"

    def test_segment_with_empty_text_fields(self):
        """Handles segments with empty text fields."""
        seg = make_segment(text_vi="", text_en="")
        result = serialize_transcript_to_txt([seg])
        assert result == "[Speaker 1] VI:  | EN: "

    def test_spoken_language_en_segment(self):
        """English-spoken segments are serialized the same way."""
        seg = make_segment(
            speaker_label="Speaker 1",
            text_vi="Xin chào",
            text_en="Hello",
            spoken_language="en",
        )
        result = serialize_transcript_to_txt([seg])
        assert result == "[Speaker 1] VI: Xin chào | EN: Hello"

    def test_many_segments_correct_count(self):
        segments = [
            make_segment(segment_id=f"seg-{i}", text_vi=f"VI-{i}", text_en=f"EN-{i}")
            for i in range(10)
        ]
        result = serialize_transcript_to_txt(segments)
        lines = result.split("\n")
        assert len(lines) == 10

    def test_speaker_label_in_brackets(self):
        seg = make_segment(speaker_label="Speaker 3")
        result = serialize_transcript_to_txt([seg])
        assert result.startswith("[Speaker 3]")


# ---------------------------------------------------------------------------
# generate_s3_object_key
# ---------------------------------------------------------------------------


class TestGenerateS3ObjectKey:
    def test_key_contains_session_id(self):
        """Requirement 8.2: key includes Session_ID."""
        session_id = "test-session-123"
        key = generate_s3_object_key(session_id)
        assert session_id in key

    def test_key_starts_with_transcripts_prefix(self):
        """Key follows the transcripts/{session_id}/{timestamp}.txt pattern."""
        key = generate_s3_object_key("sess-abc")
        assert key.startswith("transcripts/")

    def test_key_ends_with_txt(self):
        key = generate_s3_object_key("sess-abc")
        assert key.endswith(".txt")

    def test_key_format_matches_pattern(self):
        """Key matches transcripts/{session_id}/{timestamp}.txt pattern."""
        session_id = "my-session-id"
        key = generate_s3_object_key(session_id)
        # Pattern: transcripts/<session_id>/<date>-<time>-<microseconds>.txt
        pattern = rf"^transcripts/{re.escape(session_id)}/\d{{8}}-\d{{6}}-\d+\.txt$"
        assert re.match(pattern, key), f"Key '{key}' does not match pattern"

    def test_two_calls_produce_different_keys(self):
        """Keys must be unique to avoid bucket collisions (Requirement 8.2)."""
        import time

        session_id = "same-session"
        key1 = generate_s3_object_key(session_id)
        time.sleep(0.001)  # Ensure timestamps differ
        key2 = generate_s3_object_key(session_id)
        # Different timestamps ensure uniqueness
        assert key1 != key2

    def test_different_sessions_produce_different_keys(self):
        key1 = generate_s3_object_key("session-A")
        key2 = generate_s3_object_key("session-B")
        assert key1 != key2


# ---------------------------------------------------------------------------
# upload_transcript_to_s3 (mocked S3)
# ---------------------------------------------------------------------------


class TestUploadTranscriptToS3:
    def test_successful_upload_calls_put_object(self):
        """Upload should call put_object with correct parameters."""
        mock_client = MagicMock()
        with patch("boto3.client", return_value=mock_client):
            upload_transcript_to_s3(
                bucket="my-bucket",
                key="transcripts/sess/file.txt",
                content="hello world",
                session_id="sess-1",
                region="us-east-1",
            )
        mock_client.put_object.assert_called_once()
        call_kwargs = mock_client.put_object.call_args[1]
        assert call_kwargs["Bucket"] == "my-bucket"
        assert call_kwargs["Key"] == "transcripts/sess/file.txt"
        assert call_kwargs["Body"] == b"hello world"
        assert "text/plain" in call_kwargs["ContentType"]

    def test_upload_error_raises_upload_error(self):
        """Requirement 8.4: on upload failure, raise UploadError."""
        from botocore.exceptions import ClientError

        mock_client = MagicMock()
        mock_client.put_object.side_effect = ClientError(
            {"Error": {"Code": "NoSuchBucket", "Message": "Bucket does not exist"}},
            "PutObject",
        )
        with patch("boto3.client", return_value=mock_client):
            with pytest.raises(UploadError):
                upload_transcript_to_s3(
                    bucket="bad-bucket",
                    key="transcripts/sess/file.txt",
                    content="content",
                    session_id="sess-1",
                )

    def test_upload_error_logs_to_logging_service(self):
        """Requirement 8.4: upload failure is recorded through Logging_Service."""
        from botocore.exceptions import ClientError

        mock_client = MagicMock()
        mock_client.put_object.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "Access Denied"}},
            "PutObject",
        )
        with patch("boto3.client", return_value=mock_client):
            with patch(
                "app.services.storage.log_integration_error"
            ) as mock_log:
                with pytest.raises(UploadError):
                    upload_transcript_to_s3(
                        bucket="bucket",
                        key="key",
                        content="content",
                        session_id="sess-1",
                    )
                mock_log.assert_called_once()
                call_args = mock_log.call_args
                assert call_args[0][0] == "sess-1"  # session_id
                assert "Amazon S3" in call_args[0][1]  # service_name

    def test_content_encoded_as_utf8(self):
        """TXT content with Unicode (Vietnamese) is encoded as UTF-8."""
        mock_client = MagicMock()
        with patch("boto3.client", return_value=mock_client):
            upload_transcript_to_s3(
                bucket="bucket",
                key="key.txt",
                content="Xin chào thế giới",
                session_id="sess-1",
            )
        call_kwargs = mock_client.put_object.call_args[1]
        assert call_kwargs["Body"] == "Xin chào thế giới".encode("utf-8")


# ---------------------------------------------------------------------------
# generate_presigned_download_link (mocked S3)
# ---------------------------------------------------------------------------


class TestGeneratePresignedDownloadLink:
    def test_returns_presigned_url(self):
        """Requirement 9.1, 9.3: generate a presigned URL with expiration."""
        mock_client = MagicMock()
        mock_client.generate_presigned_url.return_value = (
            "https://s3.amazonaws.com/bucket/key?Signature=abc"
        )
        with patch("boto3.client", return_value=mock_client):
            url = generate_presigned_download_link(
                bucket="bucket",
                key="transcripts/sess/file.txt",
                expiration_seconds=86400,
            )
        assert url.startswith("https://")
        mock_client.generate_presigned_url.assert_called_once_with(
            "get_object",
            Params={"Bucket": "bucket", "Key": "transcripts/sess/file.txt"},
            ExpiresIn=86400,
        )

    def test_passes_expiration_seconds(self):
        """Requirement 9.3: configurable expiration time."""
        mock_client = MagicMock()
        mock_client.generate_presigned_url.return_value = "https://url"
        with patch("boto3.client", return_value=mock_client):
            generate_presigned_download_link(
                bucket="b",
                key="k",
                expiration_seconds=3600,
            )
        call_kwargs = mock_client.generate_presigned_url.call_args[1]
        assert call_kwargs["ExpiresIn"] == 3600

    def test_raises_storage_error_on_failure(self):
        """Presigned URL generation failure raises StorageError."""
        from botocore.exceptions import ClientError

        mock_client = MagicMock()
        mock_client.generate_presigned_url.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "Denied"}},
            "GeneratePresignedUrl",
        )
        with patch("boto3.client", return_value=mock_client):
            with pytest.raises(StorageError):
                generate_presigned_download_link(
                    bucket="b", key="k", expiration_seconds=3600
                )


# ---------------------------------------------------------------------------
# store_transcript_and_get_download_link (full workflow, mocked S3)
# ---------------------------------------------------------------------------


class TestStoreTranscriptAndGetDownloadLink:
    def _mock_s3_client(self, presigned_url: str = "https://presigned-url") -> MagicMock:
        mock_client = MagicMock()
        mock_client.generate_presigned_url.return_value = presigned_url
        return mock_client

    def test_successful_workflow_returns_url_and_expiry(self):
        """Requirements 8.5, 9.2: returns download_url and expires_at on success."""
        mock_client = self._mock_s3_client("https://presigned-url")
        segments = [make_segment()]
        with patch("boto3.client", return_value=mock_client):
            url, expires_at = store_transcript_and_get_download_link(
                session_id="sess-1",
                segments=segments,
                bucket="bucket",
                expiration_seconds=86400,
            )
        assert url == "https://presigned-url"
        assert isinstance(expires_at, datetime)
        assert expires_at > datetime.now(timezone.utc)

    def test_expires_at_is_approximately_correct(self):
        """expires_at should be roughly now + expiration_seconds."""
        from datetime import timedelta

        mock_client = self._mock_s3_client()
        segments = [make_segment()]
        before = datetime.now(timezone.utc)
        with patch("boto3.client", return_value=mock_client):
            _, expires_at = store_transcript_and_get_download_link(
                session_id="sess-1",
                segments=segments,
                bucket="bucket",
                expiration_seconds=3600,
            )
        after = datetime.now(timezone.utc)
        expected_min = before + timedelta(seconds=3600)
        expected_max = after + timedelta(seconds=3600)
        assert expected_min <= expires_at <= expected_max

    def test_empty_transcript_still_uploads(self):
        """Requirement 7.3: empty transcript is uploaded (empty file)."""
        mock_client = self._mock_s3_client()
        with patch("boto3.client", return_value=mock_client):
            url, _ = store_transcript_and_get_download_link(
                session_id="sess-empty",
                segments=[],
                bucket="bucket",
                expiration_seconds=3600,
            )
        # put_object was called
        mock_client.put_object.assert_called_once()
        # Body is empty bytes
        call_kwargs = mock_client.put_object.call_args[1]
        assert call_kwargs["Body"] == b""

    def test_key_contains_session_id(self):
        """Requirement 8.2: key includes session_id."""
        mock_client = self._mock_s3_client()
        with patch("boto3.client", return_value=mock_client):
            store_transcript_and_get_download_link(
                session_id="my-unique-session",
                segments=[make_segment()],
                bucket="bucket",
                expiration_seconds=3600,
            )
        call_kwargs = mock_client.put_object.call_args[1]
        assert "my-unique-session" in call_kwargs["Key"]

    def test_upload_failure_raises_upload_error(self):
        """Requirement 8.4: upload failure raises UploadError."""
        from botocore.exceptions import ClientError

        mock_client = MagicMock()
        mock_client.put_object.side_effect = ClientError(
            {"Error": {"Code": "InternalError", "Message": "S3 error"}},
            "PutObject",
        )
        with patch("boto3.client", return_value=mock_client):
            with pytest.raises(UploadError):
                store_transcript_and_get_download_link(
                    session_id="sess-fail",
                    segments=[make_segment()],
                    bucket="bucket",
                    expiration_seconds=3600,
                )
