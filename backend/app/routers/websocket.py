"""WebSocket router: ``GET /ws/transcribe`` streaming endpoint.

Implements the WebSocket handler with full session lifecycle management
(task 8.1, Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.8, 3.1, 3.2, 3.3, 3.7,
5.2, 10.1, 10.2).

Session lifecycle
-----------------
1. Client connects → Backend assigns UUID v4 Session_ID, sends
   ``session_start``.
2. Client sends binary frames → validated against Expected_Audio_Format →
   pushed into an ``asyncio.Queue`` consumed by :class:`TranscriptionService`.
3. Transcription results flow back:
   * :class:`~app.models.PartialSegmentMessage` → forwarded immediately.
   * :class:`~app.models.FinalizedSegmentMessage` → translated via
     :func:`~app.services.translation.translate_segment`, then forwarded.
4. Client sends ``{"type": "stop"}`` JSON frame → end-of-stream sentinel
   pushed; session tears down gracefully.
5. On stop / timeout / error → ``session_end`` sent, connection closed,
   resources released.

Timeout
-------
Sessions are bounded by ``settings.session_timeout`` (default 30 min).  The
timeout fires even while the client is still actively streaming.

Error handling
--------------
* Malformed audio → ``error`` message with ``INVALID_AUDIO_FORMAT`` code, then
  ``session_end`` and connection close.
* Transcription error → ``error`` message with ``TRANSCRIBE_ERROR`` code, then
  ``session_end`` and connection close.
* Translation error → logged; the untranslated
  :class:`~app.models.FinalizedSegmentMessage` is forwarded as-is.
* Unexpected exception → ``error`` with ``INTERNAL_ERROR`` code, then
  ``session_end`` and connection close.
"""

from __future__ import annotations

import asyncio
import time
import json
import logging
import uuid
from dataclasses import dataclass
from typing import AsyncIterator, NamedTuple

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.config import get_settings
from app.models import (
    ErrorCode,
    ErrorMessage,
    FinalizedSegmentMessage,
    PartialSegmentMessage,
    PongMessage,
    SessionEndMessage,
    SessionStartMessage,
    StopMessage,
)
from app.services.logging_service import (
    get_logger,
    log_integration_error,
    log_session_end,
    log_session_start,
    log_websocket_connect,
    log_websocket_disconnect,
)
from app.services.idle_scaler import get_idle_scale_down_scheduler
from app.services.session_registry import (
    active_session_registry,
    get_session_registry,
)
from app.services.transcription import TranscriptionService
from app.services.translation import translate_segment
from app.utils.audio import validate_audio_chunk

router = APIRouter()

_logger: logging.Logger = get_logger()


class LanguageMode(NamedTuple):
    source_language_code: str
    source_translate_code: str
    target_language_code: str


_DEFAULT_LANGUAGE_MODE = LanguageMode(
    source_language_code="vi-VN",
    source_translate_code="vi",
    target_language_code="en",
)

_ALLOWED_LANGUAGE_MODES: dict[tuple[str, str], LanguageMode] = {
    ("vi-VN", "en"): _DEFAULT_LANGUAGE_MODE,
    ("en-US", "vi"): LanguageMode(
        source_language_code="en-US",
        source_translate_code="en",
        target_language_code="vi",
    ),
}

_DUAL_STREAM_WINDOW_SECONDS = 1.5
_DUPLICATE_FINAL_SECONDS = 2.0
_MIN_FINAL_TEXT_LENGTH = 3
_VIETNAMESE_CHARS = set(
    "ăâđêôơưáàảãạắằẳẵặấầẩẫậéèẻẽẹếềểễệ"
    "íìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ"
    "ĂÂĐÊÔƠƯÁÀẢÃẠẮẰẲẴẶẤẦẨẪẬÉÈẺẼẸẾỀỂỄỆ"
    "ÍÌỈĨỊÓÒỎÕỌỐỒỔỖỘỚỜỞỠỢÚÙỦŨỤỨỪỬỮỰÝỲỶỸỴ"
)
_COMMON_ENGLISH_WORDS = {
    "a",
    "about",
    "am",
    "and",
    "are",
    "can",
    "do",
    "for",
    "hello",
    "hi",
    "how",
    "i",
    "is",
    "it",
    "me",
    "my",
    "of",
    "please",
    "sense",
    "speak",
    "test",
    "that",
    "the",
    "this",
    "to",
    "voice",
    "what",
    "you",
    "your",
}
_COMMON_VIETNAMESE_WORDS = {
    "anh",
    "ban",
    "bạn",
    "chao",
    "chào",
    "cho",
    "co",
    "có",
    "day",
    "đây",
    "em",
    "khong",
    "không",
    "la",
    "là",
    "minh",
    "mình",
    "mot",
    "một",
    "noi",
    "nói",
    "toi",
    "tôi",
    "xin",
}


