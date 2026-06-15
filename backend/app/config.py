"""Application configuration for the LiveCap backend.

Configuration is loaded from environment variables (optionally sourced from a
local ``.env`` file via ``python-dotenv``). Sensible defaults are provided for
local development; production values are supplied through the environment.

See ``.env.example`` for the full list of supported variables.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv

# Load variables from a local .env file if present. Real environment variables
# always take precedence over values defined in the file.
load_dotenv()


# --- Defaults -------------------------------------------------------------

DEFAULT_AWS_REGION = "ap-southeast-1"
DEFAULT_S3_BUCKET = "livecap-transcripts"
# 24 hours, in seconds.
DEFAULT_DOWNLOAD_LINK_EXPIRATION = 86_400
# 30 minutes, in seconds.
DEFAULT_SESSION_TIMEOUT = 1_800
DEFAULT_MAX_SPEAKERS = 5
DEFAULT_TRANSCRIBE_LANGUAGE_CODE = "vi-VN"
DEFAULT_BILINGUAL_DUAL_STREAM = True
DEFAULT_AUDIO_PIPELINE_DEBUG = False
DEFAULT_ALLOWED_ORIGIN = "http://localhost:5173"
DEFAULT_CLOUDWATCH_LOG_GROUP = "livecap"
DEFAULT_MAX_CONCURRENT_SESSIONS = 4
DEFAULT_MAX_SESSIONS_PER_IP = 1
DEFAULT_ENABLE_IDLE_SCALE_DOWN = False
DEFAULT_IDLE_SCALE_DOWN_GRACE_SECONDS = 300


def _get_int(name: str, default: int) -> int:
    """Read an integer environment variable, falling back to ``default``.

    An empty or unparseable value falls back to the default rather than raising,
    keeping the service resilient to misconfiguration in development.
    """

    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _get_str(name: str, default: str) -> str:
    """Read a string environment variable, falling back to ``default``."""

    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip()


def _get_bool(name: str, default: bool) -> bool:
    """Read a boolean environment variable, falling back to ``default``."""

    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    """Resolved application configuration.

    Attributes:
        aws_region: AWS region for Transcribe, Translate, and S3.
        s3_bucket: S3 bucket where exported transcripts are stored.
        download_link_expiration: Lifetime (seconds) of presigned download links.
        session_timeout: Maximum session duration (seconds) before timeout.
        max_speakers: Maximum number of speakers for Transcribe diarization.
        transcribe_language_code: Fixed Transcribe Streaming language code.
        bilingual_dual_stream: Enables parallel vi-VN and en-US Transcribe streams.
        audio_pipeline_debug: Enables temporary audio flow debug logging.
        allowed_origin: The single frontend origin permitted by CORS.
        cloudwatch_log_group: CloudWatch log group for the Logging_Service.
        max_concurrent_sessions: Process-local active WebSocket session limit.
        max_sessions_per_ip: Process-local active WebSocket session limit per IP.
        enable_idle_scale_down: Enables delayed ECS scale-to-zero after idle.
        idle_scale_down_grace_seconds: Delay before scaling ECS desired count to 0.
        ecs_cluster_name: ECS cluster name used by idle scale-down.
        ecs_service_name: ECS service name used by idle scale-down.
    """

    aws_region: str = DEFAULT_AWS_REGION
    s3_bucket: str = DEFAULT_S3_BUCKET
    download_link_expiration: int = DEFAULT_DOWNLOAD_LINK_EXPIRATION
    session_timeout: int = DEFAULT_SESSION_TIMEOUT
    max_speakers: int = DEFAULT_MAX_SPEAKERS
    transcribe_language_code: str = DEFAULT_TRANSCRIBE_LANGUAGE_CODE
    bilingual_dual_stream: bool = DEFAULT_BILINGUAL_DUAL_STREAM
    audio_pipeline_debug: bool = DEFAULT_AUDIO_PIPELINE_DEBUG
    allowed_origin: str = DEFAULT_ALLOWED_ORIGIN
    cloudwatch_log_group: str = DEFAULT_CLOUDWATCH_LOG_GROUP
    max_concurrent_sessions: int = DEFAULT_MAX_CONCURRENT_SESSIONS
    max_sessions_per_ip: int = DEFAULT_MAX_SESSIONS_PER_IP
    enable_idle_scale_down: bool = DEFAULT_ENABLE_IDLE_SCALE_DOWN
    idle_scale_down_grace_seconds: int = DEFAULT_IDLE_SCALE_DOWN_GRACE_SECONDS
    ecs_cluster_name: str = ""
    ecs_service_name: str = ""

    @classmethod
    def from_env(cls) -> "Settings":
        """Build a ``Settings`` instance from the current environment."""
        max_concurrent_sessions = max(
            0,
            _get_int("MAX_CONCURRENT_SESSIONS", DEFAULT_MAX_CONCURRENT_SESSIONS),
        )
        max_sessions_per_ip = max(
            0,
            _get_int("MAX_SESSIONS_PER_IP", DEFAULT_MAX_SESSIONS_PER_IP),
        )

        return cls(
            aws_region=_get_str("AWS_REGION", DEFAULT_AWS_REGION),
            s3_bucket=_get_str("S3_BUCKET", DEFAULT_S3_BUCKET),
            download_link_expiration=_get_int(
                "DOWNLOAD_LINK_EXPIRATION", DEFAULT_DOWNLOAD_LINK_EXPIRATION
            ),
            session_timeout=_get_int("SESSION_TIMEOUT", DEFAULT_SESSION_TIMEOUT),
            max_speakers=_get_int("MAX_SPEAKERS", DEFAULT_MAX_SPEAKERS),
            transcribe_language_code=_get_str(
                "TRANSCRIBE_LANGUAGE_CODE", DEFAULT_TRANSCRIBE_LANGUAGE_CODE
            ),
            bilingual_dual_stream=_get_bool(
                "BILINGUAL_DUAL_STREAM", DEFAULT_BILINGUAL_DUAL_STREAM
            ),
            audio_pipeline_debug=_get_bool(
                "AUDIO_PIPELINE_DEBUG", DEFAULT_AUDIO_PIPELINE_DEBUG
            ),
            allowed_origin=_get_str("ALLOWED_ORIGIN", DEFAULT_ALLOWED_ORIGIN),
            cloudwatch_log_group=_get_str(
                "CLOUDWATCH_LOG_GROUP", DEFAULT_CLOUDWATCH_LOG_GROUP
            ),
            max_concurrent_sessions=max_concurrent_sessions,
            max_sessions_per_ip=max_sessions_per_ip,
            enable_idle_scale_down=_get_bool(
                "ENABLE_IDLE_SCALE_DOWN", DEFAULT_ENABLE_IDLE_SCALE_DOWN
            ),
            idle_scale_down_grace_seconds=max(
                0,
                _get_int(
                    "IDLE_SCALE_DOWN_GRACE_SECONDS",
                    DEFAULT_IDLE_SCALE_DOWN_GRACE_SECONDS,
                ),
            ),
            ecs_cluster_name=_get_str("ECS_CLUSTER_NAME", ""),
            ecs_service_name=_get_str("ECS_SERVICE_NAME", ""),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached application settings.

    Cached so configuration is read from the environment only once per process.
    """

    return Settings.from_env()
