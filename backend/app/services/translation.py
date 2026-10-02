"""Translation_Service: Amazon Translate integration.

Implements bilingual (Vietnamese ↔ English) translation of Finalized_Segments
(task 6.1, Requirements 5.1, 5.2, 5.3, correctness property CP-8).

Public interface
----------------
translate_segment(segment, session_id) -> Segment
    Asynchronously translate a :class:`~app.models.Segment` and return a new
    :class:`~app.models.Segment` with both ``text_vi`` and ``text_en``
    populated.

TranslationService
    Injectable class (useful for testing / dependency injection) wrapping the
    same logic.

Translation directionality
--------------------------
* spoken Vietnamese (``spoken_language == "vi"``) → translate vi → en.
* spoken English   (``spoken_language == "en"``) → translate en → vi.
* The source text is placed in its own column; translated text goes in the
  other column.  A language is NEVER translated into itself (CP-8).

Error handling
--------------
If Amazon Translate raises an exception the function returns the original
segment with only the source column populated and logs the error through the
:mod:`~app.services.logging_service` (Requirement 5.3).
"""

from __future__ import annotations

import asyncio
import time
from contextvars import ContextVar
from typing import Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.models import Segment
from app.services.logging_service import get_safe_logger, log_integration_error
from app.services.pipeline_instrumentation import context, duration_ms, segment_id

# Human-readable service name used in log records (Requirement 10.3).
_SERVICE_NAME = "Amazon Translate"
_CALL_TIMING: ContextVar[dict | None] = ContextVar("translation_call_timing", default=None)
_OPERATION_START: ContextVar[float | None] = ContextVar("translation_operation_start", default=None)


class TranslationService:
    """Translates :class:`~app.models.Segment` objects using Amazon Translate.

    A single instance can safely be shared across coroutines; boto3 clients
    are thread-safe and the translation calls are dispatched via
    ``asyncio.get_event_loop().run_in_executor`` so they do not block the
    asyncio event loop (design: "Run translation asynchronously to avoid
    blocking the WebSocket handler").

    Parameters
    ----------
    aws_region:
        AWS region to use for the Translate client.  Defaults to
        ``"ap-southeast-1"``.
    """

    def __init__(self, aws_region: str = "ap-southeast-1") -> None:
        self._region = aws_region
        self._client = boto3.client("translate", region_name=aws_region)
        self._logger = get_safe_logger()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _call_translate(
        self,
        text: str,
        source_language_code: str,
        target_language_code: str,
    ) -> str:
        """Synchronous boto3 call — run inside an executor thread.

        Returns the translated string, or raises on error.
        """
        started = time.perf_counter()
        try:
            response = self._client.translate_text(
                Text=text,
                SourceLanguageCode=source_language_code,
                TargetLanguageCode=target_language_code,
            )
        finally:
            timing = _CALL_TIMING.get()
            if timing is not None:
                timing["sdk_call_duration_ms"] = duration_ms(started)
        return response["TranslatedText"]

    async def _translate_async(
        self,
        text: str,
        source_language_code: str,
        target_language_code: str,
    ) -> str:
        """Run the blocking boto3 call in the default thread-pool executor."""
        loop = asyncio.get_event_loop()
        submitted = time.perf_counter()
        timing = _CALL_TIMING.get()

        def call():
            if timing is not None:
                timing["executor_queue_duration_ms"] = duration_ms(submitted)
            token = _CALL_TIMING.set(timing)
            try:
                return self._call_translate(text, source_language_code, target_language_code)
            finally:
                _CALL_TIMING.reset(token)

        translated = await loop.run_in_executor(
            None,
            call,
        )
        return translated

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def translate_segment(
        self,
        segment: Segment,
        session_id: str = "",
        source_language_code: str | None = None,
        target_language_code: str | None = None,
    ) -> Segment:
        """Translate *segment* and return a new :class:`Segment` with both
        ``text_vi`` and ``text_en`` populated.

        Translation directionality (CP-8 / Requirement 5.1):
        * ``spoken_language == "vi"`` → source in ``text_vi``, translate to
          ``text_en``.
        * ``spoken_language == "en"`` → source in ``text_en``, translate to
          ``text_vi``.

        On a Translate error the original segment is returned with only the
        source column populated and the error is recorded through the
        Logging_Service (Requirement 5.3).

        Parameters
        ----------
        segment:
            The Finalized_Segment to translate.  ``spoken_language`` must be
            ``"vi"`` or ``"en"``.
        session_id:
            The Session_ID of the active session, used for error logging.

        Returns
        -------
        Segment
            A new :class:`Segment` instance with ``text_vi`` and ``text_en``
            fields filled in.  The original segment is never mutated.
        """
        operation_started = _OPERATION_START.get()
        if operation_started is None:
            operation_started = time.perf_counter()
        telemetry = context(session_id)
        spoken = segment.spoken_language

        # Determine source/target languages and which field to write into.
        if spoken == "vi":
            source_text = segment.text_vi
            default_source_lang = "vi"
            default_target_lang = "en"
        else:  # spoken == "en"
            source_text = segment.text_en
            default_source_lang = "en"
            default_target_lang = "vi"

        source_lang = source_language_code or default_source_lang
        target_lang = target_language_code or default_target_lang
        log_fields = dict(segment_id=segment_id(segment.segment_id, telemetry.stream_mode, spoken),
                          direction=f"{source_lang}_to_{target_lang}", aggregate=False)

        # If the source text is empty there is nothing to translate; return
        # the segment as-is so we don't waste an API call.
        if not source_text.strip():
            telemetry.emit("translation_operation_completed", outcome="skipped_empty",
                           executor_queue_duration_ms=None, sdk_call_duration_ms=None, **log_fields)
            return segment.model_copy()

        timing: dict = {}
        timing_token = _CALL_TIMING.set(timing)
        try:
            translated_text = await self._translate_async(
                source_text, source_lang, target_lang
            )
        except asyncio.CancelledError as exc:
            telemetry.emit("translation_operation_completed", success=False, outcome="cancelled",
                           error=exc, duration_ms=duration_ms(operation_started),
                           executor_queue_duration_ms=timing.get("executor_queue_duration_ms"),
                           sdk_call_duration_ms=timing.get("sdk_call_duration_ms"), **log_fields)
            raise
        except (BotoCoreError, ClientError, Exception) as exc:  # noqa: BLE001
            telemetry.emit("translation_operation_completed", success=False, outcome="failed",
                           error=exc, duration_ms=duration_ms(operation_started),
                           executor_queue_duration_ms=timing.get("executor_queue_duration_ms"),
                           sdk_call_duration_ms=timing.get("sdk_call_duration_ms"), **log_fields)
            # On any Translate error: return segment without translated text
            # and record the error (Requirement 5.3).
            log_integration_error(
                session_id=session_id,
                service_name=_SERVICE_NAME,
                error=exc,
            )
            get_safe_logger(self._logger).warning(
                "Translation failed; returning source segment without translation",
                extra={
                    "session_id": session_id,
                    "spoken_language": spoken,
                    "source_language": source_lang,
                    "target_language": target_lang,
                    "error_type": type(exc).__name__,
                },
            )
            return segment.model_copy()
        finally:
            _CALL_TIMING.reset(timing_token)

        telemetry.emit("translation_operation_completed", success=bool(translated_text.strip()),
                       outcome="translated" if translated_text.strip() else "failed",
                       duration_ms=duration_ms(operation_started),
                       executor_queue_duration_ms=timing.get("executor_queue_duration_ms"),
                       sdk_call_duration_ms=timing.get("sdk_call_duration_ms"), **log_fields)

        # Build the translated segment with both columns populated.
        if spoken == "vi":
            return segment.model_copy(
                update={
                    "text_vi": source_text,
                    "text_en": translated_text,
                }
            )
        else:  # spoken == "en"
            return segment.model_copy(
                update={
                    "text_en": source_text,
                    "text_vi": translated_text,
                }
            )


