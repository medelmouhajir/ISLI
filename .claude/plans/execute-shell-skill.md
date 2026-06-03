# Plan: Implement `execute-shell` Skill with Docker Sandbox

## Context

`shell-exec` is already registered in Core (`SKILL_REGISTRY`, `SKILL_METADATA`) and the SDK (`shell_exec`, `SHELL_EXEC_DEF`). The `SKILL_SHELL_EXEC_URL` environment variable is already wired in `docker-compose.yml`. **Only the actual `/exec` endpoint in `isli-skills` is missing.**

This plan implements the endpoint using **ephemeral Docker containers** as the sandbox — one container per command, heavily restricted, with no network, no privileges, read-only rootfs, and resource limits.

---

## Security Model

| Control | Implementation |
|---------|----------------|
| Isolation | Fresh ephemeral container per command (`--rm`) |
| Network | `--network none` |
| Privileges | `--cap-drop ALL`, `--security-opt no-new-privileges` |
| Filesystem | `--read-only` rootfs; only `workspace_data` volume mounted RW at `/workspace` |
| User | Runs as non-root (`--user 1000:1000`) |
| Resources | `--memory 256m`, `--cpus 1.0` (configurable via env) |
| Timeout | Hard timeout (default 30s, max 300s); container killed if exceeded |
| Output | Truncated to 64KB to prevent memory exhaustion |
| Command length | Limited to 4096 characters |
| Path traversal | `working_dir` sanitized; `..` and absolute paths rejected |
| Auth | `X-Internal-Auth` JWT required (existing `require_internal_auth`) |
| Docker socket | Mounted read-only on `skills` service only |

---

## Files to Create / Modify

### 1. `isli-skills/requirements.txt` & `pyproject.toml`
Add `docker==7.1.0` dependency.

### 2. `isli-skills/src/isli_skills/config.py`
Add sandbox configuration settings:
- `shell_exec_image`: default `alpine:latest`
- `shell_exec_mem_limit`: default `256m`
- `shell_exec_cpu_limit`: default `1.0`
- `shell_exec_timeout_default`: default `30`
- `shell_exec_timeout_max`: default `300`
- `shell_exec_output_limit`: default `65536`
- `workspace_base_path`: default `/workspaces`

### 3. `isli-skills/src/isli_skills/shell_executor.py` (NEW)
Core sandbox engine module:

```python
# Responsibilities:
# - sanitize_working_dir() → reject traversal, absolute paths, backslashes
# - run_sandboxed_command(agent_id, command, timeout, working_dir) → dict
#   1. Construct host workspace path: /workspaces/agents/{agent_id}
#   2. Initialize docker client (from_env)
#   3. Build container config:
#      image=settings.shell_exec_image
#      command=["/bin/sh", "-c", command]
#      working_dir=/workspace/agents/{agent_id}/{working_dir}
#      volumes={'workspace_data': {'bind': '/workspace', 'mode': 'rw'}}
#      network_mode='none'
#      mem_limit=settings.shell_exec_mem_limit
#      cpu_period=100000, cpu_quota=int(100000 * float(cpu_limit))
#      read_only=True
#      cap_drop=['ALL']
#      security_opt=['no-new-privileges:true']
#      user='1000:1000'
#      auto_remove=True
#      detach=True
#   4. Start container, wait with timeout
#   5. If timeout exceeded → container.kill(), set timed_out=True
#   6. Fetch logs(stdout=True, stderr=True), decode, truncate
#   7. Inspect for exit_code
#   8. Return: stdout, stderr, exit_code, duration_ms, timed_out, error (if any)
# - Handle Docker daemon errors gracefully → raise HTTPException(503)
```

### 4. `isli-skills/src/isli_skills/main.py`
Add:
- `ShellExecRequest` Pydantic model (`command`, `agent_id`, `timeout` default 30, `working_dir` optional)
- Validation: `timeout` clamped to max from config; `command` length ≤ 4096
- `POST /exec` endpoint protected by `Depends(require_internal_auth)`
- Calls `shell_executor.run_sandboxed_command()`
- Returns JSON response

