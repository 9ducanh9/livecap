"""Export router: ``POST /api/sessions/{session_id}/export``.

Implements the transcript export REST endpoint.  The endpoint:

1. Validates that at least one segment was provided (400 if not).
2. Delegates to the Storage_Service to serialize, upload, and generate a
   presigned download link.
3. Returns the download URL and its expiration time on success (200).
4. Returns a 500 with an error detail if the Storage_Service raises any error.

Requirements satisfied:
- 7.1: Serialize the Transcript to TXT format
- 7.2: Ordered by finalization sequence
- 7.3: Handle empty-transcript case (validated before reaching Storage_Service)
- 8.3: Abort on key assignment failure → 500
- 8.4: Surface S3 upload errors → 500
- 8.5: Return confirmation on success
- 9.2: Send the Download_Link back to the Frontend
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Path

from app.config import get_settings
from app.models import ExportRequest, ExportResponse
from app.services.auth import AuthenticatedUser, optional_authenticated_user
from app.services.storage import (
    StorageError,
    store_transcript,
    store_transcript_and_get_download_link,
)
from app.services.transcript_history import TranscriptHistoryError, save_history_record

_logger = logging.getLogger("livecap")

router = APIRouter()


@router.post(
    "/api/sessions/{session_id}/export",
    response_model=ExportResponse,
    summary="Export and store a session transcript",
    responses={
        200: {"description": "Transcript stored; download link returned."},
        400: {"description": "No segments provided."},
        500: {"description": "Failed to upload transcript to S3."},
    },
)
async def export_transcript(
    session_id: str = Path(..., description="The Session_ID for this transcript"),
    body: ExportRequest = ...,
    user: AuthenticatedUser | None = Depends(optional_authenticated_user),
) -> ExportResponse:
    """Export a transcript to S3 and return a time-limited download link.

    Accepts the ordered list of finalized segments from the Frontend,
    serializes them to TXT, uploads the file to S3, and returns the
    presigned download URL together with its expiration timestamp.

    Returns
    -------
    ExportResponse
        ``{ download_url, expires_at }`` on success.

    Raises
    ------
    HTTPException 400
        When ``segments`` is empty (Requirement 7.3 / design spec).
    HTTPException 500
        When the Storage_Service fails for any reason (Requirements 8.3, 8.4).
    """
    # --- 400: no segments provided ----------------------------------------
    if not body.segments:
        raise HTTPException(status_code=400, detail="No segments provided")

    settings = get_settings()

    # --- Invoke Storage_Service -------------------------------------------
    try:
        if user is None:
            download_url, expires_at = store_transcript_and_get_download_link(
                session_id=session_id,
                segments=body.segments,
                bucket=settings.s3_bucket,
                expiration_seconds=settings.download_link_expiration,
                region=settings.aws_region,
                summary_text=body.summary_text,
            )
        else:
            stored = store_transcript(
                session_id=session_id,
                segments=body.segments,
                bucket=settings.s3_bucket,
                expiration_seconds=settings.download_link_expiration,
                region=settings.aws_region,
                summary_text=body.summary_text,
                owner_id=user.user_id,
            )
    except StorageError as exc:
        _logger.error(
            "export_failed",
            extra={
                "event": "export_failed",
                "session_id": session_id,
                "error": str(exc),
            },
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to upload transcript to S3",
        ) from exc

    # --- 200: return storage confirmation and Download_Link ---------------
    if user is not None:
        try:
            save_history_record(
                table_name=settings.transcript_history_table_name,
                region=settings.aws_region,
                user_id=user.user_id,
                session_id=session_id,
                s3_key=stored.object_key,
                segment_count=len(body.segments),
                retention_days=settings.transcript_history_retention_days,
            )
        except TranscriptHistoryError as exc:
            # The export succeeded but without its metadata the user could not
            # find it later, so surface a retryable failure instead of claiming
            # success.
            _logger.error("transcript_history_save_failed", exc_info=exc)
            raise HTTPException(
                status_code=500,
                detail="Transcript was stored but its history record could not be saved",
            ) from exc

        return ExportResponse(download_url=stored.download_url, expires_at=stored.expires_at)
    return ExportResponse(download_url=download_url, expires_at=expires_at)
