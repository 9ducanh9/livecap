"""LiveCap backend application entry point.

Assembles the FastAPI application (task 9.1, Requirements 11.1, 11.3, 10.1):

- Creates the FastAPI app instance.
- Registers the WebSocket router (``GET /ws/transcribe``).
- Registers the export, meeting-notes, and optional enrichment routers.
- Configures CORS for the explicitly configured frontend origins.
- Adds the ``GET /api/health`` endpoint.
- Initialises the Logging_Service at application startup via the
  ``lifespan`` context manager.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import enrichment as enrichment_router
from app.routers import export as export_router
from app.routers import history as history_router
from app.routers import summary as summary_router
from app.routers import websocket as websocket_router
from app.services.logging_service import get_logger, setup_logging
from app.tracing import configure_tracing


# ---------------------------------------------------------------------------
# Lifespan: runs once at startup and once at shutdown
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler.

    Startup
    -------
    1. Call ``setup_logging()`` to initialise the Logging_Service (CloudWatch
       with stdout fallback) — satisfies Requirement 10.1.
    2. Log a startup event so operators can confirm the service is running.

    Shutdown
    --------
    Log a shutdown event.
    """
    settings = get_settings()

    # Initialise the Logging_Service (Requirement 10.1).
    setup_logging(
        log_group=settings.cloudwatch_log_group,
        aws_region=settings.aws_region,
    )

    logger = get_logger()
    logger.info(
        "livecap_startup",
        extra={
            "event": "application_startup",
            "allowed_origins": settings.allowed_origins,
            "session_timeout": settings.session_timeout,
        },
    )

    yield  # --- application is running ---

    logger.info("livecap_shutdown", extra={"event": "application_shutdown"})


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="LiveCap",
    description=(
        "Real-time speech caption and translation backend. "
        "Streams audio via WebSocket to Amazon Transcribe and Amazon Translate."
    ),
    version="1.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# CORS middleware — allow only the deployed frontend origin (Req 11.3)
# ---------------------------------------------------------------------------

_settings = get_settings()

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(_settings.allowed_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Optional AWS X-Ray tracing (C4). No-op unless ENABLE_XRAY is set.
configure_tracing(app)


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

# WebSocket endpoint: GET /ws/transcribe (upgrade to WebSocket)
app.include_router(websocket_router.router)

# Export REST endpoint: POST /api/sessions/{session_id}/export
app.include_router(export_router.router)

# Optional Cognito-protected transcript history.
app.include_router(history_router.router)

# On-demand meeting notes: POST /api/sessions/{session_id}/summary
app.include_router(summary_router.router)

# Optional English-only enrichment: POST /api/tts and POST /api/analyze
app.include_router(enrichment_router.router)

# Usage quota: GET /api/usage
from app.routers import quota as quota_router
app.include_router(quota_router.router)


# ---------------------------------------------------------------------------
# Health check endpoint
# ---------------------------------------------------------------------------


@app.get(
    "/api/health",
    summary="Health check",
    response_description="Service health status",
    tags=["health"],
)
async def health_check() -> dict:
    """Return a simple health status response.

    ``GET /api/health`` → ``{ "status": "healthy", "version": "1.0.0" }``

    Used by load balancers and monitoring tools to verify the service is
    reachable and responding (Requirement 11.1).
    """
    return {"status": "healthy", "version": "1.0.0"}