### 5. `docker-compose.yml`
Add to `skills` service:
```yaml
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - workspace_data:/workspaces
```

### 6. `isli-skills/tests/test_shell_executor.py` (NEW)
Unit tests for `shell_executor.py` using mocked Docker client:
- `test_sanitize_working_dir_safe`
- `test_sanitize_working_dir_traversal_rejected`
- `test_sanitize_working_dir_absolute_rejected`
- `test_run_sandboxed_success` (mock container with exit 0)
- `test_run_sandboxed_timeout` (mock wait raising exception)
- `test_run_sandboxed_oom` (mock exit_code 137)
- `test_run_sandboxed_docker_unavailable`

### 7. `isli-skills/tests/test_api.py`
Add integration test:
- `test_shell_exec_endpoint` — POST `/exec` with mocked `shell_executor`

### 8. No changes needed in:
- `isli-core/src/isli_core/routers/skills.py` (already registered)
- `isli-agent-sdk/src/isli_agent/tools/system.py` (already wrapped)
- `isli-agent-sdk/src/isli_agent/tools/__init__.py` (already registered)
- Core docker-compose env vars (`SKILL_SHELL_EXEC_URL` already set)

---

## API Contract

### Request
```json
POST /exec
Headers: X-Internal-Auth: <jwt>
Body:
{
  "agent_id": "kimi-02",
  "command": "ls -la && echo hello",
  "timeout": 30,
  "working_dir": "src"
}
```

### Response (success)
```json
{
  "stdout": "total 8\ndrwxr-xr-x ...\nhello\n",
  "stderr": "",
  "exit_code": 0,
  "duration_ms": 1523,
  "timed_out": false
}
```

### Response (timeout)
```json
{
  "stdout": "partial output...",
  "stderr": "",
  "exit_code": -1,
  "duration_ms": 30000,
  "timed_out": true,
  "error": "Command timed out after 30 seconds"
}
```

### Response (Docker unavailable)
```json
HTTP 503
{
  "detail": "Sandbox engine unavailable: Docker daemon not reachable"
}
```

### Response (policy/validation)
```json
HTTP 400
{
  "detail": "Command exceeds maximum length of 4096 characters"
}
```

---

## Open Decision

**Container image choice:**
- `alpine:latest` — smallest, already has `/bin/sh`, but lacks many utilities (no `git`, `python`, `node`, etc.)
- Custom `isli-sandbox` image — larger but pre-installs common build tools

**Recommendation:** Start with `alpine:latest` as default. If agents need `python`/`node`/`gcc` inside the sandbox, we can build a custom `isli-sandbox` image later and change `SHELL_EXEC_IMAGE` via env var without code changes.

**UID/GID alignment:** The workspace files on `workspace_data` are created by the `workspace` service (likely running as root in Docker). The sandbox container runs as UID 1000. If permission errors occur when writing files, we may need to:
- Option A: Run sandbox as root too (weaker)
- Option B: Ensure workspace directories are `chmod 777` or owned by UID 1000
- Option C: Dynamically detect workspace owner UID from the volume

**Recommendation:** Start with `--user 1000:1000` and observe. If write permission issues arise, adjust the `workspace` service to create directories with `mode=0o777` (it already does this in `sandbox.py` line `root.mkdir(parents=True, exist_ok=True, mode=0o777)`), so reads should work and writes to existing files might need `chmod` in the workspace service.

---

## Verification Steps (post-implementation)

1. `cd isli-skills && ruff check .`
2. `pytest tests/test_shell_executor.py -v`
3. `pytest tests/test_api.py::TestSkillsAPI::test_shell_exec_endpoint -v`
4. Rebuild: `docker compose up -d --build skills`
5. Test end-to-end: trigger an agent that uses `shell_exec` tool, verify command runs in isolated container
6. Verify `docker ps -a` shows no leftover containers after execution (auto_remove)
