FROM docker.m.daocloud.io/library/python:3.12-slim AS builder

WORKDIR /build
COPY backend/requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir --target=/deps -r requirements.txt


FROM docker.m.daocloud.io/library/python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_WORKERS=1 \
    PYTHONPATH=/app/deps

RUN addgroup --system --gid 1001 appgroup \
    && adduser --system --uid 1001 --gid 1001 appuser \
    && apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=builder /deps /app/deps
COPY --chown=appuser:appgroup backend /app/backend
COPY --chown=appuser:appgroup scripts /app/scripts
RUN mkdir -p /app/logs /app/chroma_db /app/knowledge_files \
    && chown -R appuser:appgroup /app

USER appuser
WORKDIR /app/backend

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl --fail http://localhost:8000/health || exit 1

CMD ["sh", "-c", "exec python -m uvicorn main:app --host 0.0.0.0 --port 8000 --workers ${APP_WORKERS}"]
