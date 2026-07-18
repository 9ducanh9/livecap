"""Authenticated transcript-history API.

Only metadata is returned from DynamoDB. Each download is re-authorized for
the Cognito owner and receives a short-lived S3 presigned URL.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Path, Query

from app.config import get_settings
from app.models import (
    TranscriptDownloadResponse,
    TranscriptHistoryItem,
    TranscriptHistoryResponse,
)
from app.services.auth import AuthenticatedUser, require_authenticated_user
from app.services.storage import StorageError, generate_presigned_download_link
from app.services.transcript_history import (
    TranscriptHistoryError,
    get_history_record,
    list_history_records,
)

router = APIRouter(prefix="/api/transcripts", tags=["transcript history"])


@router.get("", response_model=TranscriptHistoryResponse)
async def list_transcript_history(
    limit: int = Query(default=20, ge=1, le=100),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> TranscriptHistoryResponse:
    settings = get_settings()
    try:
        records = list_history_records(
            table_name=settings.transcript_history_table_name,
            region=settings.aws_region,
            user_id=user.user_id,
            limit=limit,
        )
    except TranscriptHistoryError as exc:
        raise HTTPException(status_code=500, detail="Transcript history is unavailable") from exc
    return TranscriptHistoryResponse(
        items=[
            TranscriptHistoryItem(
                history_id=record.history_id,
                session_id=record.session_id,
                created_at=record.created_at,
                segment_count=record.segment_count,
            )
            for record in records
        ]
    )


@router.get("/{history_id}/download", response_model=TranscriptDownloadResponse)
async def download_history_transcript(
    history_id: str = Path(..., min_length=1),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> TranscriptDownloadResponse:
    settings = get_settings()
    try:
        record = get_history_record(
            table_name=settings.transcript_history_table_name,
            region=settings.aws_region,
            user_id=user.user_id,
            history_id=history_id,
        )
    except TranscriptHistoryError as exc:
        raise HTTPException(status_code=500, detail="Transcript history is unavailable") from exc
    if record is None:
        raise HTTPException(status_code=404, detail="Transcript was not found")
    try:
        url = generate_presigned_download_link(
            bucket=settings.s3_bucket,
            key=record.s3_key,
            expiration_seconds=settings.download_link_expiration,
            region=settings.aws_region,
        )
    except StorageError as exc:
        raise HTTPException(status_code=500, detail="Transcript download is unavailable") from exc
    return TranscriptDownloadResponse(
        download_url=url,
        expires_at=datetime.now(timezone.utc)
        + timedelta(seconds=settings.download_link_expiration),
    )
