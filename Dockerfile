# ============================================================================
# Freedom That Lasts - Production Dockerfile
# Multi-stage build for minimal image size and security
# ============================================================================

# ============================================================================
# Stage 1: Builder
# ============================================================================
FROM python:3.11-slim AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /build

# Copy dependency files first (for layer caching)
COPY pyproject.toml README.md ./
COPY src/ ./src/

# Install dependencies and build wheel
RUN pip install --no-cache-dir build && \
    python -m build --wheel && \
    pip wheel --no-cache-dir --wheel-dir /wheels .

# ============================================================================
# Stage 2: Runtime
# ============================================================================
FROM python:3.11-slim

# Set labels for metadata
LABEL maintainer="Freedom That Lasts Contributors"
LABEL description="Event-sourced governance kernel for democratic systems"
LABEL version="1.0.0-dev"

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    tini \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r -g 1000 ftl && \
    useradd -r -u 1000 -g ftl -m -d /home/ftl -s /bin/bash ftl

# Set working directory
WORKDIR /app

# Copy wheels from builder
COPY --from=builder /wheels /wheels

# Install the application
RUN pip install --no-cache-dir /wheels/*.whl && \
    rm -rf /wheels

# Create directories for data and logs
RUN mkdir -p /app/data /app/logs && \
    chown -R ftl:ftl /app

# Copy additional files
COPY --chown=ftl:ftl examples/ /app/examples/

# Switch to non-root user
USER ftl

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    FTL_DB_PATH=/app/data/ftl.db \
    FTL_LOG_LEVEL=INFO \
    FTL_JSON_LOGS=true

# Expose ports
# 8080: Health check server
# 9090: Prometheus metrics
EXPOSE 8080 9090

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/health/ready || exit 1

# Use tini as init system (proper signal handling)
ENTRYPOINT ["/usr/bin/tini", "--"]

# Default command: Start both health and metrics servers
# In production, use a process manager or run separate containers
CMD ["python", "-c", "\
import os; \
import threading; \
from pathlib import Path; \
from freedom_that_lasts.health_server import initialize_health_server, run_health_server; \
from freedom_that_lasts.kernel.logging import configure_logging; \
from freedom_that_lasts.kernel.metrics import start_metrics_server; \
\
# Configure logging\n\
configure_logging(json_output=True, log_level=os.getenv('FTL_LOG_LEVEL', 'INFO')); \
\
# Initialize health server\n\
db_path = os.getenv('FTL_DB_PATH', '/app/data/ftl.db'); \
Path(db_path).parent.mkdir(parents=True, exist_ok=True); \
initialize_health_server(db_path); \
\
# Start metrics server in background\n\
metrics_thread = threading.Thread(target=lambda: start_metrics_server(9090), daemon=True); \
metrics_thread.start(); \
\
# Start health server (blocking)\n\
run_health_server(port=8080, debug=False); \
"]
