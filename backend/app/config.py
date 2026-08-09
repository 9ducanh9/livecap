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
DEFAULT_TRANSCRIBE_LANGUAGE_CODE = "vi-VN"
DEFAULT_BILINGUAL_DUAL_STREAM = True
DEFAULT_AUDIO_PIPELINE_DEBUG = False
DEFAULT_ALLOWED_ORIGIN = "http://localhost:5173"
DEFAULT_CLOUDWATCH_LOG_GROUP = "livecap"
DEFAULT_MAX_CONCURRENT_SESSIONS = 4
DEFAULT_MAX_SESSIONS_PER_IP = 1
DEFAULT_ENABLE_IDLE_SCALE_DOWN = False
DEFAULT_IDLE_SCALE_DOWN_GRACE_SECONDS = 300
# Meeting summary (DeepSeek). Disabled by default so the feature is strictly
# opt-in and never adds cost unless explicitly enabled. Previously called
# Anthropic-on-Bedrock, but every Anthropic model quota in this account's
# Bedrock region was 0 (confirmed with a real InvokeModel call -- not a code
# bug, just unapproved AWS quota), so the feature never actually worked.
# Switched to DeepSeek's OpenAI-compatible API, which needs its own key
# rather than AWS credentials already on the task role.
DEFAULT_ENABLE_MEETING_SUMMARY = False
DEFAULT_DEEPSEEK_MODEL = "deepseek-chat"
# Minimum finalized segments before a summary is worth generating.
DEFAULT_SUMMARY_MIN_SEGMENTS = 3
# Upper bound on transcript characters sent to the model (cost/latency guard).
DEFAULT_SUMMARY_MAX_INPUT_CHARS = 12_000
# Wall-clock budget for one user-requested summary call.
DEFAULT_SUMMARY_TIMEOUT_SECONDS = 20
# Session registry backend. "memory" is process-local (single task). "dynamodb"
# shares the active-session limits across tasks, unblocking horizontal scaling.
DEFAULT_SESSION_STORE_BACKEND = "memory"
DEFAULT_SESSION_TABLE_NAME = "livecap-sessions"
# TTL for session items; a safety net that reclaims rows from crashed tasks.
# Keep it comfortably above the session timeout.
DEFAULT_SESSION_TTL_SECONDS = 3_600
# Product accounts and transcript history are deliberately opt-in. Existing
# workshop/demo deployments remain anonymous until Cognito is provisioned.
DEFAULT_ENABLE_AUTH = False
DEFAULT_COGNITO_USER_POOL_ID = ""
DEFAULT_TRANSCRIPT_HISTORY_TABLE_NAME = "livecap-transcript-history"
DEFAULT_TRANSCRIPT_HISTORY_RETENTION_DAYS = 14
# Stripe subscription billing for the Pro/Business tiers. Off by default; the
# usage_quota table always defaults new users to the free tier until a Stripe
# webhook says otherwise (see app.services.stripe_billing).
DEFAULT_ENABLE_STRIPE_BILLING = False
DEFAULT_STRIPE_PRICE_ID_PRO = ""
DEFAULT_STRIPE_PRICE_ID_BUSINESS = ""
DEFAULT_FRONTEND_BASE_URL = "http://localhost:5173"


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
        transcribe_language_code: Fixed Transcribe Streaming language code.
        bilingual_dual_stream: Enables parallel vi-VN and en-US Transcribe streams.
        audio_pipeline_debug: Enables temporary audio flow debug logging.
        allowed_origin: Comma-separated frontend origins permitted by CORS.
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
    enable_meeting_summary: bool = DEFAULT_ENABLE_MEETING_SUMMARY
    deepseek_api_key: str = ""
    deepseek_model: str = DEFAULT_DEEPSEEK_MODEL
    summary_min_segments: int = DEFAULT_SUMMARY_MIN_SEGMENTS
    summary_max_input_chars: int = DEFAULT_SUMMARY_MAX_INPUT_CHARS
    summary_timeout_seconds: int = DEFAULT_SUMMARY_TIMEOUT_SECONDS
    session_store_backend: str = DEFAULT_SESSION_STORE_BACKEND
    session_table_name: str = DEFAULT_SESSION_TABLE_NAME
    session_ttl_seconds: int = DEFAULT_SESSION_TTL_SECONDS
    enable_auth: bool = DEFAULT_ENABLE_AUTH
    cognito_user_pool_id: str = DEFAULT_COGNITO_USER_POOL_ID
    transcript_history_table_name: str = DEFAULT_TRANSCRIPT_HISTORY_TABLE_NAME
    transcript_history_retention_days: int = DEFAULT_TRANSCRIPT_HISTORY_RETENTION_DAYS
    enable_stripe_billing: bool = DEFAULT_ENABLE_STRIPE_BILLING
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_id_pro: str = DEFAULT_STRIPE_PRICE_ID_PRO
    stripe_price_id_business: str = DEFAULT_STRIPE_PRICE_ID_BUSINESS
    frontend_base_url: str = DEFAULT_FRONTEND_BASE_URL

    @property
    def allowed_origins(self) -> tuple[str, ...]:
        """Return the configured CORS origins without blanks or duplicates."""
        origins = dict.fromkeys(
            origin.strip()
            for origin in self.allowed_origin.split(",")
            if origin.strip()
        )
        return tuple(origins) or (DEFAULT_ALLOWED_ORIGIN,)

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
            enable_meeting_summary=_get_bool(
                "ENABLE_MEETING_SUMMARY", DEFAULT_ENABLE_MEETING_SUMMARY
            ),
            deepseek_api_key=_get_str("DEEPSEEK_API_KEY", ""),
            deepseek_model=_get_str("DEEPSEEK_MODEL", DEFAULT_DEEPSEEK_MODEL),
            summary_min_segments=max(
                1, _get_int("SUMMARY_MIN_SEGMENTS", DEFAULT_SUMMARY_MIN_SEGMENTS)
            ),
            summary_max_input_chars=max(
                500,
                _get_int(
                    "SUMMARY_MAX_INPUT_CHARS", DEFAULT_SUMMARY_MAX_INPUT_CHARS
                ),
            ),
            summary_timeout_seconds=max(
                1,
                _get_int(
                    "SUMMARY_TIMEOUT_SECONDS", DEFAULT_SUMMARY_TIMEOUT_SECONDS
                ),
            ),
            session_store_backend=_get_str(
                "SESSION_STORE_BACKEND", DEFAULT_SESSION_STORE_BACKEND
            ).strip().lower(),
            session_table_name=_get_str(
                "SESSION_TABLE_NAME", DEFAULT_SESSION_TABLE_NAME
            ),
            session_ttl_seconds=max(
                60, _get_int("SESSION_TTL_SECONDS", DEFAULT_SESSION_TTL_SECONDS)
            ),
            enable_auth=_get_bool("ENABLE_AUTH", DEFAULT_ENABLE_AUTH),
            cognito_user_pool_id=_get_str(
                "COGNITO_USER_POOL_ID", DEFAULT_COGNITO_USER_POOL_ID
            ),
            transcript_history_table_name=_get_str(
                "TRANSCRIPT_HISTORY_TABLE_NAME",
                DEFAULT_TRANSCRIPT_HISTORY_TABLE_NAME,
            ),
            transcript_history_retention_days=max(
                1,
                _get_int(
                    "TRANSCRIPT_HISTORY_RETENTION_DAYS",
                    DEFAULT_TRANSCRIPT_HISTORY_RETENTION_DAYS,
                ),
            ),
            enable_stripe_billing=_get_bool(
                "ENABLE_STRIPE_BILLING", DEFAULT_ENABLE_STRIPE_BILLING
            ),
            stripe_secret_key=_get_str("STRIPE_SECRET_KEY", ""),
            stripe_webhook_secret=_get_str("STRIPE_WEBHOOK_SECRET", ""),
            stripe_price_id_pro=_get_str(
                "STRIPE_PRICE_ID_PRO", DEFAULT_STRIPE_PRICE_ID_PRO
            ),
            stripe_price_id_business=_get_str(
                "STRIPE_PRICE_ID_BUSINESS", DEFAULT_STRIPE_PRICE_ID_BUSINESS
            ),
            frontend_base_url=_get_str(
                "FRONTEND_BASE_URL", DEFAULT_FRONTEND_BASE_URL
            ),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached application settings.

    Cached so configuration is read from the environment only once per process.
    """

    return Settings.from_env()
