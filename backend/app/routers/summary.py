"""On-demand Amazon Bedrock meeting-summary endpoint.

The browser calls this endpoint only after a user has stopped a session and
explicitly requested meeting notes. Finalized captions are supplied in the
request and are not retained by this router.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Path

from app.config import get_settings
from app.models import FinalizedSegmentMessage, SessionSummary, SummaryRequest
from app.services.summarization import summarize_session

router = APIRouter()


@router.post(
    "/api/sessions/{session_id}/summary",
    response_model=SessionSummary,
    summary="Generate on-demand AI meeting notes",
    responses={
        400: {"description": "Not enough finalized captions were provided."},
        409: {"description": "Meeting summaries are disabled."},
        502: {"description": "Amazon Bedrock did not return a usable summary."},
    },
)
async def generate_summary(
    session_id: str = Path(..., description="The Session_ID for these captions"),
    body: SummaryRequest = ...,
) -> SessionSummary:
    """Generate AI notes for finalized captions when explicitly requested."""

    settings = get_settings()
    if not settings.enable_meeting_summary:
        raise HTTPException(status_code=409, detail="AI meeting notes are not enabled")
    if len(body.segments) < settings.summary_min_segments:
        raise HTTPException(
            status_code=400,
            detail=(
                "At least "
                f"{settings.summary_min_segments} finalized captions are required"
            ),
        )

    segments = [
        FinalizedSegmentMessage(
            segment_id=segment.segment_id,
            speaker_label=segment.speaker_label,
            text_vi=segment.text_vi,
            text_en=segment.text_en,
            spoken_language=segment.spoken_language,
            timestamp_start=segment.timestamp_start,
            timestamp_end=segment.timestamp_end,
        )
        for segment in body.segments
    ]
    summary = await summarize_session(
        session_id=session_id,
        segments=segments,
        settings=settings,
    )
    if summary is None:
        raise HTTPException(
            status_code=502,
            detail="AI meeting notes could not be generated. Please try again.",
        )
    return summary
