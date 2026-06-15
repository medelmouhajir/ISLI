# 06 — Skills System

## Design Philosophy

> **Skills are smart. Agents are smarter.**

A Skill in ISLI is a **functional capability microservice**:
- **Smart Skills**: Can contain their own AI/LLM loops for domain-specific reasoning.
- **Dumb Skills**: Pure utility microservices (regex, math, formatters).
- Returns structured JSON.
- Minimal, predictable, testable.
- Optimized for fast execution and minimal token consumption.

This allows ISLI to rival frameworks like OpenClaw by permitting skills to handle complex, ambiguous tasks that require internal reasoning before returning a result to the agent.

---

## Skill Manifest (`skill.yaml`)

Every skill is defined by a manifest file:

```yaml
skill:
  id: web-search
  name: "Web Search"
  version: "1.1.0"
  description: "Search the web and return top N results with smart relevance filtering"
  author: system

  endpoint: http://localhost:8101
  health_check: /health
  is_smart: true  # Indicates this skill uses internal AI reasoning
```

  inputs:
    - name: query
      type: string
      required: true
      description: "Search query string"
    - name: max_results
      type: integer
      default: 5
      description: "Maximum results to return"

  outputs:
    - name: results
      type: array
      schema:
        - title: string
        - url: string
        - snippet: string

  permissions_required: []
  rate_limit: 20/minute
  timeout_seconds: 15
```

---

## Built-in Skills Registry

| Skill ID | Description | Notes |
|----------|-------------|-------|
| `web-search` | Web search → structured results | Uses local SearXNG instance |
| `web-fetch` | Fetch URL content → clean text | HTML stripped; returns `status_code` & `url` |
| `pdf-extract` | Extract text from PDF | Returns paginated JSON |
| `file-read` | Read file from agent's workspace | Supports line ranges and hard character caps (16k-64k) |
| `file-write` | Write file to agent's workspace | Path-scoped, per-agent isolation |
| `file-list` | List directory entries in agent's workspace | Path-scoped, per-agent isolation |
| `file-delete` | Delete a file from agent's workspace | Path-scoped, per-agent isolation |
| `db-query` | Run read-only SQL query | Row limiting (50) and cell truncation (500 chars) |
| `shell-exec` | Execute shell command in sandbox | Ephemeral Docker container; network isolated; no privileges |
| `send-email` | Send email via SMTP | Requires SMTP config |
| `send-message` | Send message via channel | Routes to channel gateway |
| `image-describe` | Get text description of image | Calls local vision model |
| `datetime` | Current date/time in formats | Pure local SDK tool |
| `discover-skills` | List all available skills for this agent | Pure local SDK tool; triggers per-turn tool expansion |
| `json-parse` | Parse and validate JSON | Schema validation support |
| `summarize-text` | Long text → short summary | Proxies to Keeper via isli-skills |
| `embed-text` | Text → embedding vector | Proxies to Keeper via isli-skills |
| `memory-save` | Save to Tier 3 semantic memory | Inline in Core (ChromaDB) |
| `memory-delete` | Delete from Tier 3 semantic memory | Inline in Core (ChromaDB) |
| `memory-search` | Search semantic memory | Inline in Core (ChromaDB) |
| `create-kanban-task` | Create a task on the Kanban board | Enables agent self-delegation |
| `list-kanban-tasks` | Query board for tasks by status/assignee | Visibility into delegated work |
| `update-kanban-task` | Update status, priority, or add comment | Task management and handoffs |
| `create-engineering-plan` | Generate SE implementation plan | Saves PLAN.md to workspace |
| `shared-file-read` | Read file from a shared workspace | Member-scoped; owner or member |
| `shared-file-write` | Write file to a shared workspace | Member-scoped; enforces quota |
| `shared-file-list` | List files in a shared workspace | Member-scoped |
| `shared-file-delete` | Delete file from a shared workspace | Member-scoped |
| `shared-file-move` | Move/rename a file within or between shared workspaces | Member-scoped; enforces target quota |
| `shared-workspace-info` | Return shared workspace metadata | Member-scoped; name, members, root path, quota |
| `shared-workspace-search` | Search file names and/or contents across a shared workspace | Member-scoped; skip binary files |
| `shared-promote-file-workspace` | Promote a file from the agent's own workspace into a shared workspace | Member-scoped; agent → shared |
| `promote-output` | Copy/move a file from a task attachment into a shared workspace | Task → shared scope promotion |
| `speech-to-text` | Transcribe audio → text | Proxies to `isli-audio` via Core skill proxy |
| `text-to-speech` | Synthesize text → audio (URL or base64) | Proxies to `isli-audio` via Core skill proxy; language-aware voice selection; can deliver to Telegram/WhatsApp/Board via `send_voice_message` SDK wrapper |
| `test-skill` | Dry-run dynamic skill code | Transient sandbox; AST validated |
| `register-skill` | Register a new dynamic skill | Triggers Kanban review gate |
| `update-skill` | Update metadata of an existing dynamic skill | No review gate; preserves `usage_count` / `created_at` |
| `interactive-debugger` | Run code with breakpoints, variable inspection, and line-by-line trace | Batch trace via `sys.settrace()`; modes: `trace`, `breakpoints`, `run`; watch expressions; stdout/stdin capture |
| `ui-components` | Render tables, cards, buttons, forms, JSON, timelines, metrics inline in chat | Inline in Core; Board renders React components; user interactions fire back as action messages (see Docs/13-immersive-chat-ui.md) |
| `get-secret` | Retrieve a secret value from the agent's encrypted vault by name | Inline in Core; AES-256-GCM encrypted at rest; per-agent scoped; every read is audit-logged |
| `git-clone` | Clone a remote git repository into the agent's workspace | URL validation blocks `file://`; atomic temp-dir clone; sandboxed via `resolve_path()` |
| `git-status` | Show working tree status (modified, staged, untracked) | Returns structured JSON with `is_dirty` flag and file lists |
| `git-commit` | Stage files and commit with a message | Supports explicit file list or `git add -A`; returns `commit_hash` |
| `git-push` | Push current/specific branch to remote | Defaults to `origin` + active branch; no force-push exposed |
| `git-pull` | Pull changes from remote into current branch | Returns `409` on merge conflicts; typed `GitConflictError` in SDK |
| `git-branch-list` | List all branches with current indicator | Returns `current` branch name and `branches` array |
| `git-branch-create` | Create a new branch, optionally checkout | `checkout: true` switches immediately |
| `git-checkout` | Switch to an existing branch | Typed `GitInvalidOperationError` if branch does not exist |
| `git-log` | Show commit history | Capped by character count (12k) to prevent context bloat |
| `notify-user` | Display a notification card in the user's web UI | Inline in Core; rate-limited (20/hour per user per agent); respects quiet hours and user preferences |
| `web-browse-navigate` | Navigate a browser to a URL | Creates persistent session per agent; cookies/localStorage survive across calls |
| `web-browse-snapshot` | Accessibility-tree snapshot of current page | Returns `@ref` IDs for interactive elements; default `full=false` (compact) |
| `web-browse-click` | Click an element by `@ref` ID | Requires prior `web-browse-snapshot`; uses Playwright locator |
| `web-browse-type` | Type text into an input by `@ref` ID | Supports `clear` flag; resolves element via accessibility name/role |
| `web-browse-press` | Press a keyboard key | `Enter`, `Tab`, `Escape`, `ArrowDown`, etc. |
| `web-browse-scroll` | Scroll the page up or down | Amount multiplier: ~300px per unit |
| `web-browse-back` | Navigate back in browser history | Invalidates `@ref` IDs before navigation |
| `web-browse-console` | Return browser console logs | Delta since last call; cursor-based pagination; resets on navigate |
| `web-browse-vision` | Screenshot as base64 PNG | Returns `screenshot_b64`; flagged as `HEAVY_SKILL` |
| `web-browse-images` | List images with src/alt/dimensions | `eval_on_selector_all` over `<img>` tags |

