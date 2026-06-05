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
import logging
import uuid
from typing import AsyncIterator, NamedTuple

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.config import get_settings
from app.models import (
    ErrorCode,
    ErrorMessage,
    FinalizedSegmentMessage,
    PartialSegmentMessage,
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


def _resolve_language_mode(websocket: WebSocket) -> LanguageMode | None:
    """Return the validated manual translation mode from query params."""
    source = websocket.query_params.get("source") or _DEFAULT_LANGUAGE_MODE.source_language_code
    target = websocket.query_params.get("target") or _DEFAULT_LANGUAGE_MODE.target_language_code
    return _ALLOWED_LANGUAGE_MODES.get((source, target))


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
    session_id = str(uuid.uuid4())
    language_mode = _resolve_language_mode(websocket)

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

    log_websocket_connect(session_id)

    # Record session-start event (Requirement 10.1).
    log_session_start(session_id)

    # Send session_start to the client (Requirement 2.2).
    await _send(websocket, SessionStartMessage(session_id=session_id))

    _logger.info(
        "Session opened",
        extra={"event": "session_open", "session_id": session_id},
    )

    # Queue that bridges the incoming-frame reader with TranscriptionService.
    # Audio bytes are pushed here; ``None`` signals end-of-stream.
    audio_queue: asyncio.Queue[bytes | None] = asyncio.Queue()

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

                    await audio_queue.put(data)
                    if settings.audio_pipeline_debug:
                        _logger.info(
                            "audio_pipeline_audio_queued",
                            extra={
                                "event": "audio_pipeline_audio_queued",
                                "session_id": session_id,
                                "byte_length": len(data),
                                "queue_size": audio_queue.qsize(),
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

        finally:
            # Signal end-of-stream to TranscriptionService regardless of how
            # the loop exited (stop, disconnect, or error).
            await audio_queue.put(None)

    # Start the frame-reader background task.
    reader_task = asyncio.ensure_future(_read_frames())

    transcription_service = TranscriptionService(
        session_id=session_id,
        settings=settings,
        language_code=language_mode.source_language_code,
    )

    session_end_sent = False

    async def _teardown(send_session_end: bool = True) -> None:
        """Send ``session_end`` (once), cancel the reader, log disconnect."""
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
        # Push None to stop the TranscriptionService audio feed.
        await audio_queue.put(None)

    except WebSocketDisconnect:
        # Client disconnected mid-session; teardown proceeds normally.
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
        await audio_queue.put(None)

    finally:
        # Always send session_end and clean up (Requirements 2.5, 10.2).
        await _teardown(send_session_end=True)
        try:
            await websocket.close()
        except Exception:
            pass