@dataclass(frozen=True)
class TranscriptCandidate:
    source_language: str
    transcript_text: str
    message: FinalizedSegmentMessage
    mode: LanguageMode
    created_at: float


@dataclass(frozen=True)
class PartialCandidate:
    """A revisable partial result tagged with the stream that produced it."""

    source_language: str
    message: PartialSegmentMessage


class DominantLanguage:
    """Mutable holder for the stream whose partials are currently shown.

    In dual-stream mode both the vi and en Transcribe streams emit partial
    results for the same audio. To avoid the live caption flickering between a
    correct guess and a wrong-language guess, only partials from the dominant
    stream are forwarded. The dominant language starts from the user's selected
    source language and flips whenever the arbiter finalizes a segment in the
    other language.
    """

    def __init__(self, value: str) -> None:
        self.value = value


# Sentinel pushed onto the unified output queue when the finalized-candidate
# arbiter has finished, signalling the session loop to stop reading.
_ARBITRATION_DONE = object()
_DUAL_CANDIDATE_QUEUE_SIZE = 32
_DUAL_PARTIAL_QUEUE_SIZE = 64
_DUAL_OUTPUT_QUEUE_SIZE = 64


# ---------------------------------------------------------------------------
# Helper: send a Pydantic model as JSON
# ---------------------------------------------------------------------------


async def _send(websocket: WebSocket, message) -> None:
    """Serialize *message* to JSON and send it to *websocket*.

    Silently ignores send errors that occur after a disconnect has already
    been initiated, so teardown code can call this unconditionally.
    """
    try:
        await websocket.send_text(message.model_dump_json())
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------------------
# Helper: send an error message
# ---------------------------------------------------------------------------


async def _send_error(
    websocket: WebSocket,
    message: str,
    code: ErrorCode,
) -> None:
    """Send an :class:`~app.models.ErrorMessage` to the client."""
    await _send(websocket, ErrorMessage(message=message, code=code.value))


def _mode_for_source_language(source_language_code: str) -> LanguageMode | None:
    """Return the supported mode that starts from a Transcribe language code."""
    if source_language_code == "en-US":
        return _ALLOWED_LANGUAGE_MODES[("en-US", "vi")]
    if source_language_code == "vi-VN":
        return _ALLOWED_LANGUAGE_MODES[("vi-VN", "en")]
    return None


def _resolve_language_mode(
    websocket: WebSocket,
    fallback_source_language_code: str,
) -> LanguageMode | None:
    """Return the validated manual translation mode from query params."""
    if "source" not in websocket.query_params and "target" not in websocket.query_params:
        return _mode_for_source_language(fallback_source_language_code)
    source = websocket.query_params.get("source") or _DEFAULT_LANGUAGE_MODE.source_language_code
    target = websocket.query_params.get("target") or _DEFAULT_LANGUAGE_MODE.target_language_code
    return _ALLOWED_LANGUAGE_MODES.get((source, target))


def _resolve_session_id(websocket: WebSocket) -> str:
    """Reuse the client's prior session id on reconnect, else mint a new one.

    Accepts a ``session_id`` query param only if it is a valid UUID, so a client
    that reconnects after an unexpected drop can keep one logical session id
    across the gap (stable logs, export, and active-session accounting). The
    active-session registry's ``try_register`` is idempotent for a repeated id,
    so reusing it does not double-count. A missing or invalid value yields a
    fresh UUID v4 (B5).
    """
    provided = websocket.query_params.get("session_id")
    if provided:
        try:
            return str(uuid.UUID(provided))
        except (ValueError, AttributeError, TypeError):
            pass
    return str(uuid.uuid4())


