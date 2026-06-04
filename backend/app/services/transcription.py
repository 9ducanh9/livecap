"""Transcription_Service: Amazon Transcribe Streaming integration.

Provides :class:`TranscriptionService`, which opens an Amazon Transcribe
Streaming session configured for:

* Media encoding: PCM, 16 kHz, mono
* Fixed language code from configuration (default: ``vi-VN``)
* Speaker labels enabled through the Python SDK's supported
  ``show_speaker_label`` option

The service feeds audio chunks to the stream as they arrive and processes
the resulting transcription events, emitting:

* :class:`~app.models.PartialSegmentMessage` for partial (revisable) results
* :class:`~app.models.FinalizedSegmentMessage` for final (stable) results

Partial revisions of the same phrase share one Segment_ID (CP-2).

Speaker labels from Transcribe (``"spk_0"``, ``"spk_1"``, …) are mapped to
human-readable ``"Speaker 1"``, ``"Speaker 2"``, … labels that are stable
within the Session (Requirement 4.4).

The spoken language is derived from Transcribe's per-result language field when
available, otherwise from the configured fixed language code.

Transcribe errors are propagated to the caller and recorded through the
:mod:`~app.services.logging_service`.

Usage example
-------------
.. code-block:: python

    service = TranscriptionService(session_id="abc123", settings=get_settings())
    async for msg in service.transcribe(audio_queue):
        await websocket.send_json(msg.model_dump())

where ``audio_queue`` is an ``asyncio.Queue[bytes | None]`` — push audio
chunks onto the queue while capturing; push ``None`` to signal end-of-stream.
"""

from __future__ import annotations

import asyncio
import logging
from typing import AsyncIterator

from amazon_transcribe.client import TranscribeStreamingClient
from amazon_transcribe.handlers import TranscriptResultStreamHandler
from amazon_transcribe.model import TranscriptEvent

from app.config import Settings, get_settings
from app.models import (
    FinalizedSegmentMessage,
    PartialSegmentMessage,
    SegmentIdAllocator,
)
from app.services.logging_service import get_logger, log_integration_error

# Sample rate and encoding required by the Expected_Audio_Format.
_SAMPLE_RATE_HZ = 16_000
_MEDIA_ENCODING = "pcm"
_NUMBER_OF_CHANNELS = 1

# Mapping from Transcribe language codes to the MVP's internal short codes.
_LANG_MAP: dict[str, str] = {
    "vi-VN": "vi",
    "en-US": "en",
}


