# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    API_HOST=0.0.0.0 \
    API_PORT=8000 \
    API_RELOAD=false \
    DATABASE_URL=sqlite:////app/data/tenderlens.db \
    DATA_DIR=/app/data \
    RAG_QDRANT_PATH=/app/data/qdrant \
    FASTEMBED_CACHE_PATH=/app/data/fastembed_cache \
    COMPANY_PROFILE_FILE=/app/config/company_profile.example.json \
    GIGACHAT_CA_BUNDLE_FILE=/app/certs/russian_trusted_root_ca_pem.crt \
    EIS_CA_BUNDLE_FILE=/app/certs/russian_trusted_root_ca_pem.crt \
    TENDERLENS_HEALTHCHECK_URL=http://127.0.0.1:8000/health

WORKDIR /app

# ONNX Runtime uses libgomp on CPU. ca-certificates keeps normal HTTPS trust available.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN python -m pip install --upgrade pip \
    && python -m pip install -r /app/requirements.txt

COPY app /app/app
COPY config /app/config
COPY russian_trusted_root_ca_pem.crt /app/certs/russian_trusted_root_ca_pem.crt

# Persist SQLite, local Qdrant and FastEmbed cache outside the image layer.
RUN mkdir -p /app/data \
    && useradd --system --uid 10001 --create-home --home-dir /home/tenderlens tenderlens \
    && chown -R tenderlens:tenderlens /app/data /home/tenderlens \
    && python -m compileall -q /app/app

USER tenderlens

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=8s --start-period=90s --retries=3 \
    CMD ["python", "-m", "app.deployment.healthcheck"]

CMD ["python", "-m", "app.api"]
