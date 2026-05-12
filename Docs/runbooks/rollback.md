# Runbook: Rollback ISLI Deployment

## Scenario

A bad release has caused degraded service. You need to revert to the previous stable Docker image.

## Docker Compose Rollback

### 1. Identify the Previous Image Tag

If you use explicit SHA tags:

```bash
docker images ghcr.io/medelmouhajir/isli-core
# Find the previous stable SHA tag
```

If you use `latest` and need to pull an older version:

```bash
# Pull the previous known-good image explicitly
docker pull ghcr.io/medelmouhajir/isli-core:<previous-sha>
```

### 2. Update docker-compose.yml

Edit `docker-compose.yml` and pin the image for the affected service(s):

```yaml
services:
  core:
    image: ghcr.io/medelmouhajir/isli-core:<previous-sha>
```

Or use an environment variable override in `.env`:

```bash
CORE_API_IMAGE=ghcr.io/medelmouhajir/isli-core:<previous-sha>
```

### 3. Restart the Service

```bash
docker compose up -d core
```

Or restart all services:

```bash
docker compose up -d
```

### 4. Verify

```bash
curl -sf http://localhost:8000/health
curl -sf http://localhost:8000/ready
```

## Full Stack Revert

If the entire release is bad, revert the Compose file and re-deploy:

```bash
git checkout HEAD~1 -- docker-compose.yml
docker compose up -d
```

## Native Deployment Rollback

For native (non-Docker) deployments:

```bash
cd /opt/isli
git checkout <previous-tag>
./scripts/install-native.sh
systemctl restart isli-core isli-keeper isli-channels isli-skills isli-board
```

## Post-Rollback Verification

Run the same smoke tests from [deploy.md](deploy.md).