class TranscriptionService:
    """Manages a single Amazon Transcribe Streaming session.

    Create one instance per WebSocket session and call :meth:`transcribe` to
    start streaming.

    Parameters
    ----------
    session_id:
        The Session_ID of the active session, used for logging.
    settings:
        Application settings.  Defaults to the cached singleton from
        :func:`~app.config.get_settings`.
    """

    def __init__(
        self,
        session_id: str,
        settings: Settings | None = None,
    ) -> None:
        self._session_id = session_id
        self._settings = settings or get_settings()
        self._logger: logging.Logger = get_logger()

        # Allocates stable Segment_IDs within this session (CP-2).
        self._id_allocator = SegmentIdAllocator(prefix="seg")

        # Maps Transcribe raw speaker labels ("spk_0", "spk_1", …) to
        # human-readable sequential integers ("Speaker 1", "Speaker 2", …)
        # consistent within the Session (Requirements 4.2, 4.4).
        self._speaker_map: dict[str, str] = {}
        self._next_speaker_num: int = 1

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def transcribe(
        self,
        audio_queue: "asyncio.Queue[bytes | None]",
    ) -> AsyncIterator[PartialSegmentMessage | FinalizedSegmentMessage]:
        """Stream audio chunks to Transcribe and yield segment messages in real time.

        Audio chunks are consumed from *audio_queue* and forwarded to Amazon
        Transcribe Streaming concurrently with event processing, so segment
        messages are yielded to the caller as soon as Transcribe produces them
        — not after the session ends.

        Parameters
        ----------
        audio_queue:
            An ``asyncio.Queue`` from which audio chunks (``bytes``) are
            consumed.  A sentinel value of ``None`` signals end-of-stream.

        Yields
        ------
        PartialSegmentMessage | FinalizedSegmentMessage
            Segment messages produced by Transcribe, ready to be forwarded
            to the Frontend over the Streaming_Channel.

        Raises
        ------
        Exception
            Any exception raised by Transcribe Streaming is logged via the
            Logging_Service and then re-raised so the WebSocket handler can
            send an error message to the Frontend (Requirement 3.7).
        """

        # Bridge the concurrent producer tasks (audio sender + Transcribe event
        # handler) with the async generator consumer using an asyncio.Queue.
        # The sentinel ``None`` signals end-of-stream; an ``Exception`` instance
        # signals that an error occurred and should be re-raised.
        result_queue: asyncio.Queue[
            PartialSegmentMessage | FinalizedSegmentMessage | Exception | None
        ] = asyncio.Queue()

        client = TranscribeStreamingClient(region=self._settings.aws_region)

        try:
            stream = await client.start_stream_transcription(
                language_code=self._settings.transcribe_language_code,
                media_sample_rate_hz=_SAMPLE_RATE_HZ,
                media_encoding=_MEDIA_ENCODING,
                show_speaker_label=True,
                number_of_channels=_NUMBER_OF_CHANNELS,
            )
        except Exception as exc:
            log_integration_error(
                self._session_id, "Amazon Transcribe Streaming", exc
            )
            raise

        handler = _SegmentHandler(
            stream.output_stream,
            result_queue=result_queue,
            id_allocator=self._id_allocator,
            speaker_map=self._speaker_map,
            next_speaker_num_ref=self,
            logger=self._logger,
            session_id=self._session_id,
        )

        # Coroutine that feeds audio chunks into the Transcribe input stream.
        async def _send_audio() -> None:
            try:
                while True:
                    chunk = await audio_queue.get()
                    if chunk is None:
                        # End-of-stream sentinel received.
                        break
                    if self._settings.audio_pipeline_debug:
                        self._logger.info(
                            "audio_pipeline_send_audio_event",
                            extra={
                                "event": "audio_pipeline_send_audio_event",
                                "session_id": self._session_id,
                                "byte_length": len(chunk),
                            },
                        )
                    await stream.input_stream.send_audio_event(audio_chunk=chunk)
            except Exception as exc:
                log_integration_error(
                    self._session_id, "Amazon Transcribe Streaming", exc
                )
                await result_queue.put(exc)
            finally:
                await stream.input_stream.end_stream()

        # Run audio sender and event handler as background tasks so we can
        # yield from result_queue in real time while they run concurrently.
        async def _run_producers() -> None:
            try:
                await asyncio.gather(
                    _send_audio(),
                    handler.handle_events(),
                )
            except Exception as exc:
                log_integration_error(
                    self._session_id, "Amazon Transcribe Streaming", exc
                )
                await result_queue.put(exc)
            finally:
                # Signal the consumer loop to stop after all events are drained.
                await result_queue.put(None)

        producer_task = asyncio.ensure_future(_run_producers())

        # Consume and yield messages as they arrive while the producers run.
        try:
            while True:
                item = await result_queue.get()
                if item is None:
                    # End-of-stream sentinel: producers have finished.
                    break
                if isinstance(item, Exception):
                    raise item
                yield item
        except Exception:
            producer_task.cancel()
            raise
        finally:
            # Ensure the producer task is awaited to surface any residual errors
            # and avoid "task destroyed but it is pending" warnings.
            try:
                await producer_task
            except Exception:
                pass

    async def transcribe_streaming(
        self,
        audio_queue: "asyncio.Queue[bytes | None]",
        message_callback: "asyncio.Queue[PartialSegmentMessage | FinalizedSegmentMessage]",
    ) -> None:
        """Stream audio to Transcribe and push segment messages to *message_callback*.

        This variant is designed for use in the WebSocket handler where the
        caller wants to receive messages as they arrive rather than waiting for
        the entire session to complete.

        Parameters
        ----------
        audio_queue:
            Queue of PCM audio chunks.  Push ``None`` to end the stream.
        message_callback:
            Output queue to which segment messages are pushed as they arrive.

        Raises
        ------
        Exception
            Re-raised after logging when Transcribe returns an error.
        """

        client = TranscribeStreamingClient(region=self._settings.aws_region)

        try:
            stream = await client.start_stream_transcription(
                language_code=self._settings.transcribe_language_code,
                media_sample_rate_hz=_SAMPLE_RATE_HZ,
                media_encoding=_MEDIA_ENCODING,
                show_speaker_label=True,
                number_of_channels=_NUMBER_OF_CHANNELS,
            )
        except Exception as exc:
            log_integration_error(
                self._session_id, "Amazon Transcribe Streaming", exc
            )
            raise

        handler = _SegmentHandler(
            stream.output_stream,
            result_queue=message_callback,
            id_allocator=self._id_allocator,
            speaker_map=self._speaker_map,
            next_speaker_num_ref=self,
            logger=self._logger,
            session_id=self._session_id,
        )

        async def _send_audio() -> None:
            try:
                while True:
                    chunk = await audio_queue.get()
                    if chunk is None:
                        break
                    if self._settings.audio_pipeline_debug:
                        self._logger.info(
                            "audio_pipeline_send_audio_event",
                            extra={
                                "event": "audio_pipeline_send_audio_event",
                                "session_id": self._session_id,
                                "byte_length": len(chunk),
                            },
                        )
                    await stream.input_stream.send_audio_event(audio_chunk=chunk)
            except Exception as exc:
                log_integration_error(
                    self._session_id, "Amazon Transcribe Streaming", exc
                )
                # Surface the error to message_callback consumers before re-raising.
                await message_callback.put(exc)
                raise
            finally:
                await stream.input_stream.end_stream()

        try:
            await asyncio.gather(
                _send_audio(),
                handler.handle_events(),
            )
        except Exception as exc:
            log_integration_error(
                self._session_id, "Amazon Transcribe Streaming", exc
            )
            raise

    # ------------------------------------------------------------------
    # Internal helpers (called by _SegmentHandler)
    # ------------------------------------------------------------------

    def _resolve_speaker_label(self, raw_label: str) -> str:
        """Map a raw Transcribe speaker label to a human-readable "Speaker N".

        The mapping is stable within the Session: the first new raw label seen
        gets "Speaker 1", the second gets "Speaker 2", etc.  The same raw label
        always returns the same human-readable string (Requirements 4.2, 4.4).
        """
        if raw_label not in self._speaker_map:
            self._speaker_map[raw_label] = f"Speaker {self._next_speaker_num}"
            self._next_speaker_num += 1
        return self._speaker_map[raw_label]

    def _resolve_spoken_language(self, language_code: str | None) -> str:
        """Map a Transcribe language code to the MVP's internal short code.

        Returns ``"vi"`` for ``"vi-VN"`` and ``"en"`` for ``"en-US"``.
        Defaults to the configured fixed Transcribe language when the result
        does not include language metadata.
        """
        resolved_code = language_code or self._settings.transcribe_language_code
        return _LANG_MAP.get(resolved_code, "vi")


