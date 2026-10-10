# syntax=docker/dockerfile:1
#
# Solo — single-image build.
#
# A user-facing origin is served by one container: FastAPI serves the REST API,
# the WebSocket and the statically built React frontend.

# ---------------------------------------------------------------------------
# Stage 1: build the frontend
# ---------------------------------------------------------------------------
FROM node:24-alpine AS frontend-build

WORKDIR /build/frontend

# Install dependencies first so this layer is cached across source changes.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY frontend/ ./
RUN npm run build

# ---------------------------------------------------------------------------
# Stage 2: runtime
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    APP_DATA_DIR=/data \
    FRONTEND_DIST=/app/frontend/dist \
    APP_HOST=0.0.0.0 \
    APP_PORT=8080 \
    APP_ENV=production

WORKDIR /app

# curl is used by the container health check.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ ./backend/
COPY --from=frontend-build /build/frontend/dist ./frontend/dist

# Run as a non-root user; /data is the single persistent volume.
RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin solo \
    && mkdir -p /data \
    && chown -R solo:solo /app /data

USER solo

WORKDIR /app/backend

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=25s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8080/api/health || exit 1

CMD ["python", "-m", "app"]
