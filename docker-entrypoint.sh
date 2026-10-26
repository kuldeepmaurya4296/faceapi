#!/bin/sh
# Container entrypoint: turns env vars into uvicorn flags.
set -eu

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
WORKERS="${WORKERS:-2}"
LOG_LEVEL="${LOG_LEVEL:-info}"

# Make sure the models are present even when the image was built with
# DOWNLOAD_MODELS=false and no volume was mounted.
if [ ! -f "${FACEAPI_MODELS_DIR:-/app/models}/face_detection_yunet_2023mar.onnx" ]; then
  echo "entrypoint: detector model missing — downloading models"
  python scripts/download_models.py || echo "entrypoint: model download failed; the API will start and report itself unready"
fi

echo "entrypoint: starting Face API on ${HOST}:${PORT} with ${WORKERS} worker(s)"
exec uvicorn app.main:app \
  --host "$HOST" \
  --port "$PORT" \
  --workers "$WORKERS" \
  --log-level "$LOG_LEVEL" \
  --proxy-headers \
  --forwarded-allow-ips '*'
