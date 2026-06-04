"""Unit tests for backend/app/models.py.

Covers:
- Session and Segment domain model construction and field defaults
- WebSocket message models (SessionStartMessage, PartialSegmentMessage,
  FinalizedSegmentMessage, ErrorMessage, SessionEndMessage, StopMessage)
- from_segment factory helpers on message classes
- Export payload models (ExportRequest, ExportResponse, ExportSegment)
- SegmentIdAllocator: ID assignment, partial-revision reuse, finalization,
  and uniqueness of finalized IDs (Requirements 3.4, 3.5, 5.2)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from app.models import (
    ErrorCode,
    ErrorMessage,
    ExportRequest,
    ExportResponse,
    ExportSegment,
    FinalizedSegmentMessage,
    PartialSegmentMessage,
    Segment,
    SegmentIdAllocator,
    Session,
    SessionEndMessage,
    SessionStartMessage,
    StopMessage,
)


# ---------------------------------------------------------------------------
# Segment
# ---------------------------------------------------------------------------


class TestSegment:
    def test_required_fields(self):
        seg = Segment(
            segment_id="seg-1",
            speaker_label="Speaker 1",
            spoken_language="vi",
        )
        assert seg.segment_id == "seg-1"
        assert seg.speaker_label == "Speaker 1"
        assert seg.spoken_language == "vi"

    def test_defaults(self):
        seg = Segment(
            segment_id="seg-1",
            speaker_label="Speaker 1",
            spoken_language="en",
        )
        assert seg.text_vi == ""
        assert seg.text_en == ""
        assert seg.is_final is False
        assert seg.timestamp_start == 0.0
        assert seg.timestamp_end == 0.0

    def test_full_construction(self):
        seg = Segment(
            segment_id="seg-2",
            speaker_label="Speaker 2",
            text_vi="Xin chào",
            text_en="Hello",
            spoken_language="vi",
            is_final=True,
            timestamp_start=1.5,
            timestamp_end=3.0,
        )
        assert seg.text_vi == "Xin chào"
        assert seg.text_en == "Hello"
        assert seg.is_final is True
        assert seg.timestamp_start == 1.5
        assert seg.timestamp_end == 3.0

    def test_spoken_language_en(self):
        seg = Segment(
            segment_id="seg-3",
            speaker_label="Speaker 1",
            text_en="Hello world",
            spoken_language="en",
        )
        assert seg.spoken_language == "en"

    def test_invalid_spoken_language_raises(self):
        with pytest.raises(Exception):
            Segment(
                segment_id="seg-4",
                speaker_label="Speaker 1",
                spoken_language="fr",  # not valid
            )


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------


class TestSession:
    def test_auto_session_id(self):
        session = Session()
        # Should be a valid UUID
        uuid.UUID(session.session_id)

    def test_auto_started_at(self):
        session = Session()
        assert isinstance(session.started_at, datetime)
        assert session.started_at.tzinfo is not None  # timezone-aware

    def test_defaults(self):
        session = Session()
        assert session.ended_at is None
        assert session.segments == []

    def test_explicit_session_id(self):
        sid = str(uuid.uuid4())
        session = Session(session_id=sid)
        assert session.session_id == sid

    def test_unique_session_ids(self):
        s1 = Session()
        s2 = Session()
        assert s1.session_id != s2.session_id

    def test_add_segments(self):
        seg = Segment(
            segment_id="seg-1",
            speaker_label="Speaker 1",
            spoken_language="vi",
        )
        session = Session()
        session.segments.append(seg)
        assert len(session.segments) == 1
        assert session.segments[0].segment_id == "seg-1"

    def test_ended_at_can_be_set(self):
        now = datetime.now(timezone.utc)
        session = Session(ended_at=now)
        assert session.ended_at == now


# ---------------------------------------------------------------------------
# WebSocket messages: Backend → Frontend
# ---------------------------------------------------------------------------


class TestSessionStartMessage:
    def test_defaults(self):
        msg = SessionStartMessage(session_id="abc-123")
        assert msg.type == "session_start"
        assert msg.session_id == "abc-123"

    def test_serialization(self):
        msg = SessionStartMessage(session_id="abc-123")
        data = msg.model_dump()
        assert data == {"type": "session_start", "session_id": "abc-123"}


class TestPartialSegmentMessage:
    def test_is_final_locked_to_false(self):
        msg = PartialSegmentMessage(
            segment_id="seg-1",
            speaker_label="Speaker 1",
            spoken_language="vi",
        )
        assert msg.is_final is False
        assert msg.type == "partial_segment"

    def test_from_segment(self):
        seg = Segment(
            segment_id="seg-5",
            speaker_label="Speaker 2",
            text_vi="Xin chào",
            text_en="",
            spoken_language="vi",
        )
        msg = PartialSegmentMessage.from_segment(seg)
        assert msg.segment_id == "seg-5"
        assert msg.speaker_label == "Speaker 2"
        assert msg.text_vi == "Xin chào"
        assert msg.text_en == ""
        assert msg.spoken_language == "vi"
        assert msg.is_final is False
        assert msg.type == "partial_segment"

    def test_from_segment_does_not_include_timestamps(self):
        seg = Segment(
            segment_id="seg-6",
            speaker_label="Speaker 1",
            spoken_language="en",
            timestamp_start=1.0,
            timestamp_end=2.0,
        )
        msg = PartialSegmentMessage.from_segment(seg)
        # PartialSegmentMessage has no timestamp fields
        assert not hasattr(msg, "timestamp_start")
        assert not hasattr(msg, "timestamp_end")


class TestFinalizedSegmentMessage:
    def test_is_final_locked_to_true(self):
        msg = FinalizedSegmentMessage(
            segment_id="seg-1",
            speaker_label="Speaker 1",
            spoken_language="en",
        )
        assert msg.is_final is True
        assert msg.type == "finalized_segment"

    def test_from_segment(self):
        seg = Segment(
            segment_id="seg-7",
            speaker_label="Speaker 3",
            text_vi="Thế giới",
            text_en="World",
            spoken_language="vi",
            is_final=True,
            timestamp_start=4.5,
            timestamp_end=6.0,
        )
        msg = FinalizedSegmentMessage.from_segment(seg)
        assert msg.segment_id == "seg-7"
        assert msg.speaker_label == "Speaker 3"
        assert msg.text_vi == "Thế giới"
        assert msg.text_en == "World"
        assert msg.spoken_language == "vi"
        assert msg.is_final is True
        assert msg.timestamp_start == 4.5
        assert msg.timestamp_end == 6.0
        assert msg.type == "finalized_segment"

    def test_timestamp_defaults(self):
        msg = FinalizedSegmentMessage(
            segment_id="seg-1",
            speaker_label="Speaker 1",
            spoken_language="en",
        )
        assert msg.timestamp_start == 0.0
        assert msg.timestamp_end == 0.0


class TestErrorMessage:
    def test_construction(self):
        msg = ErrorMessage(
            message="Transcription failed",
            code=ErrorCode.TRANSCRIBE_ERROR.value,
        )
        assert msg.type == "error"
        assert msg.message == "Transcription failed"
        assert msg.code == "TRANSCRIBE_ERROR"

    def test_serialization(self):
        msg = ErrorMessage(message="bad audio", code="INVALID_AUDIO_FORMAT")
        data = msg.model_dump()
        assert data["type"] == "error"
        assert data["code"] == "INVALID_AUDIO_FORMAT"


class TestSessionEndMessage:
    def test_construction(self):
        msg = SessionEndMessage(session_id="sess-999")
        assert msg.type == "session_end"
        assert msg.session_id == "sess-999"


class TestStopMessage:
    def test_construction(self):
        msg = StopMessage()
        assert msg.type == "stop"

    def test_from_dict(self):
        msg = StopMessage.model_validate({"type": "stop"})
        assert msg.type == "stop"


# ---------------------------------------------------------------------------
# ErrorCode enum
# ---------------------------------------------------------------------------


class TestErrorCode:
    def test_values_present(self):
        codes = {e.value for e in ErrorCode}
        assert "INVALID_AUDIO_FORMAT" in codes
        assert "TRANSCRIBE_ERROR" in codes
        assert "TRANSLATE_ERROR" in codes
        assert "SESSION_TIMEOUT" in codes
        assert "INTERNAL_ERROR" in codes


# ---------------------------------------------------------------------------
# Export payloads
# ---------------------------------------------------------------------------


class TestExportSegment:
    def test_construction(self):
        seg = ExportSegment(
            segment_id="seg-1",
            speaker_label="Speaker 1",
            text_vi="Xin chào",
            text_en="Hello",
            spoken_language="vi",
            timestamp_start=0.0,
            timestamp_end=1.5,
        )
        assert seg.segment_id == "seg-1"
        assert seg.spoken_language == "vi"

    def test_defaults(self):
        seg = ExportSegment(
            segment_id="s1",
            speaker_label="Speaker 1",
            spoken_language="en",
        )
        assert seg.text_vi == ""
        assert seg.text_en == ""
        assert seg.timestamp_start == 0.0
        assert seg.timestamp_end == 0.0


class TestExportRequest:
    def test_empty_segments_allowed(self):
        req = ExportRequest(segments=[])
        assert req.segments == []

    def test_with_segments(self):
        seg = ExportSegment(
            segment_id="s1",
            speaker_label="Speaker 1",
            spoken_language="en",
        )
        req = ExportRequest(segments=[seg])
        assert len(req.segments) == 1

    def test_default_empty(self):
        req = ExportRequest()
        assert req.segments == []


class TestExportResponse:
    def test_construction(self):
        expires = datetime.now(timezone.utc)
        resp = ExportResponse(
            download_url="https://s3.amazonaws.com/bucket/file.txt",
            expires_at=expires,
        )
        assert resp.download_url.startswith("https://")
        assert resp.expires_at == expires


# ---------------------------------------------------------------------------
# SegmentIdAllocator
# ---------------------------------------------------------------------------


class TestSegmentIdAllocator:
    def test_first_call_allocates_new_id(self):
        alloc = SegmentIdAllocator()
        sid = alloc.assign("result-1")
        assert sid.startswith("seg-")

    def test_same_key_returns_same_id(self):
        """Partial revisions must reuse the same Segment_ID (Req 3.5)."""
        alloc = SegmentIdAllocator()
        id1 = alloc.assign("result-1")
        id2 = alloc.assign("result-1")
        id3 = alloc.assign("result-1")
        assert id1 == id2 == id3

    def test_different_keys_get_different_ids(self):
        """Each distinct phrase gets a unique Segment_ID (Req 3.4)."""
        alloc = SegmentIdAllocator()
        id1 = alloc.assign("result-A")
        id2 = alloc.assign("result-B")
        id3 = alloc.assign("result-C")
        assert id1 != id2
        assert id2 != id3
        assert id1 != id3

    def test_finalize_marks_segment(self):
        alloc = SegmentIdAllocator()
        sid = alloc.finalize("result-1")
        assert alloc.is_finalized(sid)

    def test_assign_then_finalize_returns_same_id(self):
        alloc = SegmentIdAllocator()
        assigned = alloc.assign("result-1")
        finalized = alloc.finalize("result-1")
        assert assigned == finalized

    def test_is_finalized_false_for_partial(self):
        alloc = SegmentIdAllocator()
        sid = alloc.assign("result-partial")
        assert not alloc.is_finalized(sid)

    def test_finalized_ids_are_unique(self):
        """All finalized IDs must be distinct (Req 3.4)."""
        alloc = SegmentIdAllocator()
        keys = [f"result-{i}" for i in range(10)]
        finalized = [alloc.finalize(k) for k in keys]
        assert len(set(finalized)) == 10  # all unique

    def test_finalized_ids_property(self):
        alloc = SegmentIdAllocator()
        alloc.finalize("r1")
        alloc.finalize("r2")
        alloc.finalize("r3")
        ids = alloc.finalized_ids
        assert isinstance(ids, frozenset)
        assert len(ids) == 3

    def test_partial_then_finalize_not_double_counted(self):
        alloc = SegmentIdAllocator()
        # Simulate multiple partial revisions then finalization
        for _ in range(5):
            alloc.assign("result-1")
        alloc.finalize("result-1")
        # Should appear only once in finalized set
        assert len(alloc.finalized_ids) == 1

    def test_multiple_partials_independent_keys(self):
        """Two concurrent partial segments get distinct IDs."""
        alloc = SegmentIdAllocator()
        id_a = alloc.assign("result-a")
        id_b = alloc.assign("result-b")
        # Revise both
        assert alloc.assign("result-a") == id_a
        assert alloc.assign("result-b") == id_b
        # They remain distinct
        assert id_a != id_b

    def test_custom_prefix(self):
        alloc = SegmentIdAllocator(prefix="s")
        sid = alloc.assign("k1")
        assert sid.startswith("s-")

    def test_counter_increments(self):
        alloc = SegmentIdAllocator()
        id1 = alloc.assign("key-1")
        id2 = alloc.assign("key-2")
        # IDs should differ and the second one has a higher counter
        assert id1 != id2
        # Extract counter values to verify ordering
        n1 = int(id1.split("-")[1])
        n2 = int(id2.split("-")[1])
        assert n2 > n1

    def test_finalized_segments_all_unique_across_many(self):
        """Stress-test: 100 distinct keys → 100 unique finalized IDs."""
        alloc = SegmentIdAllocator()
        for i in range(100):
            alloc.finalize(f"key-{i}")
        assert len(alloc.finalized_ids) == 100
