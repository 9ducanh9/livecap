"""Logging_Service: structured logging with Amazon CloudWatch.

Configures the Python ``logging`` module with a ``watchtower`` CloudWatch
handler and a structured JSON formatter.  When CloudWatch is unavailable
(e.g. in local development), the service falls back to a plain stdout
handler so the application remains fully functional without AWS access.

Public helpers
--------------
setup_logging()
    Call once at application startup.  Configures the root logger (or a
    named logger) for the rest of the process lifetime.

log_session_start(session_id)
    Record a session-start event (Requirement 10.1).

log_session_end(session_id)
    Record a session-end event (Requirement 10.2).

log_integration_error(session_id, service_name, error)
    Record an error from Transcribe Streaming, Translate, or S3
    (Requirement 10.3).

get_logger()
    Return the shared module-level logger for general-purpose use.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import traceback
from datetime import datetime, timezone
from typing import Any

# ---------------------------------------------------------------------------
# Logger name used throughout the application.
# ---------------------------------------------------------------------------

LOGGER_NAME = "livecap"

_logger: logging.Logger = logging.getLogger(LOGGER_NAME)

# ---------------------------------------------------------------------------
# Structured JSON formatter
# ---------------------------------------------------------------------------


class _JsonFormatter(logging.Formatter):
    """Emit every log record as a single-line JSON object.

    The record always includes ``timestamp``, ``level``, ``logger``,
    ``message``, and any extra keyword arguments passed via the ``extra``
    parameter of the logging call.
    """

    def format(self, record: logging.LogRecord) -> str:  # noqa: A003
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Attach any extra fields that callers pass via the ``extra`` kwarg.
        for key, value in record.__dict__.items():
            if key not in (
                "args",
                "created",
                "exc_info",
                "exc_text",
                "filename",
                "funcName",
                "levelname",
                "levelno",
                "lineno",
                "message",
                "module",
                "msecs",
                "msg",
                "name",
                "pathname",
                "process",
                "processName",
                "relativeCreated",
                "stack_info",
                "taskName",
                "thread",
                "threadName",
            ):
                payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------


def setup_logging(
    *,
    log_level: int = logging.INFO,
    log_group: str | None = None,
    log_stream: str | None = None,
    aws_region: str | None = None,
) -> None:
    """Configure the application logger.

    Attempts to attach a ``watchtower`` CloudWatch handler.  If that fails
    for any reason (missing credentials, network unreachable, etc.) a
    ``StreamHandler`` writing to ``stdout`` is used instead so the service
    works normally in development.

    Parameters
    ----------
    log_level:
        Minimum severity level (default: ``logging.INFO``).
    log_group:
        CloudWatch log group name.  Falls back to the ``CLOUDWATCH_LOG_GROUP``
        environment variable, then to ``"livecap"``.
    log_stream:
        CloudWatch log stream name.  Falls back to the
        ``CLOUDWATCH_LOG_STREAM`` environment variable, then to
        ``"livecap-stream"``.
    aws_region:
        AWS region for CloudWatch.  Falls back to the ``AWS_REGION``
        environment variable, then to ``"ap-southeast-1"``.
    """

    resolved_group = (
        log_group
        or os.getenv("CLOUDWATCH_LOG_GROUP")
        or "livecap"
    )
    resolved_stream = (
        log_stream
        or os.getenv("CLOUDWATCH_LOG_STREAM")
        or "livecap-stream"
    )
    resolved_region = (
        aws_region
        or os.getenv("AWS_REGION")
        or "ap-southeast-1"
    )

    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(log_level)

    # Avoid duplicate handlers when setup_logging() is called more than once.
    if logger.handlers:
        return

    formatter = _JsonFormatter()
    handler: logging.Handler

    try:
        import boto3  # noqa: PLC0415  (local import to isolate import-time failures)
        import watchtower  # noqa: PLC0415

        cw_client = boto3.client("logs", region_name=resolved_region)
        handler = watchtower.CloudWatchLogHandler(
            log_group_name=resolved_group,
            log_stream_name=resolved_stream,
            boto3_client=cw_client,
            create_log_group=True,
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.info(
            "CloudWatch logging initialised",
            extra={
                "log_group": resolved_group,
                "log_stream": resolved_stream,
                "aws_region": resolved_region,
            },
        )
    except Exception as exc:  # noqa: BLE001
        # Fall back to stdout — this keeps the service usable in development
        # environments where AWS credentials or network access may not be
        # available.
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.warning(
            "CloudWatch handler unavailable; falling back to stdout logging",
            extra={"reason": str(exc)},
        )


# ---------------------------------------------------------------------------
# Public event helpers
# ---------------------------------------------------------------------------


def log_session_start(session_id: str) -> None:
    """Record a session-start event keyed by *session_id*.

    Satisfies Requirement 10.1: WHEN a Session starts, THE Backend SHALL
    record a session-start event associated with the Session_ID through the
    Logging_Service.
    """
    _logger.info(
        "session_start",
        extra={"event": "session_start", "session_id": session_id},
    )


def log_session_end(session_id: str) -> None:
    """Record a session-end event keyed by *session_id*.

    Satisfies Requirement 10.2: WHEN a Session ends, THE Backend SHALL record
    a session-end event associated with the Session_ID through the
    Logging_Service.
    """
    _logger.info(
        "session_end",
        extra={"event": "session_end", "session_id": session_id},
    )


def log_integration_error(
    session_id: str,
    service_name: str,
    error: Exception,
) -> None:
    """Record an integration error from *service_name* for *session_id*.

    Satisfies Requirement 10.3: IF an integration with Amazon Transcribe
    Streaming, Amazon Translate, or Amazon S3 returns an error, THEN THE
    Backend SHALL record the error associated with the Session_ID through the
    Logging_Service with the name of the affected service.

    Parameters
    ----------
    session_id:
        The active Session_ID at the time of the error.
    service_name:
        Human-readable name of the failing integration, e.g.
        ``"Amazon Transcribe Streaming"``, ``"Amazon Translate"``,
        or ``"Amazon S3"``.
    error:
        The exception that was raised.
    """
    _logger.error(
        "integration_error",
        extra={
            "event": "integration_error",
            "session_id": session_id,
            "service_name": service_name,
            "error_type": type(error).__name__,
            "error_message": str(error),
            "traceback": traceback.format_exc(),
        },
    )


def log_websocket_connect(session_id: str) -> None:
    """Record a WebSocket connection event.

    Convenience helper for the WebSocket handler (design: Logging_Service
    responsibility includes WebSocket connection/disconnection events).
    """
    _logger.info(
        "websocket_connect",
        extra={"event": "websocket_connect", "session_id": session_id},
    )


def log_websocket_disconnect(session_id: str) -> None:
    """Record a WebSocket disconnection event."""
    _logger.info(
        "websocket_disconnect",
        extra={"event": "websocket_disconnect", "session_id": session_id},
    )


# ---------------------------------------------------------------------------
# General-purpose logger accessor
# ---------------------------------------------------------------------------


def get_logger() -> logging.Logger:
    """Return the shared application logger.

    Other modules can call ``get_logger()`` to obtain the same logger
    instance configured by ``setup_logging()``, ensuring consistent
    formatting and handler configuration across the whole application.
    """
    return _logger
