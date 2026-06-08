# ISLI Security Runbook
## Operational Security for ISLI Deployments

### 1. Secret Management

#### 1.1 How Secrets Work

ISLI uses **Docker Compose secrets** to inject sensitive values at runtime. Secret files live in the `secrets/` directory on the host and are mounted into containers as in-memory files under `/run/secrets/`.

| Secret File | Mounted At | Used By | Purpose |
|-------------|------------|---------|---------|
| `secrets/jwt_secret.txt` | `/run/secrets/jwt_secret` | core, keeper, channels, skills, workspace | HS256 JWT signing/verification |
| `secrets/admin_api_key.txt` | `/run/secrets/admin_api_key` | core | Board UI admin authentication |
| `secrets/pii_encryption_key.txt` | `/run/secrets/pii_encryption_key` | core | AES-256-GCM for PII archive columns |

Each service's `config.py` reads the file path via a `field_validator` that intercepts values starting with `/run/secrets/` and returns the file contents.

#### 1.2 Creating Secret Files

```bash
# Create the directory
mkdir -p secrets

# Generate a 32-byte JWT secret
openssl rand -base64 32 > secrets/jwt_secret.txt

# Generate admin API key
openssl rand -base64 32 > secrets/admin_api_key.txt

# Generate PII encryption key
openssl rand -base64 32 > secrets/pii_encryption_key.txt

# Secure permissions
chmod 600 secrets/*.txt
```

#### 1.3 Secret Rotation

**JWT rotation is NOT zero-downtime.** Every service reads `JWT_SECRET` at startup through its own `config.py`. A rolling restart creates a window where Core signs with the new key while Skills/Channels/Workspace/Keeper still verify with the old one.

**Safest rotation path** (accepts ~5s downtime):

```bash
# 1. Write new secrets
openssl rand -base64 32 > secrets/jwt_secret.txt

# 2. Restart ALL services in one command
docker compose restart core keeper channels skills workspace

# 3. Verify health
curl -f http://localhost:8000/health
curl -f http://localhost:8100/health
```

For a **zero-downtime future**, implement a SIGHUP handler in Core that re-reads `JWT_SECRET` from disk without restarting, and propagate the new key to other services via a coordinated protocol. This is not yet implemented.

#### 1.4 Incident Response: Leaked JWT_SECRET

If `JWT_SECRET` is suspected leaked:

1. **Rotate immediately** using the steps above
2. **Invalidate agent tokens**: Agents use per-agent JWTs signed with `JWT_SECRET`. Rotation forces all agents to re-register (their old tokens become invalid). The `token_issued_at` mechanism in Core already supports this — new tokens are issued with `iat` after the rotation, and the old ones fail verification.
3. **Check audit logs**: Query `audit_logs` table for unusual skill invocations or channel sends during the exposure window
4. **Review Redis**: Check for unauthorized WebSocket connections or queued events

### 2. Network Segmentation

#### 2.1 Network Topology

```
isli-public   → Traefik only  (edge ingress)
isli-mesh     → App services   (east-west traffic)
isli-data     → Data stores    (postgres, redis, chromadb, ollama)
```

Rules:
- **Data services** (postgres, redis, ollama) attach **only** to `isli-data`
- **App services** attach to `isli-mesh` + `isli-data` (pragmatic; full isolation requires a mesh)
- **Traefik** attaches to `isli-public` + `isli-mesh`
- **Board** attaches to `isli-public` only (static SPA)

#### 2.2 Host Port Bindings

In production (`docker-compose.yml`), **only Traefik binds host ports** (`80`, `443`). All internal services are reachable only within the Docker networks.

For native development, `docker-compose.override.yml` can re-add ports:

```yaml
services:
  core:
    ports:
      - "8000:8000"
  postgres:
    ports:
      - "5432:5432"
```

### 3. Application Auth Verification

#### 3.1 Verify Skill Proxy is Closed

```bash
# This must return 401, not 200
curl -s -o /dev/null -w "%{http_code}" \
  -H "X-Internal-Auth: "" \
  http://core:8000/v1/skills/memory-save/save
```

Expected: `401`

#### 3.2 Verify Channels /send is Closed

```bash
# This must return 401
curl -s -o /dev/null -w "%{http_code}" \
  -X POST http://channels:8200/send \
  -H "Content-Type: application/json" \
  -d '{"channel":"telegram","channel_user_id":"123","text":"test"}'
```

Expected: `401`

#### 3.3 Verify Empty JWT Secret Fails Closed

```bash
# In production, this must return 401
docker compose exec skills python -c "
import os
os.environ['ISLI_ENV'] = 'production'
os.environ['JWT_SECRET'] = ''
from isli_skills.auth import verify_internal_token
try:
    verify_internal_token('dummy')
    print('FAIL: accepted empty secret')
except Exception:
    print('OK: rejected empty secret')
"
```

