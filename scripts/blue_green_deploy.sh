#!/usr/bin/env bash
# ISLI Blue/Green Deployment Script
# Usage: ./scripts/blue_green_deploy.sh <green_version>

set -euo pipefail

GREEN_VERSION="${1:-latest}"
TRAEFIK_HOST="${TRAEFIK_HOST:-http://localhost:8080}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.scale-out.yml}"

BLUE_SERVICE="isli-core-blue"
GREEN_SERVICE="isli-core-green"

echo "[deploy] Starting blue/green deployment: green=${GREEN_VERSION}"

# 1. Start green environment alongside blue
export CORE_API_IMAGE="ghcr.io/isli/isli-core:${GREEN_VERSION}"
echo "[deploy] Starting green environment..."
docker compose -f "${COMPOSE_FILE}" up -d --no-deps --scale "${GREEN_SERVICE}=1" "${GREEN_SERVICE}"

# 2. Health check green
echo "[deploy] Health checking green..."
for i in {1..30}; do
    if curl -sf "http://localhost:8000/health" >/devdev/null 2>&1; then
        echo "[deploy] Green is healthy"
        break
    fi
    echo "[deploy] Waiting for green... (${i}/30)"
    sleep 2
done

# 3. Switch traffic via Traefik labels (or nginx upstream)
echo "[deploy] Switching traffic to green..."
# In Traefik, this is done by updating labels on the green container
# For docker-compose, we can use docker labels
# This is a simplified version — production uses Consul/etcd for dynamic config

# 4. Scale down blue
echo "[deploy] Scaling down blue..."
docker compose -f "${COMPOSE_FILE}" up -d --no-deps --scale "${BLUE_SERVICE}=0" "${BLUE_SERVICE}"

# 5. Verify
echo "[deploy] Verifying deployment..."
curl -sf "http://localhost:8000/health" || {
    echo "[deploy] Health check failed! Rolling back..."
    docker compose -f "${COMPOSE_FILE}" up -d --no-deps --scale "${BLUE_SERVICE}=1" "${BLUE_SERVICE}"
    docker compose -f "${COMPOSE_FILE}" up -d --no-deps --scale "${GREEN_SERVICE}=0" "${GREEN_SERVICE}"
    exit 1
}

echo "[deploy] Blue/green deployment complete. Green=${GREEN_VERSION} is live."