def _resolve_client_ip(websocket: WebSocket) -> str:
    """Resolve the caller IP, preferring ALB/CloudFront forwarded headers."""

    forwarded_for = websocket.headers.get("x-forwarded-for")
    if forwarded_for:
        first_ip = forwarded_for.split(",", maxsplit=1)[0].strip()
        if first_ip:
            return first_ip

    if websocket.client is not None and websocket.client.host:
        return websocket.client.host

    return "unknown"


def _final_text(message: FinalizedSegmentMessage, source_language: str) -> str:
    """Return the source transcript text from a finalized message."""
    return message.text_vi if source_language == "vi" else message.text_en


def _log_candidate_dropped(
    session_id: str,
    candidate: TranscriptCandidate,
    reason: str,
) -> None:
    _logger.info(
        "transcript_candidate_dropped",
        extra={
            "event": "transcript_candidate_dropped",
            "session_id": session_id,
            "source_language": candidate.source_language,
            "reason": reason,
            "transcript_text": candidate.transcript_text,
        },
    )


def _tokenize_for_language_score(text: str) -> list[str]:
    return [
        token.strip(".,!?;:\"'()[]{}").casefold()
        for token in text.split()
        if token.strip(".,!?;:\"'()[]{}")
    ]


def _normalized_transcript_text(text: str) -> str:
    return " ".join(_tokenize_for_language_score(text))


def _language_score(candidate: TranscriptCandidate) -> int:
    """Estimate whether a candidate text matches its claimed source language."""
    text = candidate.transcript_text.strip()
    tokens = _tokenize_for_language_score(text)
    english_hits = sum(1 for token in tokens if token in _COMMON_ENGLISH_WORDS)
    vietnamese_hits = sum(1 for token in tokens if token in _COMMON_VIETNAMESE_WORDS)
    vietnamese_char_hits = sum(1 for char in text if char in _VIETNAMESE_CHARS)

    if candidate.source_language == "en":
        return english_hits * 3 - vietnamese_hits * 2 - vietnamese_char_hits * 3
    return vietnamese_hits * 2 + vietnamese_char_hits * 4 - english_hits * 3


async def _translate_finalized_candidate(
    *,
    msg: FinalizedSegmentMessage,
    session_id: str,
    mode: LanguageMode,
    source_language: str,
) -> FinalizedSegmentMessage:
    """Translate one finalized candidate and preserve the old frontend contract."""
    from app.models import Segment  # local import to avoid cycles

    segment = Segment(
        segment_id=msg.segment_id,
        speaker_label=msg.speaker_label,
        text_vi=msg.text_vi,
        text_en=msg.text_en,
        spoken_language=msg.spoken_language,
        is_final=True,
        timestamp_start=msg.timestamp_start,
        timestamp_end=msg.timestamp_end,
    )

    try:
        translated = await translate_segment(
            segment,
            session_id=session_id,
            source_language_code=mode.source_translate_code,
            target_language_code=mode.target_language_code,
        )
    except Exception as exc:
        log_integration_error(
            session_id=session_id,
            service_name="Amazon Translate",
            error=exc,
        )
        translated = segment

    return FinalizedSegmentMessage(
        segment_id=f"{source_language}-{translated.segment_id}",
        speaker_label=translated.speaker_label,
        text_vi=translated.text_vi,
        text_en=translated.text_en,
        spoken_language=translated.spoken_language,
        timestamp_start=translated.timestamp_start,
        timestamp_end=translated.timestamp_end,
    )


async def _run_dual_transcription_worker(
    *,
    session_id: str,
    settings,
    mode: LanguageMode,
    source_language: str,
    audio_queue: "asyncio.Queue[bytes | None]",
    candidate_queue: "asyncio.Queue[TranscriptCandidate | Exception | None]",
    partial_queue: "asyncio.Queue[PartialCandidate] | None" = None,
) -> None:
    """Run one fixed-language Transcribe stream and publish finalized candidates.

    When *partial_queue* is provided, revisable partial results are forwarded to
    it (tagged with *source_language*) so the session loop can show a live
    caption while a phrase is still in progress.
    """
    service = TranscriptionService(
        session_id=session_id,
        settings=settings,
        language_code=mode.source_language_code,
    )
    try:
        async for msg in service.transcribe(audio_queue):
            if isinstance(msg, PartialSegmentMessage):
                if partial_queue is not None:
                    await partial_queue.put(
                        PartialCandidate(
                            source_language=source_language,
                            message=msg,
                        )
                    )
                continue
            if isinstance(msg, FinalizedSegmentMessage):
                transcript_text = _final_text(msg, source_language).strip()
                _logger.info(
                    f"{source_language}_transcript_candidate",
                    extra={
                        "event": f"{source_language}_transcript_candidate",
                        "session_id": session_id,
                        "source_language": source_language,
                        "transcript_text": transcript_text,
                        "is_final": True,
                        "timestamp_start": msg.timestamp_start,
                        "timestamp_end": msg.timestamp_end,
                    },
                )
                await candidate_queue.put(
                    TranscriptCandidate(
                        source_language=source_language,
                        transcript_text=transcript_text,
                        message=msg,
                        mode=mode,
                        created_at=time.monotonic(),
                    )
                )
    except Exception as exc:
        await candidate_queue.put(exc)
    finally:
        await candidate_queue.put(None)


