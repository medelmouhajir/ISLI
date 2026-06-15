# Runbook: Installing a Third-Party Skill via the Universal Skill Runtime

## Overview

ISLI's Universal Skill Runtime (USR) allows installing any skill published as a Dockerized HTTP service with **zero edits** to Core or the SDK. This runbook covers the installation, verification, and troubleshooting steps.

## Prerequisites

- Admin API Key (`ADMIN_API_KEY`)
- Core API is running and healthy (`curl http://localhost:8000/health`)
- The skill repository contains:
  - `isli-skill.yaml` (manifest)
  - `Dockerfile`
  - `requirements.txt` (or equivalent)
  - `src/main.py` (FastAPI app with `/health`, `/.well-known/isli-manifest`, and `POST /{endpoint}` routes)

## Installation

### Step 1: Install (Clone + DB Registration)

```bash
export ADMIN_KEY="your-admin-api-key"
export CORE_URL="http://localhost:8000"

# Install the skill from a public Git repository
curl -H "Authorization: Bearer ${ADMIN_KEY}" \
     -H "Content-Type: application/json" \
     -X POST ${CORE_URL}/v1/skills/install \
     -d '{
       "skill_id": "autocar-api",
       "git_url": "https://github.com/medelmouhajir/autocar-api-skill"
     }'
```

**Expected response:**
```json
{
  "status": "installed",
  "skill_id": "autocar-api",
  "name": "AutoCar API",
  "version": "1.2.0",
  "category": "web"
}
```

At this stage, the skill is registered in the database with status `pending`. The container has **not** been built or started yet.

### Step 2: Enable (Build + Start Container)

```bash
curl -H "Authorization: Bearer ${ADMIN_KEY}" \
     -X POST ${CORE_URL}/v1/skills/autocar-api/enable
```

**Expected response:**
```json
{"status": "enabled", "skill_id": "autocar-api"}
```

Core will:
1. Build a Docker image tagged `isli/skill-autocar-api:1.2.0`
2. Start a container named `skill-autocar-api` on the `isli_default` network
3. Inject `JWT_SECRET`, `PORT`, and `LOG_LEVEL` into the container environment
4. Update the `skill_registry` status to `active`

### Step 3: Verify

```bash
# Health check via Core's probe endpoint
curl -H "Authorization: Bearer ${ADMIN_KEY}" \
     ${CORE_URL}/v1/skills/autocar-api/probe

# List all skills (should include autocar-api)
curl ${CORE_URL}/v1/skills | python3 -m json.tool

# Check the skill manifest
curl ${CORE_URL}/v1/skills/autocar-api | python3 -m json.tool
```

### Step 4: Agent Discovery

Agents pick up new skills automatically:
- **New agents**: Discover at startup via `GET /v1/skills`
- **Running agents**: Receive a `agent:config_updated` WebSocket event and reload tools on the next heartbeat

To force an immediate reload, restart the agent container:
```bash
docker restart isli-agent-kimi-02
```

## Uninstallation

```bash
# Disable (stop container)
curl -H "Authorization: Bearer ${ADMIN_KEY}" \
     -X POST ${CORE_URL}/v1/skills/autocar-api/disable

# Uninstall (remove container, image, DB row, source)
curl -H "Authorization: Bearer ${ADMIN_KEY}" \
     -X DELETE ${CORE_URL}/v1/skills/autocar-api
```

## Troubleshooting

### `400 Bad Request` during install
- The repo is missing `isli-skill.yaml` or it fails schema validation.
- Check that `id` in the manifest matches the `skill_id` in the request.
- Verify `category` is one of: `web`, `content`, `workspace`, `communication`, `memory`, `kanban`, `engineering`, `audio`, `database`, `git`, `system`, `custom`.

### `500` during enable (Docker build failure)
- Check Core logs: `docker compose logs core | grep "scm.build_failed"`
- Verify the skill's `Dockerfile` is valid: `cd data/installed_skills/autocar-api && docker build .`
- Ensure `curl` is installed in the image (required by Docker Compose healthchecks).

### Container starts but probe fails
- Check if the skill exposes `/health` on the port defined in `isli-skill.yaml`.
- Verify the skill verifies `X-Internal-Auth` header (the probe does not send it, but the actual tool calls do).
- Check container logs: `docker logs skill-autocar-api`

### Agent cannot see the new tools
- Verify the agent's `skills` list in the database includes the new skill (or that the skill is not skill-filtered out).
- Check agent logs for `runner.dynamic_tool_registered` or `runner.tool_not_found`.
- Restart the agent container to force a fresh tool sync.

### `401 Unauthorized` on tool calls
- The skill is not verifying `X-Internal-Auth` correctly.
- Check that the skill reads `JWT_SECRET` from the environment and validates the token with `skill:proxy` scope.

## Native Dev Mode Differences

In native development (`ISLI_ENV=development` without Docker):
- `enable` assigns an ephemeral host port instead of building a Docker image.
- The skill process must be started manually (e.g., `cd data/installed_skills/autocar-api && uvicorn src.main:app --port 39000`).
- Core stores `base_url = http://localhost:{port}` in `skill_registry`.
