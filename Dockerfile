# syntax=docker/dockerfile:1
#
# Portable Face API image — works on any x86-64 or arm64 host with Docker.
#
#   docker build -t faceapi .
#   docker run -p 8000:8000 -v faceapi-data:/app/data faceapi
#
# CPU-only by design: YuNet + SFace are small enough to run on a $5 VPS.

FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential \
 && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /build
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt


FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH=/app \
    FACEAPI_DATA_DIR=/app/data \
    FACEAPI_MODELS_DIR=/app/models \
    PORT=8000 \
    WORKERS=2

# libglib2.0-0 + libgomp1 are the only shared libraries OpenCV's headless
# wheels still expect on Debian slim.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libglib2.0-0 libgomp1 \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --create-home --uid 10001 --shell /usr/sbin/nologin faceapi

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY app ./app
COPY scripts ./scripts
COPY cli.py ./
COPY docker-entrypoint.sh ./
RUN chmod +x docker-entrypoint.sh

# Bake the ONNX weights into the image. Set --build-arg DOWNLOAD_MODELS=false
# to skip (e.g. air-gapped builds where you mount ./models as a volume).
ARG DOWNLOAD_MODELS=true
RUN if [ "$DOWNLOAD_MODELS" = "true" ]; then python scripts/download_models.py; fi

RUN mkdir -p /app/data && chown -R faceapi:faceapi /app

USER faceapi
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:'+__import__('os').environ.get('PORT','8000')+'/healthz', timeout=4).status==200 else 1)"

ENTRYPOINT ["./docker-entrypoint.sh"]
