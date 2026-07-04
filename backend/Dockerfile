# LiveCap Backend Dockerfile
# Multi-stage build for efficient containerization (Requirement 13.1)
# Stage 1: Install dependencies
# Stage 2: Copy application code and configure runtime

# ==============================================================================
# Stage 1: Dependencies
# ==============================================================================
FROM python:3.11-slim-bookworm@sha256:721dc13fd1be0a771e54b72097634291d628d0007dee9da777e2ce676a9c998f AS dependencies

# Set working directory
WORKDIR /app

# Copy only requirements.txt first to leverage Docker layer caching
COPY requirements.txt .

# Install Python dependencies
# - --no-cache-dir: Reduces image size by not caching pip packages
# - --upgrade pip: Ensures we have the latest pip version
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ==============================================================================
# Stage 2: Application
# ==============================================================================
FROM python:3.11-slim-bookworm@sha256:721dc13fd1be0a771e54b72097634291d628d0007dee9da777e2ce676a9c998f AS application

# Set working directory
WORKDIR /app

# Copy installed dependencies from the dependencies stage
COPY --from=dependencies /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=dependencies /usr/local/bin /usr/local/bin

# Copy application code
COPY app/ ./app/

# Environment variable injection points (Requirement 13.6)
# These can be overridden by ECS task definition or docker run -e flags
# AWS region for Transcribe, Translate, and S3
ENV AWS_REGION=ap-southeast-1

# S3 bucket name for transcript storage (Transcript_Bucket)
ENV S3_BUCKET=livecap-transcripts

# Presigned download link expiration (seconds, default: 24 hours)
ENV DOWNLOAD_LINK_EXPIRATION=86400

# Maximum session duration (seconds, default: 30 minutes)
ENV SESSION_TIMEOUT=1800

# Transcribe language code (used when BILINGUAL_DUAL_STREAM=false)
ENV TRANSCRIBE_LANGUAGE_CODE=vi-VN

# Enable dual-stream mode (parallel vi-VN and en-US streams)
ENV BILINGUAL_DUAL_STREAM=true

# Audio pipeline debug logging
ENV AUDIO_PIPELINE_DEBUG=false

# CORS allowed origin (frontend URL)
ENV ALLOWED_ORIGIN=http://localhost:5173

# CloudWatch log group
ENV CLOUDWATCH_LOG_GROUP=livecap

# Expose port 8000 for Uvicorn
EXPOSE 8000

# Health check instruction (Requirement 13.1)
# Calls GET /api/health every 30 seconds using the Python standard library
# - interval: 30s between checks
# - timeout: 5s to wait for response
# - start-period: 30s grace period after container starts
# - retries: 3 consecutive failures before marking unhealthy
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health', timeout=4)"

# Run Uvicorn with FastAPI app (Requirement 13.1)
# - host 0.0.0.0: Listen on all network interfaces (required for container networking)
# - port 8000: Standard FastAPI port
# - app.main:app: Import path to the FastAPI application instance
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