# ---------------------------------------------------------------------------
# Internal Transcribe event handler
# ---------------------------------------------------------------------------


class _SegmentHandler(TranscriptResultStreamHandler):
    """Processes Transcribe Streaming events and converts them to segment messages.

    This handler is called by the Amazon Transcribe Streaming SDK for each
    transcription event.  It converts the raw SDK objects into the backend's
    :class:`~app.models.PartialSegmentMessage` /
    :class:`~app.models.FinalizedSegmentMessage` types and pushes them onto the
    ``result_queue``.

    Parameters
    ----------
    output_stream:
        The Transcribe streaming output stream (passed to the base class).
    result_queue:
        Destination queue for produced messages.
    id_allocator:
        The :class:`~app.models.SegmentIdAllocator` for this Session.
    speaker_map:
        The mutable speaker-label map belonging to :class:`TranscriptionService`.
    next_speaker_num_ref:
        The owning :class:`TranscriptionService` instance, used to call
        ``_resolve_speaker_label`` and ``_resolve_spoken_language``.
    logger:
        Logger for debug/warning output.
    session_id:
        The Session_ID, used when logging integration errors.
    """

    def __init__(
        self,
        output_stream,
        *,
        result_queue: asyncio.Queue,
        id_allocator: SegmentIdAllocator,
        speaker_map: dict[str, str],
        next_speaker_num_ref: "TranscriptionService",
        logger: logging.Logger,
        session_id: str,
    ) -> None:
        super().__init__(output_stream)
        self._result_queue = result_queue
        self._id_allocator = id_allocator
        self._service = next_speaker_num_ref
        self._logger = logger
        self._session_id = session_id

    async def handle_transcript_event(
        self, transcript_event: TranscriptEvent
    ) -> None:
        """Process a single :class:`TranscriptEvent` from Transcribe.

        For each result in the event:

        * If the result is *partial* (``is_partial=True``), assign or reuse the
          Segment_ID for this result and emit a
          :class:`~app.models.PartialSegmentMessage`.
        * If the result is *final* (``is_partial=False``), finalize the
          Segment_ID and emit a :class:`~app.models.FinalizedSegmentMessage`.

        Speaker labels are resolved via
        :meth:`~TranscriptionService._resolve_speaker_label` and spoken language
        via :meth:`~TranscriptionService._resolve_spoken_language`.
        """
        try:
            transcript = transcript_event.transcript
            for result in transcript.results:
                if not result.alternatives:
                    continue

                # Use the best (first) alternative.
                alternative = result.alternatives[0]
                transcript_text = alternative.transcript or ""

                # Resolve the speaker label.
                # Speaker labels are attached at the item level in Transcribe's
                # diarized output. We extract the first item that carries a
                # speaker label from the alternative.
                raw_speaker_label = _extract_speaker_label(alternative)
                speaker_label = self._service._resolve_speaker_label(
                    raw_speaker_label
                )

                # Resolve the spoken language from Transcribe's language field
                # when present, otherwise from the configured fixed language.
                language_code = _extract_language_code(result)
                spoken_language = self._service._resolve_spoken_language(
                    language_code
                )

                # Assign or reuse the Segment_ID (CP-2).
                result_key = result.result_id
                is_final = not result.is_partial

                if is_final:
                    segment_id = self._id_allocator.finalize(result_key)
                else:
                    segment_id = self._id_allocator.assign(result_key)

                # Build timing information (only meaningful for final results,
                # but we extract whatever is available).
                timestamp_start, timestamp_end = _extract_timestamps(result)

                # Determine which text column receives the spoken text.
                # Translation happens later (in the WebSocket handler / Translation
                # Service); at this stage we populate only the spoken column.
                if spoken_language == "vi":
                    text_vi = transcript_text
                    text_en = ""
                else:
                    text_vi = ""
                    text_en = transcript_text

                if is_final:
                    msg: PartialSegmentMessage | FinalizedSegmentMessage = (
                        FinalizedSegmentMessage(
                            segment_id=segment_id,
                            speaker_label=speaker_label,
                            text_vi=text_vi,
                            text_en=text_en,
                            spoken_language=spoken_language,
                            timestamp_start=timestamp_start,
                            timestamp_end=timestamp_end,
                        )
                    )
                else:
                    msg = PartialSegmentMessage(
                        segment_id=segment_id,
                        speaker_label=speaker_label,
                        text_vi=text_vi,
                        text_en=text_en,
                        spoken_language=spoken_language,
                    )

                await self._result_queue.put(msg)

        except Exception as exc:
            self._logger.warning(
                "Error processing Transcribe event",
                extra={
                    "session_id": self._session_id,
                    "error": str(exc),
                },
                exc_info=True,
            )
            log_integration_error(
                self._session_id, "Amazon Transcribe Streaming", exc
            )
            await self._result_queue.put(exc)


