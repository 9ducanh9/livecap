"""Unit tests for backend/app/services/translation.py.

Tests cover:
- Correct translation directionality: vi → en and en → vi (CP-8, Req 5.1)
- Source text placed in the correct column; translated text in the other
- A language is never translated into itself (CP-8)
- Empty source text passes through without calling Translate
- On Translate error, source segment is returned and error is logged (Req 5.3)
- Async execution (does not block)
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models import Segment
from app.services.translation import TranslationService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_vi_segment(text: str = "Xin chào thế giới") -> Segment:
    """Return a Vietnamese Finalized_Segment."""
    return Segment(
        segment_id="seg-1",
        speaker_label="Speaker 1",
        text_vi=text,
        text_en="",
        spoken_language="vi",
        is_final=True,
        timestamp_start=0.0,
        timestamp_end=1.0,
    )


def make_en_segment(text: str = "Hello world") -> Segment:
    """Return an English Finalized_Segment."""
    return Segment(
        segment_id="seg-2",
        speaker_label="Speaker 1",
        text_vi="",
        text_en=text,
        spoken_language="en",
        is_final=True,
        timestamp_start=0.0,
        timestamp_end=1.0,
    )


def run(coro):
    """Run a coroutine synchronously in tests."""
    return asyncio.run(coro)


def make_service_with_mock(translated_return: str) -> tuple[TranslationService, MagicMock]:
    """Return a TranslationService whose boto3 client is mocked."""
    mock_client = MagicMock()
    mock_client.translate_text.return_value = {"TranslatedText": translated_return}

    service = TranslationService.__new__(TranslationService)
    service._region = "us-east-1"
    service._client = mock_client

    # Use real logger (already configured via logging_service or default)
    import logging
    service._logger = logging.getLogger("livecap_test")

    return service, mock_client


# ---------------------------------------------------------------------------
# Translation directionality (CP-8 / Req 5.1)
# ---------------------------------------------------------------------------


class TestTranslationDirectionality:
    def test_default_region_is_singapore(self):
        with patch("boto3.client") as mock_boto_client:
            TranslationService()

        mock_boto_client.assert_called_once_with(
            "translate", region_name="ap-southeast-1"
        )

    def test_vi_segment_translates_to_en(self):
        """spoken vi → translated text placed in text_en, source stays in text_vi."""
        service, mock_client = make_service_with_mock("Hello world")

        segment = make_vi_segment("Xin chào thế giới")
        result = run(service.translate_segment(segment, session_id="sess-1"))

        mock_client.translate_text.assert_called_once_with(
            Text="Xin chào thế giới",
            SourceLanguageCode="vi",
            TargetLanguageCode="en",
        )
        assert result.text_vi == "Xin chào thế giới"
        assert result.text_en == "Hello world"
        assert result.spoken_language == "vi"

    def test_en_segment_translates_to_vi(self):
        """spoken en → translated text placed in text_vi, source stays in text_en."""
        service, mock_client = make_service_with_mock("Xin chào thế giới")

        segment = make_en_segment("Hello world")
        result = run(service.translate_segment(segment, session_id="sess-1"))

        mock_client.translate_text.assert_called_once_with(
            Text="Hello world",
            SourceLanguageCode="en",
            TargetLanguageCode="vi",
        )
        assert result.text_en == "Hello world"
        assert result.text_vi == "Xin chào thế giới"
        assert result.spoken_language == "en"

    def test_vi_never_translates_vi_to_vi(self):
        """The source language must never equal the target language for vi input."""
        service, mock_client = make_service_with_mock("something")

        run(service.translate_segment(make_vi_segment(), session_id="sess-1"))

        call_kwargs = mock_client.translate_text.call_args[1]
        assert call_kwargs["SourceLanguageCode"] != call_kwargs["TargetLanguageCode"]
        assert call_kwargs["TargetLanguageCode"] == "en"

    def test_en_never_translates_en_to_en(self):
        """The source language must never equal the target language for en input."""
        service, mock_client = make_service_with_mock("something")

        run(service.translate_segment(make_en_segment(), session_id="sess-1"))

        call_kwargs = mock_client.translate_text.call_args[1]
        assert call_kwargs["SourceLanguageCode"] != call_kwargs["TargetLanguageCode"]
        assert call_kwargs["TargetLanguageCode"] == "vi"


# ---------------------------------------------------------------------------
# Source text column placement
# ---------------------------------------------------------------------------


class TestColumnPlacement:
    def test_vi_source_text_stays_in_text_vi(self):
        """The originally-spoken Vietnamese text should remain in text_vi."""
        service, _ = make_service_with_mock("Translation result")
        original_vi = "Đây là văn bản gốc"
        result = run(
            service.translate_segment(make_vi_segment(original_vi), session_id="s1")
        )
        assert result.text_vi == original_vi

    def test_en_source_text_stays_in_text_en(self):
        """The originally-spoken English text should remain in text_en."""
        service, _ = make_service_with_mock("Kết quả dịch")
        original_en = "This is the original text"
        result = run(
            service.translate_segment(make_en_segment(original_en), session_id="s1")
        )
        assert result.text_en == original_en

    def test_translated_vi_text_goes_into_text_en(self):
        """For a vi segment, translation result populates text_en."""
        service, _ = make_service_with_mock("English translation here")
        result = run(service.translate_segment(make_vi_segment(), session_id="s1"))
        assert result.text_en == "English translation here"

    def test_translated_en_text_goes_into_text_vi(self):
        """For an en segment, translation result populates text_vi."""
        service, _ = make_service_with_mock("Bản dịch tiếng Việt")
        result = run(service.translate_segment(make_en_segment(), session_id="s1"))
        assert result.text_vi == "Bản dịch tiếng Việt"


# ---------------------------------------------------------------------------
# Empty source text
# ---------------------------------------------------------------------------


class TestEmptySourceText:
    def test_empty_vi_text_skips_translate_call(self):
        """If text_vi is empty for a vi segment, no API call should be made."""
        service, mock_client = make_service_with_mock("unused")
        segment = make_vi_segment(text="")
        result = run(service.translate_segment(segment, session_id="sess-empty"))
        mock_client.translate_text.assert_not_called()
        assert result.text_vi == ""
        assert result.text_en == ""

    def test_empty_en_text_skips_translate_call(self):
        """If text_en is empty for an en segment, no API call should be made."""
        service, mock_client = make_service_with_mock("unused")
        segment = make_en_segment(text="")
        result = run(service.translate_segment(segment, session_id="sess-empty"))
        mock_client.translate_text.assert_not_called()
        assert result.text_vi == ""
        assert result.text_en == ""

    def test_whitespace_only_text_skips_translate_call(self):
        """Whitespace-only text should be treated as empty and not translated."""
        service, mock_client = make_service_with_mock("unused")
        segment = make_vi_segment(text="   ")
        run(service.translate_segment(segment, session_id="s"))
        mock_client.translate_text.assert_not_called()


# ---------------------------------------------------------------------------
# Error handling (Req 5.3)
# ---------------------------------------------------------------------------


class TestErrorHandling:
    def test_translate_error_returns_source_segment(self):
        """On a Translate error, the source segment is returned without translation."""
        from botocore.exceptions import ClientError

        mock_client = MagicMock()
        mock_client.translate_text.side_effect = ClientError(
            {"Error": {"Code": "ServiceUnavailableException", "Message": "Service down"}},
            "TranslateText",
        )
        import logging
        service = TranslationService.__new__(TranslationService)
        service._region = "us-east-1"
        service._client = mock_client
        service._logger = logging.getLogger("livecap_test")

        segment = make_vi_segment("Xin chào")
        result = run(service.translate_segment(segment, session_id="sess-err"))

        # Should return original segment with source text intact
        assert result.text_vi == "Xin chào"
        # text_en should remain empty (no successful translation)
        assert result.text_en == ""
        # Segment_ID and other fields preserved
        assert result.segment_id == segment.segment_id
        assert result.spoken_language == "vi"

    def test_translate_error_logs_error(self):
        """On a Translate error, log_integration_error should be called."""
        from botocore.exceptions import BotoCoreError

        mock_client = MagicMock()
        mock_client.translate_text.side_effect = BotoCoreError()

        import logging
        service = TranslationService.__new__(TranslationService)
        service._region = "us-east-1"
        service._client = mock_client
        service._logger = logging.getLogger("livecap_test")

        with patch(
            "app.services.translation.log_integration_error"
        ) as mock_log_error:
            run(
                service.translate_segment(
                    make_vi_segment("Xin chào"), session_id="sess-err"
                )
            )
            mock_log_error.assert_called_once()
            call_kwargs = mock_log_error.call_args
            assert call_kwargs[1]["session_id"] == "sess-err" or \
                   call_kwargs[0][0] == "sess-err"
            # Service name should reference Amazon Translate
            service_arg = call_kwargs[1].get("service_name") or call_kwargs[0][1]
            assert "Translate" in service_arg

    def test_generic_exception_returns_source_segment(self):
        """A generic RuntimeError from Translate also returns the source segment."""
        mock_client = MagicMock()
        mock_client.translate_text.side_effect = RuntimeError("Unexpected error")

        import logging
        service = TranslationService.__new__(TranslationService)
        service._region = "us-east-1"
        service._client = mock_client
        service._logger = logging.getLogger("livecap_test")

        segment = make_en_segment("Hello")
        result = run(service.translate_segment(segment, session_id="sess-generic"))

        assert result.text_en == "Hello"
        assert result.text_vi == ""

    def test_en_translate_error_returns_source_segment(self):
        """Error for an en segment: text_en preserved, text_vi remains empty."""
        from botocore.exceptions import ClientError

        mock_client = MagicMock()
        mock_client.translate_text.side_effect = ClientError(
            {"Error": {"Code": "ThrottlingException", "Message": "Rate limit"}},
            "TranslateText",
        )
        import logging
        service = TranslationService.__new__(TranslationService)
        service._region = "us-east-1"
        service._client = mock_client
        service._logger = logging.getLogger("livecap_test")

        segment = make_en_segment("This is English text")
        result = run(service.translate_segment(segment, session_id="sess-en-err"))

        assert result.text_en == "This is English text"
        assert result.text_vi == ""


# ---------------------------------------------------------------------------
# Segment immutability
# ---------------------------------------------------------------------------


class TestSegmentImmutability:
    def test_original_segment_not_mutated_on_success(self):
        """translate_segment should never mutate the input Segment."""
        service, _ = make_service_with_mock("Hello")
        original = make_vi_segment("Xin chào")
        original_en_before = original.text_en

        run(service.translate_segment(original, session_id="s1"))

        assert original.text_en == original_en_before  # unchanged

    def test_original_segment_not_mutated_on_error(self):
        """Even on error, translate_segment must not mutate the input Segment."""
        mock_client = MagicMock()
        mock_client.translate_text.side_effect = RuntimeError("fail")

        import logging
        service = TranslationService.__new__(TranslationService)
        service._region = "us-east-1"
        service._client = mock_client
        service._logger = logging.getLogger("livecap_test")

        original = make_vi_segment("Xin chào")
        run(service.translate_segment(original, session_id="s1"))

        assert original.text_en == ""  # not mutated
