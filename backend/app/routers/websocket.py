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
import json
import time
import uuid
from dataclasses import dataclass
from typing import AsyncIterator, NamedTuple

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

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
    get_safe_logger,
    log_integration_error,
    log_session_end,
    log_session_start,
    log_websocket_connect,
    log_websocket_disconnect,
)
from app.services.idle_scaler import get_idle_scale_down_scheduler
from app.services.auth import authenticate_access_token, is_admin_user
from app.services.session_registry import (
    active_session_registry,
    get_session_registry,
)
from app.services.room_service import get_room_service
from app.services.transcription import TranscriptionService
from app.services.translation import translate_segment
from app.utils.audio import validate_audio_chunk
from app.services.pipeline_instrumentation import (
    CURRENT, PipelineTelemetry, context, duration_ms, error_type,
    segment_id as safe_segment_id, validate_benchmark_run_id,
)

router = APIRouter()

_logger = get_safe_logger()


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
_SCREEN_SHARE_BUFFER_SECONDS = 2.4
_SCREEN_SHARE_MAX_WORDS = 14
_SCREEN_SHARE_MAX_FRAGMENTS = 4
_SCREEN_SHARE_TERMINAL_MIN_WORDS = 4
_SCREEN_SHARE_LOW_CONFIDENCE = 0.45
_ROOM_PARTIAL_TRANSLATION_DELAY = 0.5
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
    instrumentation_started_at: float | None = None


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


class _SingleStreamCaptionBuffer:
    """Coalesce tiny screen-share finals before translation/publication."""

    def __init__(self) -> None:
        self._messages: list[FinalizedSegmentMessage] = []
        self._instrumentation_starts: list[float] = []

    def add(self, message: FinalizedSegmentMessage) -> list[FinalizedSegmentMessage]:
        started = time.perf_counter()
        text = _source_text(message).strip()
        if not text or _is_suspicious_micro_fragment(message):
            context().emit("arbitration_or_buffer_completed", kind="single_buffer", outcome="dropped",
                           segment_id=message.segment_id, duration_ms=duration_ms(started),
                           reason="empty_or_suspicious")
            return []

        ready: list[FinalizedSegmentMessage] = []
        if self._messages:
            first = self._messages[0]
            if (
                first.speaker_label != message.speaker_label
                or first.spoken_language != message.spoken_language
            ):
                flushed = self.flush()
                if flushed is not None:
                    ready.append(flushed)

        self._messages.append(message)
        self._instrumentation_starts.append(started)
        if self._should_flush():
            flushed = self.flush()
            if flushed is not None:
                ready.append(flushed)
        return ready

    def flush(self) -> FinalizedSegmentMessage | None:
        if not self._messages:
            return None

        messages = self._messages
        self._messages = []
        starts = self._instrumentation_starts
        self._instrumentation_starts = []
        for message, started in zip(messages, starts):
            context().emit("arbitration_or_buffer_completed", kind="single_buffer", outcome="emitted",
                           segment_id=message.segment_id, duration_ms=duration_ms(started))
        first = messages[0]
        last = messages[-1]
        merged_text = " ".join(
            text for message in messages if (text := _source_text(message).strip())
        )
        if not merged_text:
            return None

        confidences = [
            message.confidence
            for message in messages
            if message.confidence is not None
        ]
        confidence = sum(confidences) / len(confidences) if confidences else None
        return FinalizedSegmentMessage(
            segment_id=first.segment_id,
            speaker_label=first.speaker_label,
            text_vi=merged_text if first.spoken_language == "vi" else "",
            text_en=merged_text if first.spoken_language == "en" else "",
            spoken_language=first.spoken_language,
            timestamp_start=first.timestamp_start,
            timestamp_end=last.timestamp_end,
            confidence=confidence,
        )

    def _should_flush(self) -> bool:
        if not self._messages:
            return False

        merged_text = " ".join(_source_text(message) for message in self._messages).strip()
        word_count = len(merged_text.split())
        if word_count >= _SCREEN_SHARE_MAX_WORDS:
            return True
        if len(self._messages) >= _SCREEN_SHARE_MAX_FRAGMENTS and word_count >= 2:
            return True
        if (
            merged_text.endswith((".", "!", "?"))
            and word_count >= _SCREEN_SHARE_TERMINAL_MIN_WORDS
        ):
            return True

        first = self._messages[0]
        last = self._messages[-1]
        if last.timestamp_end > first.timestamp_start:
            return (
                last.timestamp_end - first.timestamp_start
                >= _SCREEN_SHARE_BUFFER_SECONDS
            )
        return False