### Shared Workspace Skills — Added 2026-06-15

Agents can manage **shared workspaces** via dedicated skills. Shared workspaces are collaborative filesystem scopes with an explicit owner and member list. All shared workspace skills are member-scoped: Core validates that the calling agent is the workspace owner or a member before proxying the call to the workspace service.

| Skill | Action | Routed to | Notes |
|-------|--------|-----------|-------|
| `shared-file-read` | `read` | `isli-workspace` `/read` (`scope=shared`) | Supports `max_chars`, `line_start`, `line_end` |
| `shared-file-write` | `write` | `isli-workspace` `/write` (`scope=shared`) | Atomic write; creates parent directories; enforces `quota_bytes` |
| `shared-file-list` | `list` | `isli-workspace` `/list` (`scope=shared`) | List files and directories under a path |
| `shared-file-delete` | `delete` | `isli-workspace` `/delete` (`scope=shared`) | Directories are deleted recursively (use with care) |
| `shared-file-move` | `move` | `isli-workspace` `/shared/move` | Move/rename within one workspace or across two shared workspaces |
| `shared-promote-file-workspace` | `promote` | Core inline → `isli-workspace` `/shared/promote` | Copy a file from the agent's own workspace into a shared workspace |
| `shared-workspace-info` | `info` | Core inline (DB lookup) | Returns `name`, `description`, `owner_id`, `members`, `quota_bytes`, `root_path` |
| `shared-workspace-search` | `search` | `isli-workspace` `/shared/search` | Search file names and/or contents; skips binary files and files > 10 MB |

**SDK wrappers:** `isli_agent.tools.workspace` exposes `shared_file_read`, `shared_file_write`, `shared_file_list`, `shared_file_delete`, `shared_file_move`, `shared_promote_file_workspace`, `shared_workspace_info`, `shared_workspace_search`. The `AgentRunner` convenience method `add_shared_workspace_tools()` registers all eight tools at once.

**Promotion paths:**
- **Agent workspace → shared workspace:** use `shared-promote-file-workspace` (or `shared_promote_file_workspace` in the SDK).
- **Task attachment → shared workspace:** use `promote-output` (or `promote_output` in the SDK). This is useful when a delegated Kanban task produces a deliverable that should become a permanent project asset.

### Browser Automation (Beta) — Added 2026-06-01

ISLI provides **Hermes-style browser automation** via the `isli-skills` service. Agents can navigate websites, take accessibility-tree snapshots, interact with elements by `@ref` ID, scroll, and capture screenshots — all through persistent per-agent browser sessions.

**Architecture:**
```
Agent SDK → Core API (skill proxy) → isli-skills:8100/browse/* → Playwright Chromium
                                       ↓
                                  Redis TTL heartbeat
                                  /data/browser-sessions (persistent contexts)
```

**Session Model:**
- One `BrowserContext` per `agent_id`, launched via `launch_persistent_context(user_data_dir=...)`
- Cookies, localStorage, and sessionStorage survive across skill calls
- In-memory `_sessions` dict holds Playwright objects (cannot be serialized)
- Redis used only for TTL heartbeat (`browser:session:{agent_id}`)
- Background cleanup loop closes stale sessions every 60s

**Snapshot Format (default `full=false`):**
```
[1] heading "Welcome to Example"
[2] input[text] "Email" @e1 (placeholder: "you@example.com")
[3] button "Sign in" @e2
[4] link "Forgot password?" @e3 href="/reset"
```

- Only **interactive elements** get `@ref` IDs in compact mode (`button`, `link`, `input`, `select`, `textarea`, `checkbox`, `radio`, etc.)
- `full=true` includes all semantic nodes (headings, paragraphs, lists, tables) — still only interactive elements get `@ref` IDs
- Node-boundary truncation at 8,000 chars; never cuts mid-line

**Safety Features:**
- `session.clear_refs()` called **before** every `navigate` and `back` — prevents stale `@ref` clicks on the new page
- `BrowserRefError` (400) if agent sends a click/type with an unknown or stale `@ref`
- Max concurrent sessions: `BROWSER_MAX_CONCURRENT_SESSIONS=5` → returns `503 + Retry-After: 30` when pool is exhausted
- All endpoints protected by `require_internal_auth` (X-Internal-Auth JWT)

**Heavy Skills:**
`web-browse-snapshot` and `web-browse-vision` are flagged as `HEAVY_SKILL` in Core. Their outputs are post-processed by the Keeper before reaching the agent's context window. This prevents token blowout from large pages or base64 screenshots.

**Example Agent Workflow:**
```
1. browser_navigate(url="https://example.com/signup")
2. browser_snapshot() → sees @e1 (email), @e2 (password), @e3 (submit)
3. browser_type(ref="@e1", text="user@example.com")
4. browser_type(ref="@e2", text="SecurePass123")
5. browser_click(ref="@e3")
6. browser_snapshot() → confirms success page
```

**Docker Compose Additions:**
- `skills` service: `BROWSER_REDIS_URL`, `BROWSER_SESSION_TTL`, `BROWSER_HEADLESS`, `BROWSER_SESSION_DIR`, `BROWSER_MAX_CONCURRENT_SESSIONS`
- `skills` service memory limit: `1G` (up from `512M`)
- Volume: `browser-sessions:/data/browser-sessions`

### Autonomous Skill Creation (Skill Smith)
ISLI enables agents (typically with an "Engineer" persona) to autonomously expand the system's capabilities. This follows a strict safety-first lifecycle:

1. **Design & Code**: The agent generates Python code defining an `async def run(payload: dict) -> dict:` function.
2. **Dry-Run (`test-skill`)**: The code is sent to a transient sandbox in `isli-skills`. It undergoes **AST Validation** (blocking `os`, `sys`, etc.) and is executed with a test payload.
3. **Registration (`register-skill`)**: Upon success, the agent registers the skill. This automatically:
   - Saves the code to the agent's workspace.
   - Creates a persistent entry in the skill registry.
   - Moves the corresponding Kanban task to the **Review** column.
