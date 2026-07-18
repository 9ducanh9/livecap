"""Storage_Service: Amazon S3 integration.

This module implements the Storage_Service from the design:
- Serialize a Transcript to TXT format
- Upload TXT files to Amazon S3
- Generate presigned download links with configurable expiration

Requirements satisfied:
- 7.1: TXT serialization with speaker labels, bilingual text, ordered by finalization
- 7.2: Ordered by finalization sequence
- 7.3: Handle empty-transcript case
- 8.1: Upload to configured S3 bucket
- 8.2: Unique object key with Session_ID
- 8.3: Abort on key assignment failure
- 8.4: Surface S3 upload errors
- 8.5: Return confirmation on success
- 9.1: Generate presigned download link
- 9.3: Configurable expiration
- 9.4: Grant access to file via download link
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import PurePosixPath
from typing import List

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.models import ExportSegment
from app.services.logging_service import log_integration_error

_logger = logging.getLogger(__name__)


class StorageError(Exception):
    """Base exception for storage service errors."""

    pass


class KeyAssignmentError(StorageError):
    """Raised when S3 object key assignment fails."""

    pass


class UploadError(StorageError):
    """Raised when S3 upload fails."""

    pass


@dataclass(frozen=True)
class StoredTranscript:
    """Export result including the private S3 key used for account history."""

    download_url: str
    expires_at: datetime
    object_key: str


def serialize_transcript_to_txt(
    segments: List[ExportSegment],
    summary_text: str | None = None,
) -> str:
    """Serialize a Transcript to TXT format.

    Format: One line per segment:
        [Speaker Label] VI: {text_vi} | EN: {text_en}

    Segments are ordered by finalization sequence (the order in the input list).
    The empty-transcript case (no segments) produces an empty string.

    When *summary_text* is provided (the optional AI meeting summary), it is
    prepended as a block above the transcript, separated by a blank line.

    Requirements:
    - 7.1: Serialize with speaker label, Vietnamese and English text
    - 7.2: Ordered by finalization sequence
    - 7.3: Handle empty-transcript case

    Parameters
    ----------
    segments:
        List of finalized segments in finalization order.
    summary_text:
        Optional plain-text meeting summary to prepend.

    Returns
    -------
    str
        The serialized TXT content.
    """
    if not segments:
        # Empty transcript case (Requirement 7.3)
        return ""

    lines = []
    for seg in segments:
        line = f"[{seg.speaker_label}] VI: {seg.text_vi} | EN: {seg.text_en}"
        lines.append(line)

    transcript = "\n".join(lines)
    if summary_text and summary_text.strip():
        return f"{summary_text.strip()}\n\n{transcript}"
    return transcript


def generate_s3_object_key(session_id: str, owner_id: str | None = None) -> str:
    """Generate a unique S3 object key for a transcript.

    Format: transcripts/{session_id}/{timestamp}.txt

    Requirements:
    - 8.2: Include Session_ID in key
    - 8.2: Ensure uniqueness within the bucket

    Parameters
    ----------
    session_id:
        The Session_ID for this transcript.

    Returns
    -------
    str
        The S3 object key.

    Raises
    ------
    KeyAssignmentError:
        If key generation fails (Requirement 8.3).
    """
    try:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
        if owner_id:
            # Cognito `sub` is a UUID, but retain only a conservative key
            # alphabet in case another identity provider is introduced later.
            safe_owner_id = "".join(
                character
                for character in owner_id
                if character.isalnum() or character in {"-", "_"}
            )
            if safe_owner_id:
                return f"transcripts/users/{safe_owner_id}/{session_id}/{timestamp}.txt"
        key = f"transcripts/{session_id}/{timestamp}.txt"
        return key
    except Exception as exc:
        raise KeyAssignmentError(
            f"Failed to generate S3 object key for session {session_id}"
        ) from exc


def upload_transcript_to_s3(
    bucket: str,
    key: str,
    content: str,
    session_id: str,
    region: str = "ap-southeast-1",
) -> None:
    """Upload a TXT transcript to S3.

    Requirements:
    - 8.1: Upload to configured bucket
    - 8.4: Raise error and record on upload failure

    Parameters
    ----------
    bucket:
        The S3 bucket name.
    key:
        The S3 object key.
    content:
        The TXT content to upload.
    session_id:
        The Session_ID (for error logging).
    region:
        AWS region.

    Raises
    ------
    UploadError:
        If the upload fails. The error is also recorded through the
        Logging_Service (Requirement 8.4).
    """
    try:
        s3_client = boto3.client("s3", region_name=region)
        s3_client.put_object(
            Bucket=bucket,
            Key=key,
            Body=content.encode("utf-8"),
            ContentType="text/plain; charset=utf-8",
        )
        _logger.info(
            "Uploaded transcript to S3",
            extra={
                "session_id": session_id,
                "bucket": bucket,
                "key": key,
            },
        )
    except (BotoCoreError, ClientError) as exc:
        error = UploadError(f"Failed to upload transcript to S3: {exc}")
        # Record the error through the Logging_Service (Requirement 8.4)
        log_integration_error(session_id, "Amazon S3", error)
        raise error from exc


def generate_presigned_download_link(
    bucket: str,
    key: str,
    expiration_seconds: int,
    region: str = "ap-southeast-1",
) -> str:
    """Generate a presigned download link for an S3 object.

    Requirements:
    - 9.1: Generate presigned download link
    - 9.3: Configurable expiration
    - 9.4: Grant access to file

    Parameters
    ----------
    bucket:
        The S3 bucket name.
    key:
        The S3 object key.
    expiration_seconds:
        Expiration time in seconds.
    region:
        AWS region.

    Returns
    -------
    str
        The presigned download URL.

    Raises
    ------
    StorageError:
        If presigned URL generation fails.
    """
    try:
        s3_client = boto3.client("s3", region_name=region)
        filename = PurePosixPath(key).name or "livecap-transcript.txt"
        url = s3_client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": bucket,
                "Key": key,
                "ResponseContentDisposition": f'attachment; filename="{filename}"',
                "ResponseContentType": "text/plain; charset=utf-8",
            },
            ExpiresIn=expiration_seconds,
        )
        return url
    except (BotoCoreError, ClientError) as exc:
        raise StorageError(
            f"Failed to generate presigned URL: {exc}"
        ) from exc


def store_transcript_and_get_download_link(
    session_id: str,
    segments: List[ExportSegment],
    bucket: str,
    expiration_seconds: int,
    region: str = "ap-southeast-1",
    summary_text: str | None = None,
) -> tuple[str, datetime]:
    """Complete storage workflow: serialize, upload, generate download link.

    This is the high-level function called by the export endpoint.

    Requirements:
    - All of 7.1-7.3, 8.1-8.5, 9.1-9.4

    Parameters
    ----------
    session_id:
        The Session_ID.
    segments:
        List of finalized segments in finalization order.
    bucket:
        The S3 bucket name.
    expiration_seconds:
        Download link expiration time in seconds.
    region:
        AWS region.

    Returns
    -------
    tuple[str, datetime]
        A tuple of (download_url, expires_at).

    Raises
    ------
    KeyAssignmentError:
        If object key generation fails (Requirement 8.3).
    UploadError:
        If S3 upload fails (Requirement 8.4).
    StorageError:
        If presigned URL generation fails.
    """
    stored = store_transcript(
        session_id=session_id,
        segments=segments,
        bucket=bucket,
        expiration_seconds=expiration_seconds,
        region=region,
        summary_text=summary_text,
    )
    return stored.download_url, stored.expires_at


def store_transcript(
    session_id: str,
    segments: List[ExportSegment],
    bucket: str,
    expiration_seconds: int,
    region: str = "ap-southeast-1",
    summary_text: str | None = None,
    owner_id: str | None = None,
) -> StoredTranscript:
    """Store an export and retain its key for optional owner history metadata."""
    # Serialize the transcript (Requirements 7.1, 7.2, 7.3)
    txt_content = serialize_transcript_to_txt(segments, summary_text=summary_text)

    # Generate unique S3 object key (Requirements 8.2, 8.3)
    try:
        object_key = generate_s3_object_key(session_id, owner_id=owner_id)
    except KeyAssignmentError:
        # Abort the upload (Requirement 8.3)
        raise

    # Upload to S3 (Requirements 8.1, 8.4)
    upload_transcript_to_s3(
        bucket=bucket,
        key=object_key,
        content=txt_content,
        session_id=session_id,
        region=region,
    )

    # Generate presigned download link (Requirements 9.1, 9.3, 9.4)
    download_url = generate_presigned_download_link(
        bucket=bucket,
        key=object_key,
        expiration_seconds=expiration_seconds,
        region=region,
    )

    # Calculate expiration timestamp
    expires_at = datetime.now(timezone.utc) + timedelta(
        seconds=expiration_seconds
    )

    return StoredTranscript(
        download_url=download_url,
        expires_at=expires_at,
        object_key=object_key,
    )
