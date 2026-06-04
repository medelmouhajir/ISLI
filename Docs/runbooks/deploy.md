# Runbook: Deploy ISLI to Production

## Prerequisites

- Docker Engine >= 24.0 and Docker Compose plugin installed
- At least 4 CPU cores and 8 GB RAM (16 GB recommended)
- Linux or Windows host with Docker Desktop (Windows) or Docker Engine (Linux)
- Internet access to pull images from GHCR, or an offline release tarball

## Quick Start (Online — GHCR)

```bash
# 1. Clone or download the release
git clone https://github.com/medelmouhajir/ISLI.git
cd ISLI

# 2. Create .env from template and fill in secrets
cp .env.production .env
nano .env   # or vim / notepad

# 3. Start all services
docker compose up -d

# 4. Verify
curl http://localhost:8000/health
curl http://localhost:8001/health
curl http://localhost:8002/health
curl http://localhost:8003/health
```

## Offline Deployment (Air-Gapped PC)

If the target machine has no internet access:

1. Download `isli-release-<sha>.tar.gz` from GitHub Releases on a machine with internet.
2. Copy the tarball to the target machine via USB.
3. Extract and run the included installer:

```bash
tar -xzf isli-release-<sha>.tar.gz
cd isli-release-<sha>
./install.sh
```

The installer will:
- Load Docker images from the bundled `images/*.tar.gz` files
- Create `.env` from the template
- Start `docker compose up -d`
- Wait for health checks

## Native Deployment (No Docker)

See [native-deploy.md](native-deploy.md) for running all services directly on the host OS without containers.

## Post-Deployment Verification

After `docker compose up -d`, run these checks before declaring the deployment healthy:

### 1. Container Health
```bash
docker compose ps
# All services should show (healthy) or (running)
```

### 2. Core API Reachability
```bash
curl http://localhost:8000/health
curl http://localhost:8001/health
curl http://localhost:8002/health
curl http://localhost:8003/health
```

### 3. Board → Core DNS Resolution
```bash
# Board nginx must resolve `core` to an IP
docker compose exec board getent hosts core
# Expected: 172.20.0.x  core
```
If this fails with `NXDOMAIN`, the `board` service is not on the same Docker network as `core`. Add `isli-mesh` to the `board` service's `networks` list.

### 4. Agent → Core DNS Resolution
```bash
# Spawned agents must resolve `core:8000`
docker exec isli-agent-<id> getent hosts core
# Expected: 172.20.0.x  core
```
If this fails, `AGENT_NETWORK` in Core's environment does not match a network that Core itself is attached to. Set `AGENT_NETWORK=${COMPOSE_PROJECT_NAME:-isli}_isli-mesh` so agents share the `isli-mesh` network with Core.

### 5. Ollama Models
```bash
docker compose exec ollama ollama list
# Expected: qwen3:1.7b, nomic-embed-text, qwen2.5-coder:1.5b, ...
```
If the list is empty, `ollama-init` could not reach the internet. Ensure `ollama-init` is attached to `isli-mesh` (not just `isli-data`, which is `internal: true`).

### 6. pgvector Extension
```bash
docker compose exec postgres psql -U isli -d isli -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

### 7. Required Env Vars
Verify these are set in `.env`:
```bash
grep -E '^(WEBHOOK_SECRET|SKILL_REGISTRY_TOKEN|ADMIN_API_KEY|JWT_SECRET|PII_ENCRYPTION_KEY)=' .env
```
Missing `WEBHOOK_SECRET` causes 401 errors on all Core → Channels and Core → Skills calls. Missing `SKILL_REGISTRY_TOKEN` causes skill registry refresh to fail with 401.

---

### Service Endpoints

- Board UI: http://localhost (or http://server-ip)
- Core API docs: http://localhost:8000/docs
- Jaeger traces: http://localhost:16686

### Admin API Key

Mutating endpoints (create/move/delete tasks, create/update agents) require an `Authorization: Bearer <key>` header. The key is configured via the `ADMIN_API_KEY` environment variable and must be entered in the board's login modal. Ensure the value in your `.env` matches what operators use in the board.
