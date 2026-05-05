#!/usr/bin/env bash
# Auto-train if model artifacts are missing, then seed DB, then serve.
set -euo pipefail

cd /app

DATA_CSV="data/통합_시험접수_현황.csv"
MODEL_FILE="backend/artifacts/lgbm_proc_days.txt"

if [[ ! -f "$MODEL_FILE" ]]; then
  if [[ ! -f "$DATA_CSV" ]]; then
    echo "[FATAL] $DATA_CSV not found. Mount the dataset to /app/data."
    echo "        docker run -v /host/path/to/data:/app/data ..."
    exit 1
  fi
  echo "[entrypoint] training model..."
  python backend/train.py
fi

echo "[entrypoint] seeding demo applications (idempotent)..."
python -m backend.seed || true

echo "[entrypoint] starting uvicorn on :8765"
exec python -m uvicorn backend.app:app --host 0.0.0.0 --port 8765