4. **Update (`update-skill`)**: After a skill is registered, agents can update its metadata (`description`, `category`, `workspace_path`, `endpoint`, `health_endpoint`, `agent_id`) without triggering a new review cycle. The `usage_count` and `created_at` fields are preserved.
5. **Human/Auditor Review**: The skill remains "Pending" until a human or an auditor agent approves the Kanban task.
6. **Hot-Reload**: Once approved, Core emits a config event, and all relevant agents automatically sync the new tool into their toolbox.

### Shell Execution (Sandbox) — Added 2026-06-07

ISLI provides a secure **sandboxed shell execution** environment via the `isli-skills` service. Agents can run arbitrary shell commands within highly restricted, ephemeral Docker containers.

**Architecture:**
```
Agent SDK → Core API (skill proxy) → isli-skills:8100/exec → Docker Engine (sandbox)
                                       ↓
                                  Ephemeral Container (--rm)
                                  /workspace/agents/{agent_id} (RW mount)
```

**Security Model:**
- **Isolation**: Every command runs in a fresh ephemeral container (`--rm`).
- **Network**: Disabled (`--network none`).
- **Privileges**: Dropped (`--cap-drop ALL`, `--security-opt no-new-privileges`).
- **Filesystem**: Read-only rootfs; only the agent's workspace directory is mounted read-write.
- **User**: Runs as non-root (UID 1000:1000).
- **Resource Limits**: 
  - CPU: 1.0 (configurable)
  - Memory: 256MB (configurable)
  - Timeout: Default 30s, Max 300s.
- **Output**: Truncated at 64KB to prevent context window blowout.

**Configuration:**
- `shell_exec_image`: Default `alpine:latest`.
- `workspace_base_path`: Root directory for agent workspaces.

**Example Usage (SDK):**
```python
result = await agent.shell_exec(command="ls -la && echo 'Ready'")
# Returns: {"stdout": "...", "exit_code": 0, "duration_ms": 150, "timed_out": false}
```

### Update Skill (`update-skill`) — Added 2026-06-03

Agents can update metadata of an existing dynamic skill without triggering a review cycle or resetting usage telemetry.

**Endpoint:** `POST /v1/skills/update-skill/update` (proxied by Core to `isli-skills:8100/update`).

**Request parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `name` | string | yes | Unique name of the skill to update |
| `description` | string | no | New description |
| `category` | string | no | New category (e.g., `web`, `content`, `engineering`) |
| `workspace_path` | string | no | New relative path to the skill's `.py` file in the agent workspace |
| `endpoint` | string | no | New HTTP endpoint URL |
| `health_endpoint` | string | no | New health check URL |
| `agent_id` | string | no | New owning agent ID |

**Behavior:**
- Returns `404` if the skill does not exist in the registry.
- Only fields provided in the request are changed; omitted fields retain their current values.
- `usage_count`, `created_at`, and `last_used_at` are **preserved**.
- Persists to `/tmp/skill_registry.json` (or `$REGISTRY_FILE`).

**SDK Usage:**
```python
from isli_agent import update_skill

result = await update_skill(
    name="csv-parser",
    description="Parse CSV with header inference and type coercion",
    category="content",
    core_client=client
)
# Returns: {"status": "updated", "skill": { ... }}
```

### Skill Hygiene & Janitor
To prevent code rot, the system tracks usage telemetry:
- **Metrics**: Each skill records `usage_count` and `last_used_at`.
- **Janitor**: The `scripts/skill-janitor.py` utility identifies skills unused for >30 days and creates "Cleanup" tasks on the Kanban board for deprecation.

### Web Fetch (`web-fetch`)
The web-fetch skill retrieves the raw content of a webpage and returns it as structured data.

**Implementation Details:**
- **Proxy Route:** `POST /v1/skills/web-fetch/fetch` (Requests are proxied by Core to `http://skills:8100/fetch`).
- **Endpoint Aliasing:** Also supports `POST /browse` for backward compatibility with older board integrations.
- **Output:** Returns a JSON object containing `title`, `content` (stripped of HTML), `url` (final resolved destination after redirects), and `status_code` (HTTP status from the final destination).
- **Grounding Validation:** Core requires `status_code` (integer) and `url` (string) for successful tool execution verification.
- **Relationship to Browser Automation:** `web-fetch` is the **fast path** for simple content retrieval (no JS execution, no interaction). For pages requiring clicks, form submission, or multi-step navigation, use the `web-browse-*` skills instead. `web-fetch` remains in `HEAVY_SKILLS` for Keeper post-processing.

**Example Usage (SDK):**
```python
content = await agent.web_fetch(url="https://isli-ai.com/docs")
```

### Web Search (`web-search`)

**Skill Types:**
- **External microservice** — `summarize-text`, `embed-text` live in `isli-skills` and are proxied by Core
- **Dedicated audio microservice** — `speech-to-text`, `text-to-speech` live in `isli-audio` (FastAPI + faster-whisper + piper-tts) and are proxied by Core
- **Inline handler** — `memory-save`, `memory-delete`, `memory-search` are handled directly in Core's skill proxy router using `ChromaMemoryClient`; no external service hop
- **Local SDK tool** — `datetime` is a pure Python function in `isli-agent-sdk`; no network call

### Database Query (`db-query`)

The `db-query` skill lets agents run **read-only SQL queries** against the ISLI PostgreSQL database and receive structured tabular results.

**Implementation Details:**
- **Proxy Route:** `POST /v1/skills/db-query/query` → proxied to `isli-skills` at `POST /db-query`.
- **Read-Only Enforcement (DB-layer):**
  1. `sqlparse` AST validation rejects any statement containing forbidden keywords (`INSERT`, `UPDATE`, `DELETE`, `CREATE`, `ALTER`, `DROP`, `GRANT`, `COPY`, `EXECUTE`, `BEGIN`, `SET`, etc.).
  2. Multi-statement strings (containing `;`) are rejected.
  3. Only top-level `SELECT` statements are allowed.
  4. Schema allow-list (`DB_QUERY_ALLOWED_SCHEMAS`, default `public`) blocks queries referencing unlisted schemas.
  5. `asyncpg` sets `SET TRANSACTION READ ONLY` before execution.
- **Result Limiting:** Fetches are limited to `max_rows` (default 50). Optimization: The skill fetches `max_rows + 1` to detect if more results exist (`has_more: true`) without requiring a second `COUNT(*)` query.
- **Cell Truncation:** String or JSON cells exceeding `max_cell_chars` (default 500) are truncated, appending a hint with the original byte count (e.g., `...[truncated: 1200 bytes]`).
- **Timeout Guard:** Queries are capped at 15 seconds to prevent long-running analytics from blocking the skill.
- **Error Sanitization:** Raw PostgreSQL errors are logged server-side but surfaced to the agent as generic messages with a `reference_id` for support.
- **Response Format:** `{"columns": [...], "rows": [...], "row_count": N, "has_more": bool, "truncated": bool, "execution_time_ms": float, "reference_id": str}`

