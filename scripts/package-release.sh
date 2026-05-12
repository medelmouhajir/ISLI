#!/usr/bin/env bash
# Build Docker images, save them, and create a deployable release tarball.
# Usage: ./scripts/package-release.sh [VERSION_TAG]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
VERSION="${1:-$(git -C "${PROJECT_ROOT}" rev-parse --short HEAD 2>/dev/null || echo 'latest')}"
RELEASE_DIR="${PROJECT_ROOT}/isli-release-${VERSION}"
IMAGES_DIR="${RELEASE_DIR}/images"

SERVICES=(isli-core isli-keeper isli-channels isli-skills isli-board)
REGISTRY="ghcr.io/medelmouhajir"

echo "[package-release] Packaging ISLI release ${VERSION}"

mkdir -p "${IMAGES_DIR}" "${RELEASE_DIR}/runbooks"

for svc in "${SERVICES[@]}"; do
    echo "[package-release] Building ${svc}:${VERSION}"
    docker build -t "${REGISTRY}/${svc}:${VERSION}" -t "${REGISTRY}/${svc}:latest" "${PROJECT_ROOT}/${svc}"

echo "[package-release] Saving ${svc}:${VERSION}"
    docker save "${REGISTRY}/${svc}:${VERSION}" | gzip > "${IMAGES_DIR}/${svc}.tar.gz"
done

echo "[package-release] Copying deployment files"
cp "${PROJECT_ROOT}/docker-compose.yml" "${RELEASE_DIR}/"
cp "${PROJECT_ROOT}/docker-compose.scale-out.yml" "${RELEASE_DIR}/" 2>/dev/null || true
cp "${PROJECT_ROOT}/.env.production" "${RELEASE_DIR}/.env"
cp -r "${PROJECT_ROOT}/docs/runbooks/"* "${RELEASE_DIR}/runbooks/"
cp "${PROJECT_ROOT}/scripts/install.sh" "${RELEASE_DIR}/"

echo "[package-release] Creating tarball"
tar -czf "${PROJECT_ROOT}/isli-release-${VERSION}.tar.gz" -C "${PROJECT_ROOT}" "isli-release-${VERSION}"

echo "[package-release] Release ready: isli-release-${VERSION}.tar.gz"