# ---------------------------------------------------------------------------
# Module-level convenience function
# ---------------------------------------------------------------------------

# A module-level default service instance, created lazily so the boto3 client
# is only instantiated when the module is actually used (avoids import-time
# AWS credential checks in tests that mock this module).
_default_service: Optional[TranslationService] = None


def _get_default_service() -> TranslationService:
    global _default_service
    if _default_service is None:
        from app.config import get_settings  # local import to break import cycles

        settings = get_settings()
        _default_service = TranslationService(aws_region=settings.aws_region)
    return _default_service


async def translate_segment(
    segment: Segment,
    session_id: str = "",
    source_language_code: str | None = None,
    target_language_code: str | None = None,
) -> Segment:
    """Module-level convenience wrapper around :meth:`TranslationService.translate_segment`.

    Equivalent to calling ``TranslationService().translate_segment(...)``,
    but reuses a cached client for the lifetime of the process.

    Parameters
    ----------
    segment:
        The Finalized_Segment to translate.
    session_id:
        The active Session_ID, used for error logging.

    Returns
    -------
    Segment
        A new :class:`Segment` with both ``text_vi`` and ``text_en`` filled in,
        or the source segment unchanged if translation fails.
    """
    started = time.perf_counter()
    try:
        service = _get_default_service()
    except Exception as exc:
        telemetry = context(session_id)
        telemetry.emit("translation_operation_completed", success=False, outcome="failed", error=exc,
                       duration_ms=duration_ms(started), executor_queue_duration_ms=None,
                       sdk_call_duration_ms=None,
                       direction=f"{source_language_code or segment.spoken_language}_to_"
                                 f"{target_language_code or ('en' if segment.spoken_language == 'vi' else 'vi')}",
                       segment_id=segment_id(segment.segment_id, telemetry.stream_mode, segment.spoken_language))
        raise
    token = _OPERATION_START.set(started)
    try:
        return await service.translate_segment(
            segment,
            session_id=session_id,
            source_language_code=source_language_code,
            target_language_code=target_language_code,
        )
    finally:
        _OPERATION_START.reset(token)
