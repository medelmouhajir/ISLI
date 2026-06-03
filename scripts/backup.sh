#!/usr/bin/env bash
# ISLI — Backup script
# Run as cron or sidecar container. Backs up PostgreSQL, ChromaDB, and Redis.

set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/backups}"
S3_ENDPOINT="${S3_ENDPOINT:-}"
S3_BUCKET="${S3_BUCKET:-}"
S3_ACCESS_KEY="${S3_ACCESS_KEY:-}"
S3_SECRET_KEY="${S3_SECRET_KEY:-}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
RUN_DIR="${BACKUP_DIR}/${TIMESTAMP}"

mkdir -p "${RUN_DIR}"

echo "[backup] Starting backup at ${TIMESTAMP}"

# PostgreSQL
PGHOST="${PGHOST:-postgres}"
PGPORT="${PGPORT:-5432}"
PGUSER="${PGUSER:-isli}"
PGPASSWORD="${PGPASSWORD:-password}"
PGDATABASE="${PGDATABASE:-isli}"

echo "[backup] Dumping PostgreSQL..."
export PGPASSWORD
pg_dump -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d "${PGDATABASE}" \
  -F custom -f "${RUN_DIR}/postgres.dump"
sha256sum "${RUN_DIR}/postgres.dump" > "${RUN_DIR}/postgres.dump.sha256"

# ChromaDB
CHROMA_DIR="${CHROMA_DIR:-/data/vectors}"
if [ -d "${CHROMA_DIR}" ]; then
  echo "[backup] Snapshotting ChromaDB..."
  tar czf "${RUN_DIR}/chromadb.tar.gz" -C "${CHROMA_DIR}" .
  sha256sum "${RUN_DIR}/chromadb.tar.gz" > "${RUN_DIR}/chromadb.tar.gz.sha256"
fi

# Redis
REDIS_HOST="${REDIS_HOST:-redis}"
REDIS_PORT="${REDIS_PORT:-6379}"

echo "[backup] Triggering Redis BGSAVE..."
redis-cli -h "${REDIS_HOST}" -p "${REDIS_PORT}" BGSAVE
sleep 5
# In containerized Redis, RDB is at /data/dump.rdb
REDIS_RDB="${REDIS_RDB:-/data/dump.rdb}"
if [ -f "${REDIS_RDB}" ]; then
  cp "${REDIS_RDB}" "${RUN_DIR}/redis.rdb"
  sha256sum "${RUN_DIR}/redis.rdb" > "${RUN_DIR}/redis.rdb.sha256"
fi

# Compute overall archive checksum before compression
cd "${RUN_DIR}"
sha256sum * > "${RUN_DIR}/SHA256SUMS"
cd - > /dev/null

# Compress
tar czf "${RUN_DIR}.tar.gz" -C "${BACKUP_DIR}" "${TIMESTAMP}"
rm -rf "${RUN_DIR}"

# Upload to S3/MinIO if configured
if [ -n "${S3_ENDPOINT}" ] && [ -n "${S3_BUCKET}" ]; then
  echo "[backup] Uploading to S3..."
  export AWS_ACCESS_KEY_ID="${S3_ACCESS_KEY}"
  export AWS_SECRET_ACCESS_KEY="${S3_SECRET_KEY}"
  aws --endpoint-url="${S3_ENDPOINT}" s3 cp "${RUN_DIR}.tar.gz" "s3://${S3_BUCKET}/isli-backups/"
fi

# Cleanup old backups
find "${BACKUP_DIR}" -name "*.tar.gz" -mtime +"${RETENTION_DAYS}" -delete

echo "[backup] Backup complete: ${RUN_DIR}.tar.gz"