# Sentinel pushed onto the unified output queue when the finalized-candidate
# arbiter has finished, signalling the session loop to stop reading.
_ARBITRATION_DONE = object()
_DUAL_CANDIDATE_QUEUE_SIZE = 32
_DUAL_PARTIAL_QUEUE_SIZE = 64
_DUAL_OUTPUT_QUEUE_SIZE = 64


# ---------------------------------------------------------------------------
# Helper: send a Pydantic model as JSON
# ---------------------------------------------------------------------------


async def _send(websocket: WebSocket, message) -> bool:
    """Serialize *message* to JSON and send it to *websocket*.

    Silently ignores send errors that occur after a disconnect has already
    been initiated, so teardown code can call this unconditionally.
    """
    telemetry = CURRENT.get()
    is_partial = isinstance(message, PartialSegmentMessage)
    is_final = isinstance(message, FinalizedSegmentMessage)
    started = time.perf_counter()
    failure = None
    success = False
    if telemetry is not None and telemetry.admitted:
        telemetry.partial_count += int(is_partial)
        telemetry.final_count += int(is_final)
    try:
        await websocket.send_text(message.model_dump_json())
        success = True
    except asyncio.CancelledError as exc:
        failure = exc
        if telemetry is not None and telemetry.admitted:
            telemetry.fail("send_failed", exc)
        raise
    except Exception as exc:  # noqa: BLE001
        failure = exc
        if telemetry is not None and telemetry.admitted:
            telemetry.fail("send_failed", exc)
    finally:
        elapsed = duration_ms(started)
        if telemetry is not None and telemetry.admitted:
            if isinstance(message, SessionEndMessage):
                telemetry.session_end_send_success = success
            if is_partial:
                telemetry.partial_send_success_count += int(success)
                telemetry.partial_send_failure_count += int(not success)
                telemetry.partial_send_duration_sum_ms += elapsed
                telemetry.partial_send_duration_max_ms = max(telemetry.partial_send_duration_max_ms or 0, elapsed)
                if failure:
                    telemetry.partial_send_error_type = error_type(failure)
            elif is_final:
                telemetry.emit("websocket_caption_send_completed", kind="final", aggregate=False,
                               segment_id=message.segment_id, success=success, error=failure,
                               duration_ms=elapsed, send_duration_ms=elapsed)
    return success


async def _send_caption(
    websocket: WebSocket,
    message,
    *,
    room_code: str | None,
    room_host_token: str | None,
) -> None:
    """Send a transcription message and fan out finalized room captions."""

    await _send(websocket, message)
    if (
        room_code
        and room_host_token
        and isinstance(message, FinalizedSegmentMessage)
    ):
        await get_room_service().publish_finalized_segment(
            room_code,
            room_host_token,
            message,
        )


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


def _access_token_from_subprotocol(websocket: WebSocket) -> str | None:
    """Read the JWT from the second requested WebSocket subprotocol.

    Browsers cannot set an Authorization header on a WebSocket handshake. The
    token is therefore sent as a subprotocol rather than a query parameter so
    it is not embedded in URLs, application logs, or browser history.
    """

    values = [
        value.strip()
        for value in (websocket.headers.get("sec-websocket-protocol") or "").split(",")
        if value.strip()
    ]
    return values[1] if len(values) == 2 and values[0] == "livecap.v1" else None


def _authenticated_subprotocol(websocket: WebSocket, auth_enabled: bool) -> str | None:
    """Select the negotiated protocol only when it matches the auth contract."""

    if not auth_enabled:
        return None
    return "livecap.v1" if _access_token_from_subprotocol(websocket) else None


