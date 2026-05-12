# Runbook: Update a Running ISLI Deployment

## Docker Compose Update

### Online (GHCR)

```bash
cd /opt/isli   # or wherever your compose file lives

# Pull latest images
docker compose pull

# Restart with new images
docker compose up -d

# Verify
curl http://localhost:8000/health
```

### Offline (Release Tarball)

```bash
# Extract new release
tar -xzf isli-release-<new-sha>.tar.gz
cd isli-release-<new-sha>

# Load new images
for img in images/*.tar.gz; do docker load < "$img"; done

# Copy updated compose file if needed
cp docker-compose.yml /opt/isli/

# Restart
cd /opt/isli
docker compose up -d
```

## Native Deployment Update

### Linux (systemd)

```bash
cd /opt/isli
git pull origin main

# Update Python deps
for svc in isli-core isli-keeper isli-channels isli-skills; do
    cd /opt/isli/$svc
    /opt/isli/$svc/.venv/bin/pip install -e "/opt/isli/$svc[dev]"
done

# Update board
cd /opt/isli/isli-board
npm ci
npm run build

# Restart services
sudo systemctl restart isli-core isli-keeper isli-channels isli-skills isli-board
```

### Windows (PowerShell)

```powershell
cd C:\ISLI
git pull origin main

# Update Python deps
foreach ($svc in @("isli-core","isli-keeper","isli-channels","isli-skills")) {
    & "C:\ISLI\$svc\.venv\Scripts\pip.exe" install -e "C:\ISLI\$svc[dev]"
}

# Update board
cd C:\ISLI\isli-board
npm ci
npm run build

# Restart
& 'C:\ISLI\stop-isli.ps1'
& 'C:\ISLI\start-isli.ps1'
```

## Rolling Back an Update

See [rollback.md](rollback.md).