def _candidate_passes_basic_filters(
    *,
    session_id: str,
    candidate: TranscriptCandidate,
    recent_finalized: dict[str, float],
    now: float,
) -> bool:
    text = candidate.transcript_text.strip()
    normalized = _normalized_transcript_text(text).casefold()
    if not text:
        _log_candidate_dropped(session_id, candidate, "empty_text")
        return False
    if len(normalized) < _MIN_FINAL_TEXT_LENGTH:
        _log_candidate_dropped(session_id, candidate, "too_short")
        return False
    if len(normalized.split()) < 2:
        _log_candidate_dropped(session_id, candidate, "too_few_words")
        return False
    if _language_score(candidate) < -2:
        _log_candidate_dropped(session_id, candidate, "wrong_language_score")
        return False
    last_seen = recent_finalized.get(normalized)
    if last_seen is not None and now - last_seen < _DUPLICATE_FINAL_SECONDS:
        _log_candidate_dropped(session_id, candidate, "duplicate_within_2s")
        return False
    return True


async def _next_dual_candidate(
    candidate_queue: "asyncio.Queue[TranscriptCandidate | Exception | None]",
    active_workers: int,
    timeout: float | None = None,
) -> tuple[TranscriptCandidate | Exception | None, int]:
    """Read the next candidate, tracking worker completion sentinels."""
    while active_workers > 0:
        try:
            item = (
                await candidate_queue.get()
                if timeout is None
                else await asyncio.wait_for(candidate_queue.get(), timeout=timeout)
            )
        except TimeoutError:
            return None, active_workers
        if item is None:
            active_workers -= 1
            continue
        return item, active_workers
    return None, active_workers


async def _arbitrate_dual_candidates(
    *,
    session_id: str,
    candidate_queue: "asyncio.Queue[TranscriptCandidate | Exception | None]",
    dominant_language: "DominantLanguage | None" = None,
) -> AsyncIterator[FinalizedSegmentMessage | Exception]:
    """Choose one finalized candidate when both streams produce nearby text."""
    active_workers = 2
    recent_finalized: dict[str, float] = {}

    while active_workers > 0:
        item, active_workers = await _next_dual_candidate(
            candidate_queue, active_workers
        )
        if item is None:
            continue
        if isinstance(item, Exception):
            yield item
            continue

        now = time.monotonic()
        if not _candidate_passes_basic_filters(
            session_id=session_id,
            candidate=item,
            recent_finalized=recent_finalized,
            now=now,
        ):
            continue

        candidates = [item]
        deadline = now + _DUAL_STREAM_WINDOW_SECONDS
        while active_workers > 0:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            contender, active_workers = await _next_dual_candidate(
                candidate_queue, active_workers, timeout=remaining
            )
            if contender is None:
                continue
            if isinstance(contender, Exception):
                yield contender
                continue
            contender_now = time.monotonic()
            if _candidate_passes_basic_filters(
                session_id=session_id,
                candidate=contender,
                recent_finalized=recent_finalized,
                now=contender_now,
            ):
                candidates.append(contender)

        selected = max(
            candidates,
            key=lambda c: (_language_score(c), len(c.transcript_text)),
        )
        for candidate in candidates:
            if candidate is not selected:
                _log_candidate_dropped(
                    session_id,
                    candidate,
                    "lower_language_score_window_candidate",
                )

        normalized_selected = _normalized_transcript_text(
            selected.transcript_text
        ).casefold()
        recent_finalized[normalized_selected] = time.monotonic()
        # Flip the live-caption stream to follow the language just finalized,
        # so subsequent partials are shown from the matching Transcribe stream.
        if dominant_language is not None:
            dominant_language.value = selected.source_language
        _logger.info(
            "transcript_candidate_emitted",
            extra={
                "event": "transcript_candidate_emitted",
                "session_id": session_id,
                "source_language": selected.source_language,
                "transcript_text": selected.transcript_text,
                "language_score": _language_score(selected),
            },
        )
        yield await _translate_finalized_candidate(
            msg=selected.message,
            session_id=session_id,
            mode=selected.mode,
            source_language=selected.source_language,
        )