def _final_text(message: FinalizedSegmentMessage, source_language: str) -> str:
    """Return the source transcript text from a finalized message."""
    return message.text_vi if source_language == "vi" else message.text_en


def _source_text(message: FinalizedSegmentMessage) -> str:
    return message.text_vi if message.spoken_language == "vi" else message.text_en


def _is_suspicious_micro_fragment(message: FinalizedSegmentMessage) -> bool:
    text = _source_text(message).strip()
    if not text or message.confidence is None:
        return False
    tokens = [token for token in text.split() if token.strip(".,!?;:")]
    return len(tokens) <= 1 and message.confidence < _SCREEN_SHARE_LOW_CONFIDENCE


def _log_candidate_dropped(
    session_id: str,
    candidate: TranscriptCandidate,
    reason: str,
) -> None:
    telemetry = context(session_id)
    telemetry.emit("arbitration_or_buffer_completed", kind="dual_arbitration", outcome="dropped",
                   reason=reason, segment_id=safe_segment_id(candidate.message.segment_id,
                                                            telemetry.stream_mode, candidate.source_language),
                   duration_ms=duration_ms(candidate.instrumentation_started_at)
                   if candidate.instrumentation_started_at is not None else None)


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
        translated = await _translate_observed(
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
                await candidate_queue.put(
                    TranscriptCandidate(
                        source_language=source_language,
                        transcript_text=transcript_text,
                        message=msg,
                        mode=mode,
                        created_at=time.monotonic(),
                        instrumentation_started_at=time.perf_counter(),
                    )
                )
    except Exception as exc:
        context(session_id).fail("transcribe_failed", exc)
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
        telemetry = context(session_id)
        telemetry.emit("arbitration_or_buffer_completed", kind="dual_arbitration", outcome="emitted",
                       segment_id=safe_segment_id(selected.message.segment_id, telemetry.stream_mode,
                                                  selected.source_language),
                       duration_ms=duration_ms(selected.instrumentation_started_at)
                       if selected.instrumentation_started_at is not None else None)
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
    telemetry = PipelineTelemetry(benchmark_run_id=validate_benchmark_run_id(
        websocket.query_params.get("benchmark_run_id")))
    admission_started = telemetry.started_at
    token = CURRENT.set(telemetry)
    try:
        await _websocket_transcribe(websocket, telemetry, admission_started)
    except BaseException as exc:
        if telemetry.admitted:
            telemetry.fail("internal_error", exc)
        else:
            telemetry.admission("store_error", admission_started, exc)
        raise
    finally:
        try:
            telemetry.finish()
        finally:
            CURRENT.reset(token)


async def _translate_observed(segment, **kwargs):
    """Count translation outcomes without changing or logging the payload."""
    telemetry = CURRENT.get()
    source = segment.text_vi if segment.spoken_language == "vi" else segment.text_en
    try:
        translated = await translate_segment(segment, **kwargs)
    except Exception as exc:
        if telemetry is not None:
            telemetry.translation_failure_count += 1
            telemetry.fail("translation_degraded", exc)
        raise
    if telemetry is not None:
        target = translated.text_en if segment.spoken_language == "vi" else translated.text_vi
        if not source.strip():
            telemetry.translation_skipped_count += 1
        elif target.strip():
            telemetry.translation_success_count += 1
        else:
            telemetry.translation_failure_count += 1
            telemetry.fail("translation_degraded")
    return translated


async def _websocket_transcribe(websocket: WebSocket, telemetry: PipelineTelemetry,
                                admission_started: float) -> None:
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
    room_code = (websocket.query_params.get("room_code") or "").strip().upper()
    room_host_token = websocket.query_params.get("room_token")
    language_mode = _resolve_language_mode(
        websocket,
        fallback_source_language_code=settings.transcribe_language_code,
    )
    use_dual_stream = (
        settings.bilingual_dual_stream
        and websocket.query_params.get("stream_mode") != "single"
    )
    telemetry.session_id = session_id
    telemetry.stream_mode = "dual" if use_dual_stream else "single"
    if language_mode is not None:
        telemetry.source_language = language_mode.source_language_code
        telemetry.target_language = language_mode.target_language_code

    auth_protocol = _authenticated_subprotocol(websocket, settings.enable_auth)
    await websocket.accept(subprotocol=auth_protocol)

    auth_user = None
    auth_user_is_admin = False
    if settings.enable_auth:
        token = _access_token_from_subprotocol(websocket)
        try:
            started = time.perf_counter()
            try:
                auth_user = authenticate_access_token(token or "")
            finally:
                telemetry.auth_duration_ms = duration_ms(started)
            started = time.perf_counter()
            try:
                auth_user_is_admin = await asyncio.to_thread(is_admin_user, auth_user)
            finally:
                telemetry.admin_check_duration_ms = duration_ms(started)
        except HTTPException as exc:
            telemetry.admission("auth_rejected", admission_started, exc)
            await _send_error(
                websocket,
                message="Sign in is required to start a LiveCap session.",
                code=ErrorCode.UNAUTHORIZED,
            )
            await websocket.close(code=1008)
            return

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

    if room_code:
        room_bound = (
            settings.enable_shared_rooms
            and room_host_token is not None
            and await get_room_service().bind_host_session(
                room_code,
                room_host_token,
                session_id,
            )
        )
        if not room_bound:
            await _send_error(
                websocket,
                message="The shared room was not found, expired, or is not owned by this host.",
                code=ErrorCode.INVALID_ROOM,
            )
            await websocket.close(code=1008)
            return

    client_ip = _resolve_client_ip(websocket)
    started = time.perf_counter()
    try:
        session_registry = get_session_registry(settings)
        session_registered = False
        limit_result = session_registry.try_register(
            session_id=session_id,
            client_ip=client_ip,
            max_total=settings.max_concurrent_sessions,
            max_per_ip=settings.max_sessions_per_ip,
        )
    finally:
        telemetry.registry_duration_ms = duration_ms(started)
    if not limit_result.allowed:
        telemetry.admission("limit_rejected", admission_started)
        _logger.warning(
            "Session rejected by active-session limit",
            extra={
                "event": "session_rejected",
                "session_id": session_id,
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

    # --- Usage quota check (B2C tier enforcement) ---
    # Only enforced when auth is on and quota tracking is enabled.
    if auth_user is not None and settings.enable_auth:
        started = time.perf_counter()
        try:
            from app.services.usage_quota import reserve_weekly_session  # noqa: PLC0415
            quota_error = reserve_weekly_session(
                auth_user.user_id, is_admin=auth_user_is_admin
            )
            if quota_error:
                telemetry.quota_duration_ms = duration_ms(started)
                telemetry.admission("quota_rejected", admission_started)
                _logger.warning(
                    "Session rejected by quota limit",
                    extra={"event": "quota_exceeded", "session_id": session_id},
                )
                session_registry.unregister(session_id)
                session_registered = False
                await _send_error(websocket, message=quota_error, code=ErrorCode.QUOTA_EXCEEDED)
                await websocket.close(code=1008)
                return
        except Exception as exc:  # noqa: BLE001 — preserve quota fail-open behavior
            telemetry.quota_error_type = error_type(exc)
        finally:
            telemetry.quota_duration_ms = duration_ms(started)

    telemetry.admitted = True
    telemetry.admission("store_error" if telemetry.quota_error_type else "admitted", admission_started)
    telemetry.started_at = time.perf_counter()

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

    # Flag set when the session should be torn down due to an error.
    error_event: asyncio.Event = asyncio.Event()
    error_details: dict = {}  # mutable container for error info

    async def _read_frames() -> None:
        """Consume incoming WebSocket frames in a background task.

        * Binary frames are validated and pushed to *audio_queue*.
        * JSON frames with ``{"type": "stop"}`` end this session.
        * Malformed audio triggers an error and stops the session.
        """
        try:
            while True:
                try:
                    raw = await websocket.receive()
                except WebSocketDisconnect as exc:
                    telemetry.fail("client_disconnect", exc)
                    telemetry.close_code = exc.code if isinstance(exc.code, int) else None
                    break

                # Client disconnect.
                if raw.get("type") == "websocket.disconnect":
                    telemetry.fail("client_disconnect")
                    telemetry.close_code = raw.get("code") if isinstance(raw.get("code"), int) else None
                    break

                if "bytes" in raw and raw["bytes"] is not None:
                    # Binary frame — audio chunk.
                    data: bytes = raw["bytes"]
                    telemetry.audio_bytes_received += len(data)
                    telemetry.audio_frames_received += 1
                    valid, reason = validate_audio_chunk(data)
                    if not valid:
                        telemetry.fail("internal_error")
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

                    if use_dual_stream:
                        await vi_audio_queue.put(data)
                        await en_audio_queue.put(data)
                    else:
                        await audio_queue.put(data)

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
    _session_start_ts = time.monotonic()

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
        if reader_task.done() and not reader_task.cancelled():
            reader_error = reader_task.exception()
            if reader_error is not None:
                telemetry.fail("internal_error", reader_error)

        # Record minutes used against the user's monthly quota.
        if auth_user is not None and settings.enable_auth:
            try:
                from app.services.usage_quota import add_minutes  # noqa: PLC0415
                elapsed_minutes = max(1, int((time.monotonic() - _session_start_ts) / 60))
                add_minutes(auth_user.user_id, elapsed_minutes)
            except Exception:  # noqa: BLE001
                pass

        log_websocket_disconnect(session_id)

    try:
        # A zero timeout means recordings have no wall-clock cap.
        async with asyncio.timeout(settings.session_timeout or None):
            pending_room_partial: PartialSegmentMessage | None = None
            room_partial_task: asyncio.Task[None] | None = None
            room_partial_epoch = 0
            last_translated_partial: tuple[str, str] | None = None

            async def publish_translated_room_partials() -> None:
                nonlocal pending_room_partial, last_translated_partial
                while True:
                    # Coalesce rapid ASR revisions before paying for translation.
                    await asyncio.sleep(_ROOM_PARTIAL_TRANSLATION_DELAY)
                    partial = pending_room_partial
                    pending_room_partial = None
                    if partial is None:
                        return
                    source_text = _source_text(partial).strip()
                    key = (partial.segment_id, source_text)
                    if key == last_translated_partial or len(source_text.split()) < 2:
                        if pending_room_partial is None:
                            return
                        continue
                    last_translated_partial = key
                    epoch = room_partial_epoch
                    from app.models import Segment

                    translated = await _translate_observed(
                        Segment(
                            segment_id=partial.segment_id,
                            speaker_label=partial.speaker_label,
                            text_vi=partial.text_vi,
                            text_en=partial.text_en,
                            spoken_language=partial.spoken_language,
                            is_final=False,
                        ),
                        session_id=session_id,
                    )
                    if epoch == room_partial_epoch and room_code and room_host_token:
                        await get_room_service().publish_partial_segment(
                            room_code,
                            room_host_token,
                            PartialSegmentMessage.from_segment(translated),
                        )
                    if pending_room_partial is None:
                        return

            async def send_room_partial(msg: PartialSegmentMessage) -> None:
                nonlocal pending_room_partial, room_partial_task
                await _send(websocket, msg)
                if room_code and room_host_token:
                    await get_room_service().publish_partial_segment(
                        room_code, room_host_token, msg
                    )
                    pending_room_partial = msg
                    if room_partial_task is None or room_partial_task.done():
                        room_partial_task = asyncio.create_task(
                            publish_translated_room_partials()
                        )

            async def stop_room_partials() -> None:
                if room_partial_task is not None:
                    room_partial_task.cancel()
                    await asyncio.gather(room_partial_task, return_exceptions=True)

            if use_dual_stream:
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
                            telemetry.fail("transcribe_failed", msg)
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
                        if isinstance(msg, PartialSegmentMessage):
                            await send_room_partial(msg)
                        else:
                            room_partial_epoch += 1
                            pending_room_partial = None
                            await _send_caption(
                                websocket,
                                msg,
                                room_code=room_code or None,
                                room_host_token=room_host_token,
                            )
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
                    await stop_room_partials()

            else:
                transcription_service = TranscriptionService(
                    session_id=session_id,
                    settings=settings,
                    language_code=language_mode.source_language_code,
                )
                caption_buffer = (
                    _SingleStreamCaptionBuffer()
                    if websocket.query_params.get("stream_mode") == "single"
                    else None
                )
                async def emit_single_finalized(
                    finalized_msg: FinalizedSegmentMessage,
                ) -> None:
                    from app.models import Segment  # local import to avoid cycles

                    segment = Segment(
                        segment_id=finalized_msg.segment_id,
                        speaker_label=finalized_msg.speaker_label,
                        text_vi=finalized_msg.text_vi,
                        text_en=finalized_msg.text_en,
                        spoken_language=finalized_msg.spoken_language,
                        is_final=True,
                        timestamp_start=finalized_msg.timestamp_start,
                        timestamp_end=finalized_msg.timestamp_end,
                    )
                    try:
                        translated = await _translate_observed(
                            segment,
                            session_id=session_id,
                            source_language_code=language_mode.source_translate_code,
                            target_language_code=language_mode.target_language_code,
                        )
                        outgoing = FinalizedSegmentMessage(
                            segment_id=translated.segment_id,
                            speaker_label=translated.speaker_label,
                            text_vi=translated.text_vi,
                            text_en=translated.text_en,
                            spoken_language=translated.spoken_language,
                            timestamp_start=translated.timestamp_start,
                            timestamp_end=translated.timestamp_end,
                        )
                    except Exception as exc:
                        log_integration_error(
                            session_id=session_id,
                            service_name="Amazon Translate",
                            error=exc,
                        )
                        outgoing = finalized_msg

                    await _send_caption(
                        websocket,
                        outgoing,
                        room_code=room_code or None,
                        room_host_token=room_host_token,
                    )

                try:
                    results = transcription_service.transcribe(audio_queue).__aiter__()
                    while True:
                        try:
                            msg = await anext(results)
                        except StopAsyncIteration:
                            break
                        except Exception as exc:
                            telemetry.fail("transcribe_failed", exc)
                            raise
                        # Check if an audio-format error was flagged by the reader.
                        if error_event.is_set():
                            break

                        if isinstance(msg, PartialSegmentMessage):
                            await send_room_partial(msg)

                        elif isinstance(msg, FinalizedSegmentMessage):
                            room_partial_epoch += 1
                            pending_room_partial = None
                            ready_messages = (
                                caption_buffer.add(msg) if caption_buffer is not None else [msg]
                            )
                            for ready_message in ready_messages:
                                await emit_single_finalized(ready_message)

                        elif isinstance(msg, Exception):
                            telemetry.fail("transcribe_failed", msg)
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
                finally:
                    await stop_room_partials()

                if caption_buffer is not None:
                    pending = caption_buffer.flush()
                    if pending is not None:
                        await emit_single_finalized(pending)

            # If an audio-format error was flagged, surface it now.
            if error_event.is_set():
                await _send_error(
                    websocket,
                    message=error_details.get("message", "Invalid audio format"),
                    code=error_details.get("code", ErrorCode.INVALID_AUDIO_FORMAT),
                )

    except TimeoutError as exc:
        telemetry.fail("timeout", exc)
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

    except WebSocketDisconnect as exc:
        telemetry.fail("client_disconnect", exc)
        _logger.info(
            "WebSocket disconnected",
            extra={"event": "websocket_disconnect_mid_session", "session_id": session_id},
        )

    except Exception as exc:
        if "transcribe_failed" not in telemetry.failures:
            telemetry.fail("internal_error", exc)
        # Unexpected error (Requirement 3.7).
        _logger.error(
            "Unexpected error in WebSocket handler",
            extra={"session_id": session_id, "error_type": error_type(exc)},
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
            # A transcription session can end while the room's screen share
            # continues. Only the explicit room-close endpoint archives it.
            if session_registered:
                session_registry.unregister(session_id)
                get_idle_scale_down_scheduler(
                    session_registry
                ).schedule_if_idle(settings=settings)
            try:
                await websocket.close()
            except Exception:
                pass
