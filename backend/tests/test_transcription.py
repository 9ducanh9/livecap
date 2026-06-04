"""Unit tests for backend/app/services/transcription.py.

Tests cover:
- Speaker label resolution: raw Transcribe labels → "Speaker N" (Req 4.1, 4.2, 4.4)
- Spoken language resolution: Transcribe language codes → internal short codes (Req 3.2)
- Segment ID reuse across partial revisions and uniqueness for finalized segments (Req 3.4, 3.5)
- Partial and finalized message construction from Transcribe events (Req 3.2, 3.3)
- Error logging and propagation (Req 3.7)
- Real-time streaming: messages are yielded as they arrive, not only after session ends
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import Settings
from app.models import (
    FinalizedSegmentMessage,
    PartialSegmentMessage,
    SegmentIdAllocator,
)
from app.services.transcription import (
    TranscriptionService,
    _extract_language_code,
    _extract_speaker_label,
    _extract_timestamps,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_settings(**overrides) -> Settings:
    defaults = dict(
        aws_region="us-east-1",
        s3_bucket="test-bucket",
        download_link_expiration=86400,
        session_timeout=1800,
        max_speakers=5,
        transcribe_language_code="vi-VN",
        allowed_origin="http://localhost:5173",
        cloudwatch_log_group="livecap",
    )
    defaults.update(overrides)
    return Settings(**defaults)


def make_service(session_id: str = "test-session") -> TranscriptionService:
    return TranscriptionService(session_id=session_id, settings=make_settings())


# ---------------------------------------------------------------------------
# Speaker label resolution (Req 4.1, 4.2, 4.4)
# ---------------------------------------------------------------------------


class TestSpeakerLabelResolution:
    def test_first_speaker_gets_speaker_1(self):
        """The first raw label seen is mapped to 'Speaker 1'."""
        service = make_service()
        label = service._resolve_speaker_label("spk_0")
        assert label == "Speaker 1"

    def test_second_distinct_speaker_gets_speaker_2(self):
        """The second distinct raw label is mapped to 'Speaker 2'."""
        service = make_service()
        service._resolve_speaker_label("spk_0")
        label = service._resolve_speaker_label("spk_1")
        assert label == "Speaker 2"

    def test_same_raw_label_always_returns_same_human_label(self):
        """The same raw label must always map to the same human-readable label."""
        service = make_service()
        label1 = service._resolve_speaker_label("spk_0")
        label1_again = service._resolve_speaker_label("spk_0")
        assert label1 == label1_again == "Speaker 1"

    def test_speaker_labels_are_sequential(self):
        """Multiple new speakers receive sequential integers starting at 1."""
        service = make_service()
        labels = [
            service._resolve_speaker_label(f"spk_{i}") for i in range(4)
        ]
        assert labels == ["Speaker 1", "Speaker 2", "Speaker 3", "Speaker 4"]

    def test_interleaved_speakers_stay_consistent(self):
        """Interleaved raw labels still produce consistent human-readable labels."""
        service = make_service()
        # spk_0 → Speaker 1, spk_1 → Speaker 2, then back to spk_0 → Speaker 1
        assert service._resolve_speaker_label("spk_0") == "Speaker 1"
        assert service._resolve_speaker_label("spk_1") == "Speaker 2"
        assert service._resolve_speaker_label("spk_0") == "Speaker 1"
        assert service._resolve_speaker_label("spk_1") == "Speaker 2"

    def test_speaker_label_format_contains_word_speaker(self):
        """Every resolved label starts with the word 'Speaker'."""
        service = make_service()
        for raw in ("spk_0", "spk_1", "spk_2"):
            label = service._resolve_speaker_label(raw)
            assert label.startswith("Speaker "), f"Unexpected label: {label!r}"

    def test_speaker_label_number_is_positive_integer(self):
        """The numeric suffix of every resolved label is a positive integer ≥ 1."""
        service = make_service()
        for i, raw in enumerate(("spk_0", "spk_1", "spk_2")):
            label = service._resolve_speaker_label(raw)
            parts = label.split(" ")
            assert len(parts) == 2
            num = int(parts[1])
            assert num == i + 1


# ---------------------------------------------------------------------------
# Spoken language resolution (Req 3.2)
# ---------------------------------------------------------------------------


class TestSpokenLanguageResolution:
    def test_vi_vn_maps_to_vi(self):
        service = make_service()
        assert service._resolve_spoken_language("vi-VN") == "vi"

    def test_en_us_maps_to_en(self):
        service = make_service()
        assert service._resolve_spoken_language("en-US") == "en"

    def test_none_defaults_to_vi(self):
        """None (language not yet identified) defaults to 'vi'."""
        service = make_service()
        assert service._resolve_spoken_language(None) == "vi"

    def test_unknown_code_defaults_to_vi(self):
        """An unrecognised language code falls back to 'vi'."""
        service = make_service()
        assert service._resolve_spoken_language("fr-FR") == "vi"

    def test_missing_language_uses_configured_language(self):
        """When Transcribe omits per-result language, use the configured code."""
        service = TranscriptionService(
            session_id="test-session",
            settings=make_settings(transcribe_language_code="en-US"),
        )
        assert service._resolve_spoken_language(None) == "en"


# ---------------------------------------------------------------------------
# Extraction helpers
# ---------------------------------------------------------------------------


class TestExtractSpeakerLabel:
    def test_returns_first_non_empty_label(self):
        item1 = MagicMock(speaker_label="")
        item2 = MagicMock(speaker_label="spk_1")
        alternative = MagicMock(items=[item1, item2])
        assert _extract_speaker_label(alternative) == "spk_1"

    def test_fallback_when_no_items(self):
        alternative = MagicMock(items=[])
        assert _extract_speaker_label(alternative) == "spk_0"

    def test_fallback_when_no_items_attr(self):
        alternative = MagicMock(spec=[])  # no 'items' attribute
        assert _extract_speaker_label(alternative) == "spk_0"

    def test_fallback_when_all_labels_empty(self):
        items = [MagicMock(speaker_label=""), MagicMock(speaker_label="")]
        alternative = MagicMock(items=items)
        assert _extract_speaker_label(alternative) == "spk_0"


class TestExtractLanguageCode:
    def test_language_code_attribute(self):
        result = MagicMock(language_code="vi-VN", language_identification=None)
        assert _extract_language_code(result) == "vi-VN"

    def test_language_identification_list(self):
        """When language_code is missing, use the highest-score entry in the list."""
        best = MagicMock(score=0.95, code="en-US")
        low = MagicMock(score=0.05, code="vi-VN")
        result = MagicMock(spec=["language_identification"])
        result.language_identification = [best, low]
        assert _extract_language_code(result) == "en-US"

    def test_no_language_info_returns_none(self):
        result = MagicMock(spec=[])
        assert _extract_language_code(result) is None


class TestExtractTimestamps:
    def test_extracts_start_and_end(self):
        result = MagicMock(start_time=1.23, end_time=4.56)
        start, end = _extract_timestamps(result)
        assert start == pytest.approx(1.23)
        assert end == pytest.approx(4.56)

    def test_fallback_to_zero_when_none(self):
        result = MagicMock(start_time=None, end_time=None)
        assert _extract_timestamps(result) == (0.0, 0.0)

    def test_fallback_when_no_attr(self):
        result = MagicMock(spec=[])
        assert _extract_timestamps(result) == (0.0, 0.0)


# ---------------------------------------------------------------------------
# Integration: message building from mocked Transcribe events
# ---------------------------------------------------------------------------


def _make_result(
    result_id: str,
    is_partial: bool,
    transcript_text: str,
    speaker_label: str = "spk_0",
    language_code: str = "vi-VN",
    start_time: float = 0.0,
    end_time: float = 1.0,
) -> MagicMock:
    """Build a mock Transcribe result object."""
    item = MagicMock(speaker_label=speaker_label)
    alternative = MagicMock(
        transcript=transcript_text,
        items=[item],
    )
    result = MagicMock(
        result_id=result_id,
        is_partial=is_partial,
        alternatives=[alternative],
        language_code=language_code,
        language_identification=None,
        start_time=start_time,
        end_time=end_time,
    )
    return result


def _make_transcript_event(*results) -> MagicMock:
    transcript = MagicMock(results=list(results))
    return MagicMock(transcript=transcript)


async def _collect_handler_events(service: TranscriptionService, *events) -> list:
    """Feed TranscriptEvents through a _SegmentHandler and return queued messages."""
    from app.services.transcription import _SegmentHandler

    queue: asyncio.Queue = asyncio.Queue()

    # Create a dummy output stream (not used by handle_transcript_event)
    dummy_stream = MagicMock()

    handler = _SegmentHandler(
        dummy_stream,
        result_queue=queue,
        id_allocator=service._id_allocator,
        speaker_map=service._speaker_map,
        next_speaker_num_ref=service,
        logger=service._logger,
        session_id=service._session_id,
    )

    for event in events:
        await handler.handle_transcript_event(event)

    messages = []
    while not queue.empty():
        messages.append(queue.get_nowait())
    return messages


class TestHandlerMessageBuilding:
    def test_partial_result_produces_partial_segment_message(self):
        service = make_service()
        event = _make_transcript_event(
            _make_result("r1", is_partial=True, transcript_text="xin")
        )
        msgs = asyncio.run(_collect_handler_events(service, event))
        assert len(msgs) == 1
        assert isinstance(msgs[0], PartialSegmentMessage)
        assert msgs[0].is_final is False
        assert msgs[0].text_vi == "xin"

    def test_final_result_produces_finalized_segment_message(self):
        service = make_service()
        event = _make_transcript_event(
            _make_result("r1", is_partial=False, transcript_text="xin chào", end_time=2.0)
        )
        msgs = asyncio.run(_collect_handler_events(service, event))
        assert len(msgs) == 1
        assert isinstance(msgs[0], FinalizedSegmentMessage)
        assert msgs[0].is_final is True
        assert msgs[0].text_vi == "xin chào"
        assert msgs[0].timestamp_end == pytest.approx(2.0)

    def test_partial_revisions_reuse_same_segment_id(self):
        """CP-2: Partial revisions of the same result_id share one Segment_ID."""
        service = make_service()
        event1 = _make_transcript_event(
            _make_result("r1", is_partial=True, transcript_text="hello")
        )
        event2 = _make_transcript_event(
            _make_result("r1", is_partial=True, transcript_text="hello world")
        )
        msgs = asyncio.run(_collect_handler_events(service, event1, event2))
        assert len(msgs) == 2
        assert msgs[0].segment_id == msgs[1].segment_id

    def test_finalized_segment_id_matches_partial_id(self):
        """CP-2: Finalized segment reuses the same ID as its preceding partial."""
        service = make_service()
        partial_event = _make_transcript_event(
            _make_result("r1", is_partial=True, transcript_text="hello")
        )
        final_event = _make_transcript_event(
            _make_result("r1", is_partial=False, transcript_text="hello world")
        )
        msgs = asyncio.run(_collect_handler_events(service, partial_event, final_event))
        assert len(msgs) == 2
        assert msgs[0].segment_id == msgs[1].segment_id
        assert isinstance(msgs[0], PartialSegmentMessage)
        assert isinstance(msgs[1], FinalizedSegmentMessage)

    def test_two_distinct_results_get_different_segment_ids(self):
        """Two distinct result_ids must produce different Segment_IDs."""
        service = make_service()
        event1 = _make_transcript_event(
            _make_result("r1", is_partial=False, transcript_text="first phrase")
        )
        event2 = _make_transcript_event(
            _make_result("r2", is_partial=False, transcript_text="second phrase")
        )
        msgs = asyncio.run(_collect_handler_events(service, event1, event2))
        assert len(msgs) == 2
        assert msgs[0].segment_id != msgs[1].segment_id

    def test_en_result_populates_text_en_not_text_vi(self):
        """English spoken text goes into text_en; text_vi remains empty."""
        service = make_service()
        event = _make_transcript_event(
            _make_result("r1", is_partial=False, transcript_text="hello", language_code="en-US")
        )
        msgs = asyncio.run(_collect_handler_events(service, event))
        assert msgs[0].text_en == "hello"
        assert msgs[0].text_vi == ""
        assert msgs[0].spoken_language == "en"

    def test_vi_result_populates_text_vi_not_text_en(self):
        """Vietnamese spoken text goes into text_vi; text_en remains empty."""
        service = make_service()
        event = _make_transcript_event(
            _make_result("r1", is_partial=False, transcript_text="xin chào", language_code="vi-VN")
        )
        msgs = asyncio.run(_collect_handler_events(service, event))
        assert msgs[0].text_vi == "xin chào"
        assert msgs[0].text_en == ""
        assert msgs[0].spoken_language == "vi"

    def test_speaker_label_formatted_correctly(self):
        """Speaker labels are formatted as 'Speaker N' (Req 4.4)."""
        service = make_service()
        event = _make_transcript_event(
            _make_result("r1", is_partial=True, transcript_text="hi", speaker_label="spk_0")
        )
        msgs = asyncio.run(_collect_handler_events(service, event))
        assert msgs[0].speaker_label == "Speaker 1"

    def test_result_with_no_alternatives_produces_no_message(self):
        """Results with no alternatives should be silently skipped."""
        service = make_service()
        result = MagicMock(result_id="r1", is_partial=True, alternatives=[])
        event = _make_transcript_event(result)
        msgs = asyncio.run(_collect_handler_events(service, event))
        assert msgs == []

    def test_handler_error_puts_exception_in_queue(self):
        """If processing raises an exception it is put onto the result_queue."""
        from app.services.transcription import _SegmentHandler

        async def run():
            queue: asyncio.Queue = asyncio.Queue()
            dummy_stream = MagicMock()
            service = make_service()

            handler = _SegmentHandler(
                dummy_stream,
                result_queue=queue,
                id_allocator=service._id_allocator,
                speaker_map=service._speaker_map,
                next_speaker_num_ref=service,
                logger=service._logger,
                session_id=service._session_id,
            )

            # An event that will raise when accessed
            bad_event = MagicMock()
            bad_event.transcript = MagicMock()
            bad_event.transcript.results = None  # iterating None raises TypeError

            await handler.handle_transcript_event(bad_event)

            assert not queue.empty()
            item = queue.get_nowait()
            assert isinstance(item, Exception)

        asyncio.run(run())


# ---------------------------------------------------------------------------
# Real-time streaming: messages yielded as they arrive (not only after done)
# ---------------------------------------------------------------------------


class TestRealTimeStreaming:
    """Verify transcribe() yields messages before the session completes."""

    def test_transcribe_yields_messages_as_they_arrive(self):
        """Messages must be yielded immediately, not only after gather completes."""

        yielded: list[Any] = []

        async def run_test():
            audio_q: asyncio.Queue[bytes | None] = asyncio.Queue()
            service = make_service()

            mock_input_stream = AsyncMock()
            mock_output_stream = MagicMock()

            mock_stream = MagicMock()
            mock_stream.input_stream = mock_input_stream
            mock_stream.output_stream = mock_output_stream

            mock_client = MagicMock()
            mock_client.start_stream_transcription = AsyncMock(return_value=mock_stream)

            partial_msg = PartialSegmentMessage(
                segment_id="seg-1",
                speaker_label="Speaker 1",
                text_vi="xin",
                text_en="",
                spoken_language="vi",
            )
            final_msg = FinalizedSegmentMessage(
                segment_id="seg-1",
                speaker_label="Speaker 1",
                text_vi="xin chào",
                text_en="",
                spoken_language="vi",
            )

            from app.services.transcription import _SegmentHandler

            async def patched_handle(self_h):
                await self_h._result_queue.put(partial_msg)
                await self_h._result_queue.put(final_msg)

            with (
                patch(
                    "app.services.transcription.TranscribeStreamingClient",
                    return_value=mock_client,
                ),
                patch.object(_SegmentHandler, "handle_events", patched_handle),
            ):
                # Put audio chunk + sentinel into the queue
                await audio_q.put(b"\x00" * 3200)
                await audio_q.put(None)

                async for msg in service.transcribe(audio_q):
                    yielded.append(msg)

        asyncio.run(run_test())

        # Both messages should have been yielded
        assert len(yielded) == 2
        assert isinstance(yielded[0], PartialSegmentMessage)
        assert isinstance(yielded[1], FinalizedSegmentMessage)

    def test_start_stream_uses_supported_fixed_language_args(self):
        """The installed SDK does not support multi-language detection kwargs."""

        async def run_test():
            audio_q: asyncio.Queue[bytes | None] = asyncio.Queue()
            await audio_q.put(None)

            service = TranscriptionService(
                session_id="test-session",
                settings=make_settings(transcribe_language_code="en-US"),
            )

            mock_input_stream = AsyncMock()
            mock_output_stream = MagicMock()

            mock_stream = MagicMock()
            mock_stream.input_stream = mock_input_stream
            mock_stream.output_stream = mock_output_stream

            mock_client = MagicMock()
            mock_client.start_stream_transcription = AsyncMock(return_value=mock_stream)

            from app.services.transcription import _SegmentHandler

            async def patched_handle(_self_h):
                return None

            with (
                patch(
                    "app.services.transcription.TranscribeStreamingClient",
                    return_value=mock_client,
                ),
                patch.object(_SegmentHandler, "handle_events", patched_handle),
            ):
                async for _ in service.transcribe(audio_q):
                    pass

            kwargs = mock_client.start_stream_transcription.call_args.kwargs
            assert kwargs["language_code"] == "en-US"
            assert kwargs["media_sample_rate_hz"] == 16000
            assert kwargs["media_encoding"] == "pcm"
            assert kwargs["show_speaker_label"] is True
            assert "identify_multiple_languages" not in kwargs
            assert "language_options" not in kwargs
            assert "preferred_language" not in kwargs
            assert "max_speaker_labels" not in kwargs

        asyncio.run(run_test())


# ---------------------------------------------------------------------------
# Error propagation (Req 3.7)
# ---------------------------------------------------------------------------


class TestErrorPropagation:
    def test_transcribe_start_error_is_logged_and_raised(self):
        """If start_stream_transcription raises, it is logged and re-raised."""

        async def run():
            service = make_service()
            audio_q: asyncio.Queue[bytes | None] = asyncio.Queue()

            mock_client = MagicMock()
            exc = RuntimeError("Transcribe unavailable")
            mock_client.start_stream_transcription = AsyncMock(side_effect=exc)

            with patch(
                "app.services.transcription.TranscribeStreamingClient",
                return_value=mock_client,
            ), patch(
                "app.services.transcription.log_integration_error"
            ) as mock_log:
                with pytest.raises(RuntimeError, match="Transcribe unavailable"):
                    async for _ in service.transcribe(audio_q):
                        pass  # pragma: no cover

                mock_log.assert_called_once()
                call_args = mock_log.call_args[0]
                assert call_args[0] == service._session_id
                assert "Transcribe" in call_args[1]
                assert call_args[2] is exc

        asyncio.run(run())
