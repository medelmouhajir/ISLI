#!/usr/bin/env bash
# One-command installer for ISLI on a VPS or PC with Docker.
# Usage: ./install.sh

set -euo pipefail

RELEASE_URL="${RELEASE_URL:-}"
RELEASE_FILE="${RELEASE_FILE:-}"

if [[ -z "${RELEASE_URL}" && -z "${RELEASE_FILE}" ]]; then
    echo "Usage: RELEASE_URL=<url> ./install.sh"
    echo "   or: RELEASE_FILE=./isli-release-<sha>.tar.gz ./install.sh"
    exit 1
fi

if [[ -n "${RELEASE_URL}" ]]; then
    echo "[install] Downloading release..."
    curl -L -o isli-release.tar.gz "${RELEASE_URL}"
    RELEASE_FILE="isli-release.tar.gz"
fi

echo "[install] Extracting release..."
tar -xzf "${RELEASE_FILE}"
RELEASE_DIR=$(tar -tzf "${RELEASE_FILE}" | head -1 | cut -f1 -d"/")

cd "${RELEASE_DIR}"

if ! command -v docker &>/dev/null || ! command -v docker-compose &>/dev/null; then
    echo "[install] Docker and Docker Compose are required. Install them first:"
    echo "  https://docs.docker.com/engine/install/"
    exit 1
fi

echo "[install] Loading Docker images..."
for img in images/*.tar.gz; do
    echo "[install] Loading ${img}"
    docker load < "${img}"
done

if [[ ! -f ".env" ]]; then
    echo "[install] Creating .env from template..."
    cp .env .env 2>/dev/null || true
fi

echo "[install] Please edit .env with your secrets, then press Enter to continue"
read -r

echo "[install] Starting ISLI services..."
docker compose up -d

echo "[install] Waiting for services to be healthy..."
sleep 10
for port in 8000 8001 8002 8003; do
    for i in $(seq 1 30); do
        if curl -sf "http://localhost:${port}/health" >/dev/null; then
            echo "[install] Service on port ${port} is ready"
            break
        fi
        sleep 1
    done
done

echo "[install] ISLI is running. Board available at http://localhost"
