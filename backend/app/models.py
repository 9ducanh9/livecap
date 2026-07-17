"""Data models and message contracts for the LiveCap backend.

This module defines the typed contracts shared across the backend:

* The core domain models ``Session`` and ``Segment`` (see design
  "Backend Data Models").
* The WebSocket message schemas exchanged with the Frontend
  (``session_start``, ``partial_segment``, ``finalized_segment``, ``error``,
  ``session_end``, and the inbound ``stop`` signal — see design
  "WebSocket Messages").
* The REST export request/response payloads for
  ``POST /api/sessions/{session_id}/export`` (see design "API Design").
* :class:`SegmentIdAllocator`, a helper that assigns Segment_IDs that are
  unique within a Session while letting partial revisions of the same segment
  reuse a single Segment_ID (correctness property CP-2).

All field names match the JSON shapes in the design document so the models can
be serialized to/from the wire without remapping.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import List, Literal, Optional, Union

from pydantic import BaseModel, Field

# The two Rendered_Languages of the MVP. ``spoken_language`` always carries one
# of these values, identifying which column holds the originally-spoken text.
SpokenLanguage = Literal["vi", "en"]


# ---------------------------------------------------------------------------
# Core domain models
# ---------------------------------------------------------------------------


class Segment(BaseModel):
    """A single transcription segment within a Session.

    For each segment one of ``text_vi`` / ``text_en`` holds the originally
    spoken text and the other holds the translation, depending on
    ``spoken_language``. A partial segment may have an empty translation column
    until the finalized segment is translated.
    """

    segment_id: str
    speaker_label: str  # "Speaker 1", "Speaker 2", etc.
    text_vi: str = ""
    text_en: str = ""
    spoken_language: SpokenLanguage
    is_final: bool = False
    timestamp_start: float = 0.0
    timestamp_end: float = 0.0


class Session(BaseModel):
    """A single continuous period of audio capture and transcription."""

    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    started_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    ended_at: Optional[datetime] = None
    segments: List[Segment] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# WebSocket messages: Backend -> Frontend
# ---------------------------------------------------------------------------


class SessionStartMessage(BaseModel):
    """Sent once when the Backend accepts the connection and opens a Session."""

    type: Literal["session_start"] = "session_start"
    session_id: str


class PartialSegmentMessage(BaseModel):
    """A revisable transcription result for an in-progress phrase.

    Revisions of the same phrase reuse the same ``segment_id`` (CP-2).
    """

    type: Literal["partial_segment"] = "partial_segment"
    segment_id: str
    speaker_label: str
    text_vi: str = ""
    text_en: str = ""
    spoken_language: SpokenLanguage
    is_final: Literal[False] = False

    @classmethod
    def from_segment(cls, segment: "Segment") -> "PartialSegmentMessage":
        """Build a partial-segment message from a :class:`Segment`."""

        return cls(
            segment_id=segment.segment_id,
            speaker_label=segment.speaker_label,
            text_vi=segment.text_vi,
            text_en=segment.text_en,
            spoken_language=segment.spoken_language,
        )


class FinalizedSegmentMessage(BaseModel):
    """A completed transcription segment, no longer subject to revision."""

    type: Literal["finalized_segment"] = "finalized_segment"
    segment_id: str
    speaker_label: str
    text_vi: str = ""
    text_en: str = ""
    spoken_language: SpokenLanguage
    is_final: Literal[True] = True
    timestamp_start: float = 0.0
    timestamp_end: float = 0.0

    @classmethod
    def from_segment(cls, segment: "Segment") -> "FinalizedSegmentMessage":
        """Build a finalized-segment message from a :class:`Segment`."""

        return cls(
            segment_id=segment.segment_id,
            speaker_label=segment.speaker_label,
            text_vi=segment.text_vi,
            text_en=segment.text_en,
            spoken_language=segment.spoken_language,
            timestamp_start=segment.timestamp_start,
            timestamp_end=segment.timestamp_end,
        )


class ErrorCode(str, Enum):
    """Stable error codes sent over the Streaming_Channel.

    These map to the Backend rows of the design's error-handling strategy.
    """

    INVALID_AUDIO_FORMAT = "INVALID_AUDIO_FORMAT"
    TRANSCRIBE_ERROR = "TRANSCRIBE_ERROR"
    TRANSLATE_ERROR = "TRANSLATE_ERROR"
    SESSION_TIMEOUT = "SESSION_TIMEOUT"
    INVALID_LANGUAGE_MODE = "INVALID_LANGUAGE_MODE"
    TOO_MANY_SESSIONS = "TOO_MANY_SESSIONS"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class ErrorMessage(BaseModel):
    """An error notification delivered to the Frontend over the WebSocket."""

    type: Literal["error"] = "error"
    message: str
    code: str


class SessionEndMessage(BaseModel):
    """Sent when a Session ends by user stop, timeout, or error."""

    type: Literal["session_end"] = "session_end"
    session_id: str


class PongMessage(BaseModel):
    """Heartbeat response delivered when the Frontend sends ``ping``."""

    type: Literal["pong"] = "pong"


class SessionSummary(BaseModel):
    """AI-generated wrap-up of a finished Session.

    Produced by the Summarization_Service (Amazon Bedrock) from the finalized
    transcript. Text fields are bilingual; list fields are written in the
    meeting's dominant language. All fields are optional so a partial or
    best-effort model response still yields a usable summary.
    """

    summary_vi: str = ""
    summary_en: str = ""
    key_points: List[str] = Field(default_factory=list)
    decisions: List[str] = Field(default_factory=list)
    action_items: List[str] = Field(default_factory=list)
    topics: List[str] = Field(default_factory=list)

    def is_empty(self) -> bool:
        """Return True when the model produced no usable content."""
        return not any(
            (
                self.summary_vi.strip(),
                self.summary_en.strip(),
                self.key_points,
                self.decisions,
                self.action_items,
                self.topics,
            )
        )


class SummaryMessage(BaseModel):
    """Delivers the AI-generated :class:`SessionSummary` before ``session_end``."""

    type: Literal["session_summary"] = "session_summary"
    session_id: str
    summary: SessionSummary


# A discriminated union of every message the Backend sends to the Frontend.
ServerMessage = Union[
    SessionStartMessage,
    PartialSegmentMessage,
    FinalizedSegmentMessage,
    ErrorMessage,
    SessionEndMessage,
    PongMessage,
    SummaryMessage,
]


# ---------------------------------------------------------------------------
# WebSocket messages: Frontend -> Backend
# ---------------------------------------------------------------------------


class StopMessage(BaseModel):
    """The JSON stop signal the Frontend sends to end audio capture.

    (Audio chunks themselves are sent as binary frames and have no JSON model.)
    """

    type: Literal["stop"] = "stop"


class PingMessage(BaseModel):
    """Heartbeat ping sent by the Frontend while recording."""

    type: Literal["ping"] = "ping"


# ---------------------------------------------------------------------------
# REST export payloads: POST /api/sessions/{session_id}/export
# ---------------------------------------------------------------------------


class ExportSegment(BaseModel):
    """A finalized segment as supplied by the Frontend in an export request."""

    segment_id: str
    speaker_label: str
    text_vi: str = ""
    text_en: str = ""
    spoken_language: SpokenLanguage
    timestamp_start: float = 0.0
    timestamp_end: float = 0.0


class ExportRequest(BaseModel):
    """Request body for the export endpoint.

    ``segments`` are ordered by finalization sequence. An empty list is valid
    and represents an empty Transcript (Requirement 7.3).
    """

    segments: List[ExportSegment] = Field(default_factory=list)
    # Optional plain-text meeting summary prepended to the exported transcript.
    # Backward compatible: older clients that omit it export segments only.
    summary_text: Optional[str] = None


class ExportResponse(BaseModel):
    """Successful export response carrying the time-limited Download_Link."""

    download_url: str
    expires_at: datetime


# ---------------------------------------------------------------------------
# Segment_ID assignment
# ---------------------------------------------------------------------------


class SegmentIdAllocator:
    """Assigns Segment_IDs that are unique within a single Session.

    Amazon Transcribe identifies each result with a stable result identifier
    that persists across partial revisions of the same phrase. This allocator
    maps each distinct result identifier (``result_key``) to a single
    Segment_ID so that:

    * partial revisions of the same phrase reuse one Segment_ID, and
    * every distinct (eventually finalized) segment receives a Segment_ID that
      is unique within the Session.

    Together these uphold correctness property **CP-2: Segment ID Uniqueness**
    (Requirements 3.4, 3.5).

    The allocator is intended to be used per-Session; create a fresh instance
    for each new :class:`Session`.
    """

    def __init__(self, prefix: str = "seg") -> None:
        self._prefix = prefix
        self._counter = 0
        # Maps a transcribe result key -> the stable Segment_ID assigned to it.
        self._result_to_id: dict[str, str] = {}
        # Segment_IDs that have been promoted to a Finalized_Segment.
        self._finalized: set[str] = set()

    def assign(self, result_key: str) -> str:
        """Return the Segment_ID for ``result_key``.

        The first time a ``result_key`` is seen a new unique Segment_ID is
        allocated; subsequent calls with the same key (partial revisions)
        return the same Segment_ID.
        """

        existing = self._result_to_id.get(result_key)
        if existing is not None:
            return existing

        self._counter += 1
        segment_id = f"{self._prefix}-{self._counter}"
        self._result_to_id[result_key] = segment_id
        return segment_id

    def finalize(self, result_key: str) -> str:
        """Assign (or reuse) the Segment_ID for ``result_key`` and mark it final.

        Returns the Segment_ID, which is guaranteed unique among all finalized
        segments allocated by this instance.
        """

        segment_id = self.assign(result_key)
        self._finalized.add(segment_id)
        return segment_id

    def is_finalized(self, segment_id: str) -> bool:
        """Return whether ``segment_id`` has been finalized."""

        return segment_id in self._finalized

    @property
    def finalized_ids(self) -> frozenset[str]:
        """An immutable view of every finalized Segment_ID."""

        return frozenset(self._finalized)
