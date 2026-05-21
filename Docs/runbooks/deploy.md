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

## Post-Deployment

- Board UI: http://localhost (or http://server-ip)
- Core API docs: http://localhost:8000/docs
- Jaeger traces: http://localhost:16686

### Admin API Key

Mutating endpoints (create/move/delete tasks, create/update agents) require an `Authorization: Bearer <key>` header. The key is configured via the `ADMIN_API_KEY` environment variable and must be entered in the board's login modal. Ensure the value in your `.env` matches what operators use in the board.
