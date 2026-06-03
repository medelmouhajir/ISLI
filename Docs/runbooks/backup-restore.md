# Runbook: Backup and Restore

## Docker Compose Deployment

### Backup

```bash
# PostgreSQL
docker exec -t isli-postgres-1 pg_dumpall -c -U isli > isli-backup-$(date +%F).sql

# Redis
docker exec -t isli-redis-1 redis-cli SAVE
docker cp isli-redis-1:/data/dump.rdb redis-backup-$(date +%F).rdb

# ChromaDB
docker exec -t isli-core-1 python3 scripts/chromadb_backup.py backup \
  --data-dir /data/vectors \
  --output /backups/chromadb/chroma_$(date +%Y%m%d_%H%M%S).tar.gz \
  --verify

# Ollama models
docker run --rm -v isli_ollama_data:/data -v $(pwd):/backup alpine tar czf /backup/ollama-backup-$(date +%F).tar.gz -C /data .
```

### Restore

```bash
# PostgreSQL
docker exec -i isli-postgres-1 psql -U isli < isli-backup-YYYY-MM-DD.sql

# Redis
docker cp redis-backup-YYYY-MM-DD.rdb isli-redis-1:/data/dump.rdb
docker restart isli-redis-1
```

## ChromaDB Restore

> ⚠️ **Warning:** Restoring ChromaDB requires a brief service outage for Core and Keeper.

### Prerequisites

- Identify the backup archive to restore (via `GET /v1/admin/backups/chromadb` or the filesystem at `/backups/chromadb/`).
- Verify the SHA-256 checksum matches the stored `checksum_sha256` in the `chromadb_backups` table or the `.sha256` sidecar file.

### Step-by-Step

1. **Stop Core and Keeper** (to release the ChromaDB lock):
   ```bash
   docker compose stop core keeper
   ```

2. **Preserve current data**:
   ```bash
   docker exec -t isli-core-1 mv /data/vectors /data/vectors.bak
   ```

3. **Restore from archive**:
   ```bash
   docker exec -t isli-core-1 python3 scripts/chromadb_backup.py restore \
     --archive /backups/chromadb/chroma_20260530_120000.tar.gz \
     --data-dir /data/vectors
   ```

4. **Verify integrity**:
   ```bash
   # The restore script prints whether the checksum matches.
   # If it fails, rollback immediately:
   docker exec -t isli-core-1 rm -rf /data/vectors
   docker exec -t isli-core-1 mv /data/vectors.bak /data/vectors
   ```

5. **Start services**:
   ```bash
   docker compose up -d core keeper
   ```

6. **Smoke test**:
   - Open the Board → Settings → Keeper.
   - Trigger a semantic memory search via an agent conversation.
   - If searches return results, the restore succeeded.

7. **Cleanup** (only after confirming success):
   ```bash
   docker exec -t isli-core-1 rm -rf /data/vectors.bak
   ```

## Native Deployment

### Backup

```bash
# PostgreSQL
pg_dumpall -c -U isli > isli-backup-$(date +%F).sql

# Redis
cp /var/lib/redis/dump.rdb redis-backup-$(date +%F).rdb

# SQLite (if used)
cp isli_prod.db isli-backup-$(date +%F).db

# Ollama models
tar czf ollama-backup-$(date +%F).tar.gz -C ~/.ollama .
```

### Restore

```bash
# PostgreSQL
psql -U isli < isli-backup-YYYY-MM-DD.sql

# Redis
cp redis-backup-YYYY-MM-DD.rdb /var/lib/redis/dump.rdb
systemctl restart redis

# SQLite
cp isli-backup-YYYY-MM-DD.db isli_prod.db

# Ollama
tar xzf ollama-backup-YYYY-MM-DD.tar.gz -C ~/.ollama
```

## Automated Backups

Add a cron job for nightly backups:

```bash
# /etc/cron.d/isli-backup
0 2 * * * root /opt/isli/scripts/backup.sh
```

The `scripts/backup.sh` script in the repo already handles Docker-based backups.
