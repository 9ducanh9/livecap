"""Optional AWS X-Ray tracing (C4). Default OFF via ``ENABLE_XRAY``.

When enabled it:

* patches the AWS SDK (``patch_all``) so Transcribe / Translate / S3 / Bedrock /
  Polly / Comprehend / DynamoDB calls appear as subsegments, and
* wraps **HTTP** requests in an X-Ray segment via a small Starlette middleware.

The WebSocket route is intentionally not traced: Starlette's ``BaseHTTPMiddleware``
runs for HTTP scopes only, so ``/ws/transcribe`` is untouched, and
``context_missing="IGNORE"`` means AWS SDK calls made during a WebSocket session
(outside any request segment) never raise.

Requires an X-Ray daemon reachable at ``AWS_XRAY_DAEMON_ADDRESS`` (a sidecar in
the same task; default ``127.0.0.1:2000``). Everything is best-effort: if the
SDK is missing or configuration fails, tracing is disabled and the app runs
normally.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from app.services.logging_service import get_logger


def xray_enabled() -> bool:
    """True when tracing is switched on via the ``ENABLE_XRAY`` env var."""
    return os.getenv("ENABLE_XRAY", "").strip().lower() in {"1", "true", "yes", "on"}


def _build_http_middleware(recorder: Any, service_name: str):
    """Build a Starlette HTTP middleware class bound to *recorder*.

    Defined lazily so importing this module never requires starlette/xray.
    """
    from starlette.middleware.base import BaseHTTPMiddleware  # noqa: PLC0415

    class _XRayHttpMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            segment = recorder.begin_segment(service_name)
            try:
                try:
                    from aws_xray_sdk.core.models import http  # noqa: PLC0415

                    segment.put_http_meta(http.URL, str(request.url))
                    segment.put_http_meta(http.METHOD, request.method)
                except Exception:  # noqa: BLE001 — metadata is best-effort
                    pass
                response = await call_next(request)
                try:
                    from aws_xray_sdk.core.models import http  # noqa: PLC0415

                    segment.put_http_meta(http.STATUS, response.status_code)
                except Exception:  # noqa: BLE001
                    pass
                return response
            finally:
                recorder.end_segment()

    return _XRayHttpMiddleware


def configure_tracing(app) -> bool:
    """Enable X-Ray tracing on *app* when ``ENABLE_XRAY`` is set.

    Returns True when tracing was configured, False otherwise (disabled or the
    SDK is unavailable). Never raises.
    """
    logger: logging.Logger = get_logger()
    if not xray_enabled():
        return False

    try:
        from aws_xray_sdk.core import patch_all, xray_recorder  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "xray_unavailable",
            extra={"event": "xray_unavailable", "error": str(exc)},
        )
        return False

    service_name = os.getenv("XRAY_SERVICE_NAME", "livecap-backend")
    try:
        configure_kwargs: dict[str, Any] = {
            "service": service_name,
            "context_missing": "IGNORE",
            "daemon_address": os.getenv("AWS_XRAY_DAEMON_ADDRESS", "127.0.0.1:2000"),
            "sampling": True,
        }
        # Do NOT pass AsyncContext — it calls loop.set_task_factory() which
        # uvloop rejects (does not accept the `context` argument). The default
        # threading.local context works correctly with uvicorn+uvloop for HTTP
        # tracing; WebSocket routes are intentionally excluded anyway.
        xray_recorder.configure(**configure_kwargs)
        patch_all()
        app.add_middleware(_build_http_middleware(xray_recorder, service_name))
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "xray_configure_failed",
            extra={"event": "xray_configure_failed", "error": str(exc)},
        )
        return False

    logger.info(
        "xray_enabled",
        extra={"event": "xray_enabled", "service": service_name},
    )
    return True