Expected: `OK: rejected empty secret`

#### 3.4 Verify WebSocket Token is in Header

```bash
# Capture the WebSocket handshake
tcpdump -i any -A -s 0 port 8000 &
# Or check proxy logs — the URL should NOT contain ?token=...
```

The agent WebSocket connection now sends the token in the `Authorization` header instead of the query string.

### 4. mTLS Readiness Checklist

Before adopting a service mesh, verify:

- [ ] All services read secrets from `/run/secrets/` (not hardcoded env vars)
- [ ] `ServiceDiscovery` utility resolves all upstreams correctly
- [ ] `X-Internal-Auth` is present on ALL inter-service calls
- [ ] Empty `jwt_secret` returns 401 in every service
- [ ] Network segmentation is active (`isli-public` / `isli-mesh` / `isli-data`)
- [ ] No internal service exposes host ports except Traefik
- [ ] `secrets/` directory is in `.gitignore`

### 5. Board UI Admin Key

The admin key is stored in browser `localStorage`. This is a known limitation:

- **Risk**: XSS can expose the admin key
- **Mitigation**: Board UI runs as a static SPA with CSP headers; no inline scripts
- **Future**: Move to session-based auth or SSO when multi-tenancy is introduced

### 6. Emergency Controls & Dynamic Security

#### 6.1 Global Emergency Stop (E-Stop)

ISLI includes a global circuit breaker that can halt all agent activity immediately.

- **Effect**: Blocks all task creation, skill invocations, and agent coordination.
- **Mechanism**: Redis pub/sub (`isli:estop` channel) + persistent key (`isli:estop:active`).
- **Management**:
    - **UI**: Settings -> Security -> Emergency Controls.
    - **API (Trigger)**: `POST /v1/security/estop/trigger` (Requires Admin Key)
    - **API (Reset)**: `POST /v1/security/estop/reset` (Requires Admin Key)
    - **API (Status)**: `GET /v1/security/estop/status`

#### 6.2 PII Mesh Verification

To confirm the PII Mesh is active and no raw PII leaks to cloud LLMs:

```bash
# 1. Enable PII Mesh for an agent
 curl -X PUT http://localhost:8000/v1/agents/kimi-02 \
   -H "Authorization: Bearer $(cat secrets/admin_api_key.txt)" \
   -H "Content-Type: application/json" \
   -d '{"config": {"pii_mesh_enabled": true, "pii_use_slm": true}}'

# 2. Send a test message containing PII
 curl -X POST http://localhost:8000/v1/sessions/test-session/message \
   -H "Authorization: Bearer $(cat secrets/admin_api_key.txt)" \
   -H "Content-Type: application/json" \
   -d '{"text": "My email is alice@example.com and SSN is 123-45-6789"}'

# 3. Inspect the agent runner logs — the LLM payload should contain {{PII:email:...}} and {{PII:ssn:...}}
 docker compose logs --tail=50 agent-runner-xxx | grep "pii_mesh\|scrubbed"

# 4. Verify the user-facing response contains the original values (re-hydrated)
# 5. Verify Core logs show no CRITICAL stray-token warnings
 docker compose logs --tail=50 core | grep "pii_stray_token"
```

Expected: No `CRITICAL` lines. The user receives "My email is alice@example.com...", but the cloud LLM only saw tokens.

### 6.3 Dynamic Security Settings

Core security behaviors can be adjusted at runtime via the Board UI without restarting services.

| Setting Key | Scope | Purpose | Default |
|-------------|-------|---------|---------|
| `security_pii_scrubber_enabled` | `security` | Toggle PII scanning (SSN, Email, CC) | `true` |
| `security_prompt_injection_threshold` | `security` | Risk score threshold for blocking injections | `0.5` |
| `security_default_monthly_usd_cap` | `security` | Default budget cap for new users | `50.0` |
| `security_audit_retention_days` | `security` | Audit log retention period | `90` |
| `pii_mesh_default_enabled` | `system` | Default PII Mesh state for new agents | `false` |
| `pii_use_slm_default` | `system` | Default SLM usage for new agents | `false` |
| `pii_regex_pre_filter` | `system` | Enable fast regex pre-filter before SLM | `true` |
| `pii_token_ttl_hours` | `system` | Token map retention in Keeper vault | `24` |

These settings are evaluated by the `PolicyEngine` during every interaction.

### 7. Contact / Escalation

| Scenario | Action |
|----------|--------|
| Suspected JWT leak | Rotate secrets + invalidate agent tokens (Section 1.4) |
| Unauthorized skill access | Check `audit_logs` + verify auth bypasses are closed (Section 3) |
| Network breach | Isolate affected container + review `isli-mesh` / `isli-data` traffic |
| Consul/Linkerd migration | See `Docs/15-service-mesh-backlog.md` |