**Example Usage (SDK):**
```python
result = await agent.db_query(query="SELECT id, name, status FROM agents WHERE status = 'online' LIMIT 5")
```

### Git Integration (Added 2026-05-30)

ISLI provides **first-class Git version control** for agents via the `isli-workspace` service. All 9 git operations operate directly on the agent's sandboxed filesystem and share the same `scope`/`scope_id` access control model as `file-read/write/list/delete`.

---

## Skills Store — Universal Skill Runtime (USR) (Added 2026-06-11)

ISLI now supports a **Universal Skill Runtime** where any skill published as a standalone Dockerized HTTP service can be installed dynamically with **zero code changes** to Core or the SDK.

### Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────────────┐
│   Agent     │────▶│  Core API   │────▶│   Skill Container   │
│   SDK       │     │  /v1/skills │     │   (Docker per skill)│
└─────────────┘     └─────────────┘     └─────────────────────┘
                           │
                           ▼
                    ┌──────────────┐
                    │ skill_registry │ (PostgreSQL)
                    │ skill_runs   │ (PostgreSQL)
                    └──────────────┘
```

### Skill Manifest (`isli-skill.yaml`)

Every installable skill must provide an `isli-skill.yaml` manifest at its repository root:

```yaml
isli_version: "2.0"
id: "autocar-api"                      # Globally unique, kebab-case
name: "AutoCar API"
description: "Manage invoices, customers, work orders"
version: "1.2.0"
author: "medelmouhajir"
category: "web"                        # web, content, workspace, communication, memory, kanban, engineering, audio, database, git, system, custom

runtime:
  port: 8500
  build:
    context: "."
    dockerfile: "Dockerfile"

auth:
  type: "internal_jwt"               # Verifies X-Internal-Auth header

tools:
  - name: "autocar_login"
    description: "Authenticate with AutoCar ERP"
    endpoint: "login"
    method: "POST"
    parameters:
      type: "object"
      properties:
        email: { type: "string" }
        password: { type: "string" }
      required: ["email", "password"]

  - name: "autocar_call"
    description: "Call any AutoCar endpoint"
    endpoint: "call"
    method: "POST"
    parameters:
      type: "object"
      properties:
        method: { type: "string", enum: ["GET", "POST", "PUT", "DELETE"] }
        endpoint: { type: "string" }
        data: { type: "object" }
      required: ["method", "endpoint"]
```

### Container Contract

Any language/framework is acceptable as long as the container exposes:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/health` | `GET` | Docker Compose healthcheck. Return `{"status": "ok"}` |
| `/.well-known/isli-manifest` | `GET` | Returns the manifest as JSON |
| `/{endpoint}` | `POST` | One per tool. Accepts JSON, returns JSON. Must verify `X-Internal-Auth` JWT. |

### Admin Lifecycle API

All endpoints require `Authorization: Bearer {ADMIN_API_KEY}`.

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/v1/skills/install` | Clone repo, validate manifest, insert into DB (status `pending`) |
| `POST` | `/v1/skills/install-and-enable` | **One-click install** — clones, builds, runs, and probes in a single call |
| `POST` | `/v1/skills/{id}/enable` | Build Docker image and start container |
| `POST` | `/v1/skills/{id}/disable` | Stop container |
| `DELETE` | `/v1/skills/{id}` | Uninstall (stop, remove image, delete DB row) |
| `GET` | `/v1/skills/{id}/probe` | Health-check the skill's `/health` endpoint |
| `POST` | `/v1/skills/{id}/check-update` | Check remote git for newer version |
| `POST` | `/v1/skills/{id}/update` | Pull new source, blue/green container swap |
| `POST` | `/v1/skills/{id}/rollback` | Rollback to previous version |
| `GET` | `/v1/skills/{id}/versions` | List available git tags |
| `PATCH` | `/v1/skills/{id}` | Update `update_policy` or `source_ref` |
| `GET` | `/v1/skills/{id}/logs` | **Optional** — stream last N lines of container logs |

### One-Click Installation Flow (Added 2026-06-12)

**`POST /v1/skills/install-and-enable`** is the primary endpoint for the Board UI and CLI. It performs the full lifecycle in one call:

```bash
curl -H "Authorization: Bearer $ADMIN_API_KEY" \
     -X POST http://core:8000/v1/skills/install-and-enable \
     -d '{"skill_id":"autocar-api","git_url":"https://github.com/medelmouhajir/autocar-api-skill"}'