# ---------------------------------------------------------------------------
# Private extraction helpers
# ---------------------------------------------------------------------------


def _extract_speaker_label(alternative) -> str:
    """Return the raw Transcribe speaker label from *alternative*.

    Iterates over the alternative's items and returns the first non-empty
    ``speaker_label`` found. Falls back to ``"spk_0"`` when no label is
    present (e.g. before diarization data is available for a partial result).
    """
    items = getattr(alternative, "items", None) or []
    for item in items:
        label = getattr(item, "speaker_label", None)
        if label:
            return label
    return "spk_0"


def _extract_language_code(result) -> str | None:
    """Return the identified language code for *result*, or ``None``.

    Amazon Transcribe Streaming may expose the language code in different
    attributes depending on the SDK version. This helper tries several known
    attribute paths so the service stays robust across minor SDK variations.
    """
    # Primary attribute when the SDK includes per-result language metadata.
    lang = getattr(result, "language_code", None)
    if lang:
        return lang

    # Some SDK versions expose it under language_identification.
    lang_id = getattr(result, "language_identification", None)
    if lang_id:
        if isinstance(lang_id, list) and lang_id:
            # List of LanguageWithScore objects — pick the highest-score entry.
            best = max(lang_id, key=lambda x: getattr(x, "score", 0))
            code = getattr(best, "code", None) or getattr(best, "language_code", None)
            if code:
                return code
        code = getattr(lang_id, "code", None) or getattr(lang_id, "language_code", None)
        if code:
            return code

    return None


def _extract_timestamps(result) -> tuple[float, float]:
    """Return ``(start_time, end_time)`` in seconds for *result*.

    Falls back to ``(0.0, 0.0)`` when timing data is unavailable.
    """
    start = getattr(result, "start_time", None) or 0.0
    end = getattr(result, "end_time", None) or 0.0
    return float(start), float(end)