async def _forward_dual_partials(
    *,
    session_id: str,
    partial_queue: "asyncio.Queue[PartialCandidate]",
    output_queue: "asyncio.Queue",
    dominant_language: "DominantLanguage",
) -> None:
    """Forward live partials from the dominant stream to the output queue.

    Only partials whose ``source_language`` matches the current dominant
    language are forwarded, so the single frontend live-caption slot does not
    flicker between the two streams' competing guesses. The segment_id is
    prefixed with the source language to mirror the finalized-segment contract
    so the frontend can replace the partial when its finalized form arrives.
    """
    while True:
        candidate = await partial_queue.get()
        if candidate.source_language != dominant_language.value:
            continue
        msg = candidate.message
        await output_queue.put(
            PartialSegmentMessage(
                segment_id=f"{candidate.source_language}-{msg.segment_id}",
                speaker_label=msg.speaker_label,
                text_vi=msg.text_vi,
                text_en=msg.text_en,
                spoken_language=msg.spoken_language,
            )
        )


async def _drive_dual_arbiter(
    *,
    session_id: str,
    candidate_queue: "asyncio.Queue[TranscriptCandidate | Exception | None]",
    output_queue: "asyncio.Queue",
    dominant_language: "DominantLanguage",
) -> None:
    """Run the finalized-candidate arbiter, pushing results to the output queue.

    Signals completion by pushing the :data:`_ARBITRATION_DONE` sentinel so the
    session loop knows no more finalized segments will arrive.
    """
    try:
        async for msg in _arbitrate_dual_candidates(
            session_id=session_id,
            candidate_queue=candidate_queue,
            dominant_language=dominant_language,
        ):
            await output_queue.put(msg)
    finally:
        await output_queue.put(_ARBITRATION_DONE)


# ---------------------------------------------------------------------------
# Core WebSocket endpoint
# ---------------------------------------------------------------------------


