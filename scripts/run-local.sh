#!/usr/bin/env bash
# Start all ISLI services natively (no Docker)
# Usage: ./scripts/run-local.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

if [[ -f "${PROJECT_ROOT}/.env.local" ]]; then
    echo "[run-local] Loading .env.local"
    set -a
    source "${PROJECT_ROOT}/.env.local"
    set +a
else
    echo "[run-local] .env.local not found, using defaults"
fi

PIDS=()

cleanup() {
    echo "[run-local] Shutting down services..."
    for pid in "${PIDS[@]}"; do
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
        fi
    done
    wait
    echo "[run-local] All services stopped"
    exit 0
}

trap cleanup SIGINT SIGTERM

echo "[run-local] Starting isli-core on :8000"
cd "${PROJECT_ROOT}/isli-core"
python -m uvicorn isli_core.main:app --host 127.0.0.1 --port 8000 &
PIDS+=($!)

echo "[run-local] Starting isli-keeper on :8001"
cd "${PROJECT_ROOT}/isli-keeper"
python -m uvicorn isli_keeper.main:app --host 127.0.0.1 --port 8001 &
PIDS+=($!)

echo "[run-local] Starting isli-channels on :8002"
cd "${PROJECT_ROOT}/isli-channels"
python -m uvicorn isli_channels.main:app --host 127.0.0.1 --port 8002 &
PIDS+=($!)

echo "[run-local] Starting isli-skills on :8003"
cd "${PROJECT_ROOT}/isli-skills"
python -m uvicorn isli_skills.main:app --host 127.0.0.1 --port 8003 &
PIDS+=($!)

echo "[run-local] Starting isli-board on :5173"
cd "${PROJECT_ROOT}/isli-board"
npm run dev &
PIDS+=($!)

echo "[run-local] All services started. Press Ctrl+C to stop."
wait
