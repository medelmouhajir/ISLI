# Runbook: Backup and Restore

## Docker Compose Deployment

### Backup

```bash
# PostgreSQL
docker exec -t isli-postgres-1 pg_dumpall -c -U isli > isli-backup-$(date +%F).sql

# Redis
docker exec -t isli-redis-1 redis-cli SAVE
docker cp isli-redis-1:/data/dump.rdb redis-backup-$(date +%F).rdb

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
