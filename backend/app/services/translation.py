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
import logging
from typing import Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.models import Segment
from app.services.logging_service import get_logger, log_integration_error

# Human-readable service name used in log records (Requirement 10.3).
_SERVICE_NAME = "Amazon Translate"


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
        ``"us-east-1"``.
    """

    def __init__(self, aws_region: str = "us-east-1") -> None:
        self._region = aws_region
        self._client = boto3.client("translate", region_name=aws_region)
        self._logger: logging.Logger = get_logger()

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
        response = self._client.translate_text(
            Text=text,
            SourceLanguageCode=source_language_code,
            TargetLanguageCode=target_language_code,
        )
        return response["TranslatedText"]

    async def _translate_async(
        self,
        text: str,
        source_language_code: str,
        target_language_code: str,
    ) -> str:
        """Run the blocking boto3 call in the default thread-pool executor."""
        loop = asyncio.get_event_loop()
        translated = await loop.run_in_executor(
            None,
            self._call_translate,
            text,
            source_language_code,
            target_language_code,
        )
        return translated

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def translate_segment(
        self,
        segment: Segment,
        session_id: str = "",
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
        spoken = segment.spoken_language

        # Determine source/target languages and which field to write into.
        if spoken == "vi":
            source_text = segment.text_vi
            source_lang = "vi"
            target_lang = "en"
        else:  # spoken == "en"
            source_text = segment.text_en
            source_lang = "en"
            target_lang = "vi"

        # If the source text is empty there is nothing to translate; return
        # the segment as-is so we don't waste an API call.
        if not source_text.strip():
            return segment.model_copy()

        try:
            translated_text = await self._translate_async(
                source_text, source_lang, target_lang
            )
        except (BotoCoreError, ClientError, Exception) as exc:  # noqa: BLE001
            # On any Translate error: return segment without translated text
            # and record the error (Requirement 5.3).
            log_integration_error(
                session_id=session_id,
                service_name=_SERVICE_NAME,
                error=exc,
            )
            self._logger.warning(
                "Translation failed; returning source segment without translation",
                extra={
                    "session_id": session_id,
                    "spoken_language": spoken,
                    "source_language": source_lang,
                    "target_language": target_lang,
                    "error": str(exc),
                },
            )
            return segment.model_copy()

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
    service = _get_default_service()
    return await service.translate_segment(segment, session_id=session_id)