```

Response:
```json
{
  "status": "active",
  "skill_id": "autocar-api",
  "name": "AutoCar API",
  "version": "1.2.0",
  "category": "web",
  "build_time_ms": 12450,
  "probe_ok": true
}
```

What happens internally:
1. **Clone** — `git clone` into `data/installed_skills/{skill_id}`
2. **Validate** — Parse `isli-skill.yaml` against `SkillManifest` schema
3. **Build** — Docker builds `isli/skill-{id}:{version}` with `rm=True`
4. **Run** — Container starts on `isli_default` network with `JWT_SECRET` injected
5. **Probe** — Retry loop calls `/health` every 3s for up to 60s
6. **Broadcast** — `skill:enabled` Redis event emitted; all connected agents re-sync config
7. **DB update** — `status` → `active`, `last_probe_status` → `healthy`

If any step fails, the skill row stays in `error` status with `last_probe_result` containing the failure details.

### Startup Resilience (Added 2026-06-12)

Core's startup lifespan (`startup/skills.py`) automatically re-enables any `skill_registry` rows with `status='active'` on boot. This means skill containers survive `docker compose down && docker compose up` cycles without manual intervention.

### Agent Push Notification (Added 2026-06-12)

When a skill is enabled (via either `install-and-enable` or standalone `enable`), Core emits a `skill:enabled` Redis Pub/Sub event:

```json
{
  "type": "skill:enabled",
  "payload": {
    "skill_id": "autocar-api",
    "skill_name": "AutoCar API",
    "category": "web",
    "tools": [...]
  }
}
```

- **Board UI** receives it via WebSocket and refreshes the Skills Store page without reload.
- **Agent SDK** receives it via the existing agent→Core WebSocket and triggers `_sync_config()`, which fetches `GET /v1/skills` and registers the new tools immediately.

This means running agents discover new skills **within seconds** of installation, without requiring a restart.

### Probe Status Observability (Added 2026-06-12)

The `skill_registry` table now tracks per-skill health:

| Column | Type | Purpose |
|--------|------|---------|
| `last_probe_status` | `string` | `building`, `healthy`, `unhealthy`, `error` |
| `last_probe_result` | `JSON` | Raw `/health` response or `{"error": "..."}` |
| `last_probe_at` | `datetime` | Timestamp of last probe attempt |

`GET /v1/skills` returns these fields for every DB-backed skill, enabling the Board UI to show real-time status badges: green "Running", amber "Building", red "Build Failed", gray "Stopped". Installed cards also expose **Start**/**Stop** toggle buttons (calling `POST /v1/skills/{id}/enable` and `POST /v1/skills/{id}/disable`), **Retry Enable** for failed builds, and **Uninstall**.

### Skill Versioning & Updates (Added 2026-06-13)

Skills installed from Git repositories now support full semantic-versioning lifecycle: version detection, safe update with blue/green container swap, automatic updates, and rollback.

#### Versioning DB Columns

| Column | Type | Purpose |
|--------|------|---------|
| `source_url` | `Text` | Git clone URL |
| `source_ref` | `String(64)` | Tracked branch or tag (default: `main`) |
| `installed_commit_sha` | `String(40)` | Exact commit currently on disk |
| `latest_commit_sha` | `String(40)` | Latest remote commit from `git ls-remote` |
| `latest_version` | `String(32)` | Version parsed from remote manifest |
| `update_policy` | `String(16)` | `manual` (default), `auto`, or `pinned` |
| `previous_version` | `String(32)` | Version before last update (for rollback) |
| `previous_commit_sha` | `String(40)` | Commit SHA before last update |
| `previous_image_tag` | `String(128)` | Docker image tag of previous build |
| `changelog` | `JSON` | Parsed `CHANGELOG.md` entries |
| `last_checked_at` | `DateTime` | When `check_update` last ran |

#### Update Policies

| Policy | Behavior |
|--------|----------|
| `manual` (default) | Board UI shows "Update Available" badge; admin must click to apply |
| `auto` | `SkillUpdateWorker` checks every hour and applies updates automatically |
| `pinned` | Update endpoint is rejected unless `force=true` is passed |

#### Blue/Green Update Flow

When `POST /v1/skills/{id}/update` is called:

1. **Acquire Redis lock** `skill:update:{id}` — rejects concurrent updates with `409 Conflict`
2. **Save rollback state** — current version, commit SHA, and image tag are preserved
3. **Pull/checkout new source** — `git fetch && git checkout {target_ref}` (or fresh clone)
4. **Validate manifest** — `id` must still match
5. **Stop old container** — `disable()` frees the container name
6. **Build new image** — `isli/skill-{id}:{new_version}`; old image tagged with `rollback-{timestamp}`
7. **Start next container** — ephemeral port, name `skill-{id}-next`
8. **Probe with retry** — `GET /health` × 12 retries × 2.5s = 30s max; also validates `skill_id` in response
9. **On success**: rename next container to `skill-{id}`, update DB status `active`, emit `skill:updated`
10. **On failure**: remove next container, restart old container, set status `error`
11. **Release Redis lock**

This guarantees the old container stays alive until the new one passes health checks. If the build or probe fails, the skill never goes offline.

#### Rollback Flow

`POST /v1/skills/{id}/rollback` reverses the last update:
1. Check out `previous_commit_sha` in the skill dir
2. Restart the previous image tag container (same blue/green probe)
3. On success: clear rollback fields, set status `active`
4. On failure: leave in error state

#### Auto-Update Worker

`SkillUpdateWorker` runs every hour with two safety gates:
- `last_checked_at` must be older than 30 minutes (`MIN_RECHECK = 1800s`)
- Acquires Redis lock before updating; skips locked skills

Only skills with `update_policy = 'auto'` are processed.

#### Agent SDK — Drain-and-Swap

When a skill is updated, Core emits `skill:updated` via Redis Pub/Sub. The Agent SDK receives this over its WebSocket and sets `_pending_tool_reload = true`. The tool registry is **not** mutated mid-turn. Instead, `_auto_register_tools_from_skills()` runs only after the current ReAct turn completes, preventing schema mismatch errors during tool execution.

#### Board UI Enhancements

The Skills Store page now shows:
- **Version badge** — inline version display; shows "Update Available" (cyan) when `latest_version != version`
- **Update detail modal** — version diff, changelog preview, update policy dropdown, Update Now / Rollback buttons
- **"Check All for Updates"** button — batch refresh of all installed skills

### Legacy Installation Flow (Two-Step)

For programmatic or troubleshooting use, the two-step flow still works:

1. **Install** (`POST /v1/skills/install`) → status `pending`
2. **Enable** (`POST /v1/skills/{id}/enable`) → status `active`

3. **Discovery** (`GET /v1/skills`)
   - Returns static skills + legacy dynamic skills + DB-backed external skills.
   - Agents fetch this at startup for dynamic tool registration.

4. **Auto-Registration**
   - The SDK's `fetch_dynamic_tools()` reads the manifest from Core.
   - For each tool in the manifest, it generates an async invoker that POSTs to `/v1/skills/{id}/{endpoint}`.
   - Tools are registered with LiteLLM automatically.

### Legacy Dynamic Skills (File-System Based)

The previous file-system-based dynamic skill system (code stored in `data/installed_skills/` and `exec()`'d by `isli-skills`) is still supported for backward compatibility. It is managed by `DynamicSkillManager` and listed alongside DB-backed skills in `GET /v1/skills`.

---

## Skill Invocation Flow

- **Service:** `isli-workspace` (not `isli-skills`) — reuses existing `resolve_path()` sandbox and `check_access()` model.
- **Endpoints:** `POST /git/clone`, `/git/status`, `/git/commit`, `/git/push`, `/git/pull`, `/git/branch/list`, `/git/branch/create`, `/git/checkout`, `/git/log`.
- **Proxy Routes:** `POST /v1/skills/git-{operation}/{action}` → proxied by Core to `http://workspace:8300/git/{operation}`.
- **Engine:** [GitPython](https://gitpython.readthedocs.io/) ≥3.1 with async wrappers; `git` binary installed in workspace Docker image.
- **Security:**
  - URL validation rejects `file://` schemes and non-`.git` absolute paths in `git_clone`.
  - All repo paths resolved through `resolve_path()` — path traversal is impossible.
  - No persistent credential storage; agents use HTTPS URLs with embedded tokens or rely on pre-mounted SSH keys.
  - Force-push is not exposed.
  - Atomic clone into temp directory first, then `os.rename()` on success.
- **Typed Exceptions (SDK):** `GitNotRepoError`, `GitAuthError`, `GitConflictError`, `GitRemoteError`, `GitInvalidOperationError` — enables graceful ReAct loop recovery.

**Example Usage (SDK):**
```python
await agent.git_clone(path="repo", url="https://github.com/user/project.git", branch="main")
await agent.git_status(path="repo")
await agent.git_commit(path="repo", message="fix bug")
await agent.git_push(path="repo")
```

---

## Pre-Turn Skill Filtering (Added 2026-06-11)

To minimize token consumption, ISLI does **not** send every assigned skill's metadata to the LLM on every turn. Instead, a lightweight intent classifier decides which skills are relevant.

**Pipeline:**
1. **Compression**: Core builds a compressed skill list for the agent. Each skill is represented by its name + an 8-word hint (from the explicit `hint` field in `skill.yaml`, or truncated from the `description`).
2. **Classification**: The Keeper runs intent classification (same `/session-prep` call for mesh agents; standalone `POST /intent/classify` for legacy agents).
3. **Filtering**: Core forwards `relevant_skills` to the agent runner. The `AgentRunner` sends only the matching tool definitions to the LLM.
4. **Expansion**: If the agent needs a skill not in the filtered set, it calls `discover_skills`. The runner expands the full toolbox for the **next** turn only, then resets.

**Always-visible skills:**
Tools marked with `"x_isli_always_active": true` in their definition bypass filtering. This ensures critical tools like `get_current_datetime` and `discover_skills` are always available.

**Cache:**
The Keeper caches intent classification results in-memory with an LRU (500 entries, 60s TTL). The cache key includes `agent_id + message[:120] + sorted(skill_names)`, so repeated similar queries within a minute skip Ollama inference entirely.

**Fallback:**
If the Keeper returns an empty `relevant_skills` list, or if the classification call fails, the runner falls back to sending the **full** tool set for that turn. This ensures the agent is never left tool-less due to a classifier error.

---

## Skill Invocation Flow

Agents do not call skills directly. All skill calls go through the **Core API skill proxy**:

```
Agent → Core API /api/skills/{skill_id}/invoke (POST)
Core API → validates agent has permission for this skill
Core API → forwards to Skill microservice
Skill microservice → executes, returns JSON
Core API → logs invocation to archive (Tier 4)
Core API → returns response to agent
```

**Streaming visibility** (2026-05-31): When the agent's `streaming_mode` is `tools`, `trace`, or `debug`, the `AgentRunner` emits `tool_call` events (started + done with `duration_ms`) over the agent→Core WebSocket before and after each skill invocation. These events are fanned out to Board clients as `session:stream_event`, rendering `ToolCallBar` cards with a spinner→checkmark transition.

Benefits:
- Central audit log of all skill calls
- Rate limiting enforced at proxy layer
- Skills never know which agent is calling them
- Skills can be hot-swapped without agents knowing

---

## Skill Response Format

External microservice skills return a standard envelope:

```json
{
  "skill_id": "web-search",
  "success": true,
  "data": { ... },
  "error": null,
  "execution_ms": 342,
  "timestamp": "2026-05-10T14:23:00Z"
}
```

Inline handlers (memory skills) and local SDK tools return simpler, domain-specific payloads. For example:

**`memory-save` response:**
```json
{"id": "<uuid>", "collection": "agent_test-agent", "status": "saved"}
```

**`memory-search` response:**
```json
{"ids": [["uuid-1"]], "documents": [["Paris is the capital of France"]], "distances": [[0.21]]}
```

**`summarize-text` response:**
```json
{"summary": "Quick fox jumps over a lazy dog.", "model": "qwen3:1.7b"}
```

On Keeper failure:
```json
{"summary": "<raw input>", "model": "fallback", "note": "Keeper unreachable; returning raw text"}
```

---

## Agent SDK Tool Registry

The `isli-agent-sdk` maintains a central `SKILL_TOOL_REGISTRY` in `isli_agent/tools/__init__.py` that maps normalized skill names to their `(function, definition)` tuples. This registry covers all **built-in** skills:

```python
from isli_agent.tools import SKILL_TOOL_REGISTRY, normalize_skill_name

# Built-in registry includes:
#   "send_message", "shell_exec", "web_fetch", "web_search", ...
```

### Dynamic Tool Loading (Added 2026-06-11)

For **DB-backed external skills** installed via the Universal Skill Runtime, the SDK does not require a code change. At startup, `AgentRunner` calls `fetch_dynamic_tools(core_client)`:

1. Fetches `GET /v1/skills` from Core.
2. For any skill with a manifest containing `tools`, generates an async invoker.
3. The invoker POSTs to `/v1/skills/{skill_id}/{tool_endpoint}` with `agent_id` and the LLM-provided arguments.
4. Registers the tool definition with LiteLLM automatically.

```python
# Inside AgentRunner.start() — runs automatically
await self._auto_register_tools_from_skills()
```

This means agents automatically gain access to newly installed skills on the next heartbeat or config sync event.

### Auto-Registration (Built-In + Dynamic)

```python
# Built-in tools
for skill_name in self.config.skills:
    normalized = normalize_skill_name(skill_name)  # "send-message" -> "send_message"
    if normalized in SKILL_TOOL_REGISTRY:
        func, definition = SKILL_TOOL_REGISTRY[normalized]
        self.add_tool(normalized, func, definition)

# Dynamic tools from installed skills
dynamic_tools = await fetch_dynamic_tools(self.client)
for tool_name, (func, definition) in dynamic_tools.items():
    self.add_dynamic_tool(tool_name, func, definition)
```

### Convenience Methods

```python
runner.add_workspace_tools()  # file_read, file_write, file_list, file_delete
runner.add_channel_tools()    # send_message
runner.add_system_tools()     # get_current_datetime (always auto-registered)
# discover_skills is auto-registered automatically and marked x_isli_always_active
```

### LiteLLM Tool Definitions

All tool definitions (`FILE_READ_DEF`, `SEND_MESSAGE_DEF`, `MEMORY_SAVE_DEF`, `DATETIME_DEF`, etc.) are exported from their respective `isli_agent.tools.*` modules and from the top-level `isli_agent` package for custom registration:

```python
from isli_agent import send_message, SEND_MESSAGE_DEF
```

### Workspace Tools

Each workspace tool is an async function that calls the Core skill proxy and raises typed exceptions on failure:

| Tool | Parameters | Exception (404) | Exception (403) | Exception (413) |
|------|------------|----------------|----------------|----------------|
| `file_read` | `path`, `max_chars`, `line_start`, `line_end` | `WorkspaceNotFoundError` | `WorkspacePathError` | — |
| `file_write` | `path`, `content` | `WorkspaceNotFoundError` | `WorkspacePathError` | `WorkspaceQuotaError` |
| `file_list` | `path` | `WorkspaceNotFoundError` | `WorkspacePathError` | — |
| `file_delete` | `path` | `WorkspaceNotFoundError` | `WorkspacePathError` / `WorkspacePermissionError` | — |

**Note on `file_read` Caps:** The `file_read` tool enforces a hard character limit (default 16,000). If a file is truncated, the response includes `truncated: true` and an enriched notice in the content guiding the agent to use `line_start` for pagination.

These exceptions allow the agent's ReAct loop to recover gracefully instead of crashing on raw HTTP errors.

### Shared Workspace Quota

Unlike per-agent workspaces (hard-coded 100MB default), shared workspaces use a **configurable `quota_bytes`** stored in the `SharedWorkspace` model (default 500MB). Core passes this quota to the workspace service on every `write`, `upload`, and `promote` call. The workspace service rejects the operation with HTTP `413` if the resulting total size would exceed the limit.

### Keeper Tools

`summarize_text` and `embed_text` proxy through Core to `isli-skills`, which forwards to Keeper. If Keeper/Ollama is unreachable, they gracefully degrade:
- `summarize_text` returns the raw input text
- `embed_text` returns an empty embedding list

Both require a valid `JWT_SECRET` on the `skills` service to sign internal auth tokens for Keeper communication.

### Memory Tools

`memory_save`, `memory_delete`, and `memory_search` are handled **inline** in Core's skill proxy router (not via an external microservice). Core reads `agent_id` from the request body and calls `ChromaMemoryClient` directly. Collections are scoped per-agent using the `agent_{id}` naming convention.

### Audio Tools

`speech_to_text` and `text_to_speech` proxy through Core to `isli-audio`:

- **`speech_to_text`**: Accepts an `audio_url` (public URL to an audio file) and optional `language` (e.g., `"en"`, `"fr"`, `"auto"`). Returns a transcription string. The Telegram adapter also uses this internally for voice message auto-transcription before the agent sees the message.
- **`text_to_speech`**: Accepts `text`, optional `voice`, and optional `language`. Returns a URL to the synthesized audio file. If `language` is provided, the audio service selects the appropriate piper voice from the `tts_voices_by_language` mapping.
- **`send_voice_message`** (SDK convenience wrapper): Combines `text_to_speech` + `send_message` into a single call. The agent provides `channel`, `channel_user_id`, and `text`; the SDK synthesizes audio via Core, uploads it to the agent's workspace (`_attachments/audio/...`), and forwards the voice message to the target channel. Supports optional `voice` and `language` parameters.

**Example `speech_to_text` response:**
```json
{"text": "Hello, this is a voice message.", "language": "en", "model": "whisper-tiny"}
```

**Example `text_to_speech` response:**
```json
{"audio_url": "http://audio:8400/tts/output/abc123.wav", "voice": "piper-en-us-lessac-medium", "duration_ms": 2400}
```

**Example `send_voice_message` usage (SDK):**
```python
from isli_agent import send_voice_message

await send_voice_message(
    channel="telegram",
    channel_user_id="123456789",
    text="Welcome to ISLI. How can I help you today?",
    voice="piper-en-us-lessac-medium",
    language="en",
    core_client=client
)
```

Both tools require the agent to have the corresponding skill in its `config.skills` list. Runtime dependency injection handles `agent_id` and `core_client` automatically.

### Interactive Debugger (`interactive-debugger`) — Added 2026-05-30

The interactive debugger gives agents the ability to **set breakpoints**, **inspect variable states during execution**, and **step through code line-by-line** when diagnosing complex bugs. Unlike `test-skill` (which only returns success/failure), the debugger returns a rich execution trace.

**Architecture:** Batch trace model — the agent calls the skill once and receives a complete trace, rather than making dozens of sequential interactive calls.

**Endpoint:** `POST /v1/skills/interactive-debugger/debug` (proxied by Core to `isli-skills:8100/debug`).

**Request parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `code` | string | required | Python code to execute |
| `payload` | object | `{}` | Injected into the namespace as `payload` |
| `breakpoints` | int[] | `[]` | Line numbers to capture detailed state at |
| `mode` | string | `"breakpoints"` | `"trace"` = every line; `"breakpoints"` = only at breakpoints; `"run"` = just final result |
| `max_steps` | int | `1000` | Safety limit; aborts execution if exceeded |
| `max_trace_size` | int | `32768` | Max bytes for trace JSON; stops adding events beyond this |
| `only_changes` | bool | `true` | Only include locals whose value changed vs previous step |
| `include_locals` | bool | `true` | Include local variables in trace events |
| `include_globals` | bool | `false` | Include global variables in trace events |
| `watch_expressions` | string[] | `[]` | Expressions evaluated safely at each recorded step |
| `stdin` | string | `""` | Input fed to the program via `sys.stdin` |

**Response:**
```json
{
  "success": true,
  "trace": [
    {"line": 5, "event": "line", "locals": {"x": "10"}, "watch_results": {"x+y": "15"}, "breakpoint_hit": true, "source_line": "x = 10"}
  ],
  "final_result": "42",
  "exception": null,
  "total_steps": 47,
  "breakpoints_hit": [5],
  "trace_truncated": false,
  "truncation_reason": null,
  "stdout": "hello world\n",
  "execution_time_ms": 125
}
```

**Safety:**
- Same AST forbidden-import whitelist as `test-skill` (`os`, `sys`, `subprocess`, `socket`, `pickle`, `marshal`).
- `max_steps` + `max_time` (30s) prevents infinite loops from consuming resources.
- `safe_repr` caps variable serialization at 256 chars to prevent JSON bloat.
- Watch expressions use a restricted `__builtins__` namespace to prevent arbitrary code execution.
- Dunder variables filtered from dumps.

**SDK usage:**
```python
from isli_agent import interactive_debugger

result = await interactive_debugger(
    code="x = 10\ny = 5\nz = x + y\nresult = z",
    mode="trace",
    breakpoints=[3],
    watch_expressions=["x + y"],
    core_client=client
)
```

### Secret Vault (`get-secret`) — Added 2026-05-31

ISLI provides a **per-agent encrypted secret vault** so agents can access API keys, database credentials, authentication tokens, and encryption keys at runtime without hardcoding them in source code or agent config.

**Architecture:**
- **Storage:** PostgreSQL `secrets` table with `value_encrypted` using existing `PIIEncryption` (AES-256-GCM) under the `PII_ENCRYPTION_KEY` environment variable.
- **Scope:** Strictly per-agent. The `(agent_id, name)` pair has a unique DB index preventing namespace collisions. Agents cannot read other agents' secrets.
- **Access Control:**
  - **Admin write** — `POST /v1/secrets` and `DELETE /v1/secrets/{name}` require `ADMIN_API_KEY`.
  - **Agent read** — `POST /v1/skills/get-secret/get` requires the agent's own JWT (enforced via `agent_id` body parameter matching token `sub`).
- **Audit Trail:** Every `get-secret` read writes an `AuditLog` row with `actor_id`, `secret_name`, and timestamp. The decrypted value is **never** logged, printed, or returned in list endpoints.
- **Board UI:** `/agents/:id/secrets` page lists secret names and metadata; admins can create secrets (value masked) and delete them. Values are never displayed in the UI.

**Endpoints:**
| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | `/v1/secrets` | admin | Create or overwrite a secret for an agent |
| GET | `/v1/secrets?agent_id=` | admin | List secret names/metadata (values never exposed) |
| DELETE | `/v1/secrets/{name}?agent_id=` | admin | Delete a secret |
| POST | `/v1/skills/get-secret/get` | agent JWT | Retrieve decrypted secret value (audit-logged) |

**SDK Usage:**
```python
from isli_agent import get_secret

api_key = await get_secret("openai_api_key", core_client=client)
# Returns the decrypted string value
```

**Typed Exceptions:**
- `SecretNotFoundError` — Secret name does not exist for this agent.
- `SecretAccessError` — Agent lacks permission (rare; usually caught by JWT scoping first).

**Security Design:**
| Concern | Mitigation |
|---------|-----------|
| Encryption at rest | AES-256-GCM via `PIIEncryption` with `PII_ENCRYPTION_KEY` |
| Cross-agent isolation | Unique `(agent_id, name)` DB index + JWT `sub` enforcement |
| Audit trail | Every read logged to `AuditLog`; value never included |
| No source-code leaks | Agents call `get_secret("name")` at runtime; keys live only in encrypted DB |
| No UI exposure | List endpoint returns names only; create form masks value input |

### System Tools

`get_current_datetime` is a pure Python function that uses `datetime.now(timezone.utc)`. No network call, no auth, no external dependency.

### LiteLLM Tool Definitions

All tool definitions (`FILE_READ_DEF`, `SUMMARIZE_TEXT_DEF`, `MEMORY_SAVE_DEF`, `DATETIME_DEF`, etc.) are exported from their respective `isli_agent.tools.*` modules for custom registration.

---

## Adding a Custom Skill

### Option A: External Microservice (Recommended for Production)

1. Create a Python FastAPI microservice (or Node.js/Go/Rust — any HTTP server):

```python
# my-skill/src/main.py
import os
import httpx
from fastapi import FastAPI, Header, HTTPException, Depends
import jwt

app = FastAPI()
JWT_SECRET = os.getenv("JWT_SECRET")

def verify_auth(x_internal_auth: str = Header(...)):
    try:
        payload = jwt.decode(x_internal_auth, JWT_SECRET, algorithms=["HS256"])
        if "skill:proxy" not in payload.get("scopes", []):
            raise HTTPException(status_code=403)
    except Exception:
        raise HTTPException(status_code=401)

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.post("/echo")
async def echo(body: dict, _=Depends(verify_auth)):
    return {"success": True, "echo": body}
```

2. Add `isli-skill.yaml` at repo root (see manifest schema above).
3. Add `Dockerfile` and `requirements.txt`.
4. Publish to a public Git repository.
5. Install via Board UI or admin API:
   ```bash
   curl -H "Authorization: Bearer $ADMIN_API_KEY" \
        -X POST http://core:8000/v1/skills/install \
        -d '{"skill_id":"my-skill","git_url":"https://github.com/user/my-skill"}'
   ```
6. Enable:
   ```bash
   curl -H "Authorization: Bearer $ADMIN_API_KEY" \
        -X POST http://core:8000/v1/skills/my-skill/enable
   ```
7. Skill is immediately available to all permitted agents. No Core or SDK rebuild required.

### Option B: Inline Handler (Core-Native)

For skills that need direct DB access or don't warrant a separate container:

1. Add a handler block in `isli-core/src/isli_core/routers/skills.py` under the inline section.
2. Add metadata to `SKILL_METADATA`.
3. Requires a Core restart (source mounted in dev, image rebuild in production).

### Option C: Legacy Dynamic Skill (Sandboxed Code)

For user-uploaded custom code:

1. Agent generates Python code with `async def run(payload: dict) -> dict:`.
2. Agent calls `test-skill` → AST validation → sandbox execution.
3. On success, agent calls `register-skill` → code saved to workspace.
4. Core's `DynamicSkillManager` loads the code via `exec()` on demand.

**This pattern is deprecated for third-party skills.** Use Option A (External Microservice) for all new skill development.

---

## Skill Evolution (SkillClaw Pattern)

ISLI implements a simplified version of the **SkillClaw collective evolution** concept:

- Skill invocations are logged with success/failure status
- Keeper periodically analyzes failed invocations
- Keeper generates improvement suggestions stored in Tier 3 memory
- Developer reviews suggestions via Kanban board "Skill Reports" tab

This is **advisory**, not automatic — skills don't rewrite themselves. But the signal is surfaced for human-driven improvement.

---

## Large Output Handling

ISLI uses a multi-layered defense to prevent large skill outputs from bloating agent context windows:

1. **Hard Output Caps (First Defense):**
   - `file-read`: Capped at `max_chars=16000` (max 64,000). Returns enriched truncation notice with line-range hints for pagination.
   - `db-query`: Capped at `max_rows=50` and `max_cell_chars=500`. Returns `has_more` flag.
   - `git-log`: Capped at `max_chars=12000` to prevent large diffs from `--patch` or `--stat` calls from exhausting context.
   - All capped skills return `truncated: true` and an explicit `truncated: false` on success.

2. **Keeper Summarization (Second Defense):**
   When a skill (like `web-fetch` or `web-browse-snapshot`) returns a large payload that exceeds the token threshold:
```
Skill returns large payload to Core API
Core API detects payload > token_threshold (default: 2000 tokens)
Core API calls Keeper /summarize with payload
Keeper summarizes to ≤ 500 tokens
Core API returns summary to agent
Core API stores full payload in Tier 4 archive

Agent receives summary, not full text.
Agent can request full text by calling skill again with `format: full`.
```

This prevents skill outputs from bloating agent context windows.

---

## Skills System Gaps (2026-05-11 Research)

The following gaps were identified during a parallel 12-agent research review:

### Critical
- **Skills have no internal auth or network isolation** — **Partially Fixed 2026-06-07**. `shell-exec` provides network isolation and non-privileged execution in a dedicated container. Other skills still lack granular network isolation.
- **`web-fetch` lacks SSRF protections** — no URL blocklists, private IP filtering, or DNS rebinding checks.

### High
- **`db-query` "read-only" not enforced at DB layer** — relies solely on skill code; a bug could allow `DELETE` or `DROP`.
- ~~**No retry policies with exponential backoff**~~ — **Fixed 2026-05-30**. `isli_core/retry.py` provides `exponential_backoff` with jitter; wired into the skill proxy at `routers/skills.py:351` for downstream skill failures.
- **No structured skill-level observability** — no per-skill latency percentiles, error rates, or payload size logging.

### Medium
- ~~**`file-write` path scoping undocumented**~~ — **Fixed 2026-05-19**. Workspace sandbox (`isli-workspace/src/isli_workspace/sandbox.py`) enforces path traversal blocking via `resolve_path()` + `_ensure_within_workspace()`. Directory deletion is blocked; file size limit is 10 MB; workspace quota is 100 MB.
- **Skill evolution (SkillClaw) is advisory only** — no automated validation that improvement suggestions actually improve outcomes.
- **No per-skill rate limiting** — `rate_limit: 20/minute` in manifest but no enforcement code shown.

> See `Memory/ISLI-Research-Report.md` for full details and recommendations.