# syntax=docker/dockerfile:1.7
# Build context is the repo root:  docker build -f infra/Dockerfile .

# ---- 1. dashboard: static assets ------------------------------------------
FROM node:22-alpine AS dashboard
WORKDIR /build
COPY dashboard/package.json dashboard/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY dashboard/ ./
RUN npm run build

# ---- 2. runtime: API + built dashboard ------------------------------------
FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

# dependencies first so code edits don't bust the pip layer
COPY pyproject.toml ./
COPY src ./src
RUN pip install ".[api]"

COPY --from=dashboard /build/dist /app/dashboard

RUN useradd --create-home --uid 10001 splitkit
USER splitkit

ENV SPLITKIT_DASHBOARD_DIR=/app/dashboard \
    WEB_CONCURRENCY=2
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import sys, urllib.request; sys.exit(urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).status != 200)"

# migrate (idempotent) then serve; exec so uvicorn receives SIGTERM directly
CMD ["sh", "-c", "python -m splitkit.db.migrate && exec uvicorn splitkit.api.main:app --host 0.0.0.0 --port 8000 --workers ${WEB_CONCURRENCY}"]