@router.websocket("/ws/transcribe")
async def websocket_transcribe(websocket: WebSocket) -> None:
    """Accept a WebSocket upgrade and manage the full transcription session.

    This is the primary entry point for the Streaming_Channel.  It:

    1. Accepts the connection and assigns a UUID v4 Session_ID.
    2. Sends ``session_start``.
    3. Spawns a background task that reads incoming frames (binary audio or
       JSON control) and routes them appropriately.
    4. Drives the transcription pipeline and forwards results to the client.
    5. Sends ``session_end`` and closes cleanly on stop, timeout, or error.
    """
    settings = get_settings()
    session_id = _resolve_session_id(websocket)
    language_mode = _resolve_language_mode(
        websocket,
        fallback_source_language_code=settings.transcribe_language_code,
    )

    await websocket.accept()

    if language_mode is None:
        await _send_error(
            websocket,
            message=(
                "Invalid language mode. Allowed modes are "
                "source=vi-VN&target=en or source=en-US&target=vi."
            ),
            code=ErrorCode.INVALID_LANGUAGE_MODE,
        )
        await websocket.close(code=1008)
        return

    client_ip = _resolve_client_ip(websocket)
    session_registry = get_session_registry(settings)
    session_registered = False
    limit_result = session_registry.try_register(
        session_id=session_id,
        client_ip=client_ip,
        max_total=settings.max_concurrent_sessions,
        max_per_ip=settings.max_sessions_per_ip,
    )
    if not limit_result.allowed:
        _logger.warning(
            "Session rejected by active-session limit",
            extra={
                "event": "session_rejected",
                "session_id": session_id,
                "client_ip": client_ip,
                "reason": limit_result.reason,
                "max_concurrent_sessions": settings.max_concurrent_sessions,
                "max_sessions_per_ip": settings.max_sessions_per_ip,
            },
        )
        await _send_error(
            websocket,
            message="Too many active LiveCap sessions. Please try again later.",
            code=ErrorCode.TOO_MANY_SESSIONS,
        )
        await websocket.close(code=1008)
        return
    session_registered = True
    get_idle_scale_down_scheduler(session_registry).cancel_pending()

    log_websocket_connect(session_id)

    # Record session-start event (Requirement 10.1).
    log_session_start(session_id)

    # Send session_start to the client (Requirement 2.2).
    await _send(websocket, SessionStartMessage(session_id=session_id))

    _logger.info(
        "Session opened",
        extra={"event": "session_open", "session_id": session_id},
    )

    # Queues that bridge the incoming-frame reader with TranscriptionService.
    # Audio bytes are pushed here; ``None`` signals end-of-stream.
    audio_queue: asyncio.Queue[bytes | None] = asyncio.Queue()
    vi_audio_queue: asyncio.Queue[bytes | None] = asyncio.Queue()
    en_audio_queue: asyncio.Queue[bytes | None] = asyncio.Queue()

    async def _signal_end_of_stream() -> None:
        """Push end-of-stream sentinels to all possible Transcribe queues."""

        await audio_queue.put(None)
        await vi_audio_queue.put(None)
        await en_audio_queue.put(None)

    # Flag shared between the frame-reader and the session main loop.
    # Set to True when a JSON stop signal is received.
    stop_requested: asyncio.Event = asyncio.Event()

    # Flag set when the session should be torn down due to an error.
    error_event: asyncio.Event = asyncio.Event()
    error_details: dict = {}  # mutable container for error info

    async def _read_frames() -> None:
        """Consume incoming WebSocket frames in a background task.

        * Binary frames are validated and pushed to *audio_queue*.
        * JSON frames with ``{"type": "stop"}`` set *stop_requested*.
        * Malformed audio triggers an error and stops the session.
        """
        try:
            while True:
                try:
                    raw = await websocket.receive()
                except WebSocketDisconnect:
                    break

                # Client disconnect.
                if raw.get("type") == "websocket.disconnect":
                    break

                if "bytes" in raw and raw["bytes"] is not None:
                    # Binary frame — audio chunk.
                    data: bytes = raw["bytes"]
                    if settings.audio_pipeline_debug:
                        _logger.info(
                            "audio_pipeline_websocket_received",
                            extra={
                                "event": "audio_pipeline_websocket_received",
                                "session_id": session_id,
                                "byte_length": len(data),
                            },
                        )
                    valid, reason = validate_audio_chunk(data)
                    if not valid:
                        # Reject malformed audio (Requirement 2.8).
                        _logger.warning(
                            "Invalid audio chunk received",
                            extra={
                                "session_id": session_id,
                                "reason": reason,
                            },
                        )
                        error_details["message"] = reason or "Invalid audio format"
                        error_details["code"] = ErrorCode.INVALID_AUDIO_FORMAT
                        error_event.set()
                        break

                    if settings.bilingual_dual_stream:
                        await vi_audio_queue.put(data)
                        await en_audio_queue.put(data)
                        _logger.info(
                            "dual_stream_audio_fanned_out",
                            extra={
                                "event": "dual_stream_audio_fanned_out",
                                "session_id": session_id,
                                "byte_length": len(data),
                                "vi_queue_size": vi_audio_queue.qsize(),
                                "en_queue_size": en_audio_queue.qsize(),
                            },
                        )
                    else:
                        await audio_queue.put(data)
                    if settings.audio_pipeline_debug:
                        _logger.info(
                            "audio_pipeline_audio_queued",
                            extra={
                                "event": "audio_pipeline_audio_queued",
                                "session_id": session_id,
                                "byte_length": len(data),
                                "queue_size": (
                                    vi_audio_queue.qsize()
                                    if settings.bilingual_dual_stream
                                    else audio_queue.qsize()
                                ),
                            },
                        )

                elif "text" in raw and raw["text"] is not None:
                    # Text frame — expect JSON control message.
                    try:
                        payload = json.loads(raw["text"])
                    except json.JSONDecodeError:
                        _logger.warning(
                            "Received non-JSON text frame",
                            extra={"session_id": session_id},
                        )
                        continue  # Ignore malformed JSON control frames

                    if isinstance(payload, dict) and payload.get("type") == "stop":
                        _logger.info(
                            "Stop signal received",
                            extra={"session_id": session_id},
                        )
                        stop_requested.set()
                        break
                    if isinstance(payload, dict) and payload.get("type") == "ping":
                        await _send(websocket, PongMessage())
                        continue

        finally:
            # Signal end-of-stream to TranscriptionService regardless of how
            # the loop exited (stop, disconnect, or error).
            await _signal_end_of_stream()

    # Start the frame-reader background task.
    reader_task = asyncio.ensure_future(_read_frames())

    session_end_sent = False
    async def _teardown(send_session_end: bool = True) -> None:
        """Send ``session_end`` once, cancel the reader, and log cleanup."""
        nonlocal session_end_sent
        if send_session_end and not session_end_sent:
            session_end_sent = True
            await _send(websocket, SessionEndMessage(session_id=session_id))
            # Record session-end event (Requirement 10.2).
            log_session_end(session_id)
            _logger.info(
                "Session closed",
                extra={"event": "session_close", "session_id": session_id},
            )

        if not reader_task.done():
            reader_task.cancel()
            try:
                await reader_task
            except (asyncio.CancelledError, Exception):
                pass

        log_websocket_disconnect(session_id)

    try:
        # Wrap the entire session in a timeout (Requirement 2.5).
        async with asyncio.timeout(settings.session_timeout):
            if settings.bilingual_dual_stream:
                _logger.info(
                    "dual_stream_started",
                    extra={
                        "event": "dual_stream_started",
                        "session_id": session_id,
                    },
                )
                candidate_queue: asyncio.Queue[
                    TranscriptCandidate | Exception | None
                ] = asyncio.Queue(maxsize=_DUAL_CANDIDATE_QUEUE_SIZE)
                # Unified output queue: both the finalized-candidate arbiter and
                # the live-partial forwarder push here, so a single consumer owns
                # all websocket sends (no concurrent-send race).
                output_queue: asyncio.Queue = asyncio.Queue(
                    maxsize=_DUAL_OUTPUT_QUEUE_SIZE
                )
                partial_queue: asyncio.Queue[PartialCandidate] = asyncio.Queue(
                    maxsize=_DUAL_PARTIAL_QUEUE_SIZE
                )
                # The live caption follows the user's selected source language
                # until the arbiter finalizes a segment in the other language.
                dominant_language = DominantLanguage(
                    language_mode.source_translate_code
                )
                vi_task = asyncio.create_task(
                    _run_dual_transcription_worker(
                        session_id=session_id,
                        settings=settings,
                        mode=_ALLOWED_LANGUAGE_MODES[("vi-VN", "en")],
                        source_language="vi",
                        audio_queue=vi_audio_queue,
                        candidate_queue=candidate_queue,
                        partial_queue=partial_queue,
                    )
                )
                en_task = asyncio.create_task(
                    _run_dual_transcription_worker(
                        session_id=session_id,
                        settings=settings,
                        mode=_ALLOWED_LANGUAGE_MODES[("en-US", "vi")],
                        source_language="en",
                        audio_queue=en_audio_queue,
                        candidate_queue=candidate_queue,
                        partial_queue=partial_queue,
                    )
                )
                arbiter_task = asyncio.create_task(
                    _drive_dual_arbiter(
                        session_id=session_id,
                        candidate_queue=candidate_queue,
                        output_queue=output_queue,
                        dominant_language=dominant_language,
                    )
                )
                partial_task = asyncio.create_task(
                    _forward_dual_partials(
                        session_id=session_id,
                        partial_queue=partial_queue,
                        output_queue=output_queue,
                        dominant_language=dominant_language,
                    )
                )
                try:
                    while True:
                        msg = await output_queue.get()
                        if msg is _ARBITRATION_DONE:
                            # Arbiter finished: no more finalized segments.
                            break
                        if error_event.is_set():
                            break
                        if isinstance(msg, Exception):
                            log_integration_error(
                                session_id=session_id,
                                service_name="Amazon Transcribe Streaming",
                                error=msg,
                            )
                            await _send_error(
                                websocket,
                                message=f"Transcription error: {msg}",
                                code=ErrorCode.TRANSCRIBE_ERROR,
                            )
                            break
                        await _send(websocket, msg)
                finally:
                    for task in (vi_task, en_task, arbiter_task, partial_task):
                        if not task.done():
                            task.cancel()
                    await asyncio.gather(
                        vi_task,
                        en_task,
                        arbiter_task,
                        partial_task,
                        return_exceptions=True,
                    )

            else:
                transcription_service = TranscriptionService(
                    session_id=session_id,
                    settings=settings,
                    language_code=language_mode.source_language_code,
                )
                async for msg in transcription_service.transcribe(audio_queue):
                    # Check if an audio-format error was flagged by the reader.
                    if error_event.is_set():
                        break

                    if isinstance(msg, PartialSegmentMessage):
                        # Forward partial segment directly (Requirement 3.2).
                        await _send(websocket, msg)

                    elif isinstance(msg, FinalizedSegmentMessage):
                        # Translate the finalized segment, then forward (Req 5.2).
                        # Build a temporary Segment to pass to translate_segment.
                        from app.models import Segment  # local import to avoid cycles

                        segment = Segment(
                            segment_id=msg.segment_id,
                            speaker_label=msg.speaker_label,
                            text_vi=msg.text_vi,
                            text_en=msg.text_en,
                            spoken_language=msg.spoken_language,
                            is_final=True,
                            timestamp_start=msg.timestamp_start,
                            timestamp_end=msg.timestamp_end,
                        )

                        try:
                            translated = await translate_segment(
                                segment,
                                session_id=session_id,
                                source_language_code=language_mode.source_translate_code,
                                target_language_code=language_mode.target_language_code,
                            )
                            # Rebuild the FinalizedSegmentMessage with translated
                            # text so both columns are populated.
                            translated_msg = FinalizedSegmentMessage(
                                segment_id=translated.segment_id,
                                speaker_label=translated.speaker_label,
                                text_vi=translated.text_vi,
                                text_en=translated.text_en,
                                spoken_language=translated.spoken_language,
                                timestamp_start=translated.timestamp_start,
                                timestamp_end=translated.timestamp_end,
                            )
                            await _send(websocket, translated_msg)
                        except Exception as exc:
                            # Translation error: log and forward untranslated
                            # segment (Requirement 5.3).
                            log_integration_error(
                                session_id=session_id,
                                service_name="Amazon Translate",
                                error=exc,
                            )
                            await _send(websocket, msg)

                    elif isinstance(msg, Exception):
                        # Transcription error surfaced as an exception value.
                        log_integration_error(
                            session_id=session_id,
                            service_name="Amazon Transcribe Streaming",
                            error=msg,
                        )
                        await _send_error(
                            websocket,
                            message=f"Transcription error: {msg}",
                            code=ErrorCode.TRANSCRIBE_ERROR,
                        )
                        break

            # If an audio-format error was flagged, surface it now.
            if error_event.is_set():
                await _send_error(
                    websocket,
                    message=error_details.get("message", "Invalid audio format"),
                    code=error_details.get("code", ErrorCode.INVALID_AUDIO_FORMAT),
                )

    except TimeoutError:
        # Session timeout (Requirement 2.5).
        _logger.info(
            "Session timed out",
            extra={
                "event": "session_timeout",
                "session_id": session_id,
                "timeout_seconds": settings.session_timeout,
            },
        )
        await _send_error(
            websocket,
            message=(
                f"Session exceeded the maximum duration of "
                f"{settings.session_timeout} seconds."
            ),
            code=ErrorCode.SESSION_TIMEOUT,
        )
        await _signal_end_of_stream()

    except WebSocketDisconnect:
        _logger.info(
            "WebSocket disconnected",
            extra={"event": "websocket_disconnect_mid_session", "session_id": session_id},
        )

    except Exception as exc:
        # Unexpected error (Requirement 3.7).
        _logger.error(
            "Unexpected error in WebSocket handler",
            extra={"session_id": session_id, "error": str(exc)},
            exc_info=True,
        )
        await _send_error(
            websocket,
            message="An unexpected server error occurred.",
            code=ErrorCode.INTERNAL_ERROR,
        )
        await _signal_end_of_stream()

    finally:
        # Always send session_end and clean up (Requirements 2.5, 10.2).
        try:
            await _teardown(send_session_end=True)
        finally:
            if session_registered:
                session_registry.unregister(session_id)
                get_idle_scale_down_scheduler(
                    session_registry
                ).schedule_if_idle(settings=settings)
            try:
                await websocket.close()
            except Exception:
                pass
