# 01 — ISLI System Architecture

## Overview

ISLI is built as a **layered, event-driven multi-agent system**. The architecture inverts the common pattern: instead of a powerful orchestrator model dispatching to weak workers, ISLI uses a *silent local Keeper* for all background intelligence, and lets each agent be sovereign within its domain, communicating through a shared Kanban board.

---

## Architecture Layers

```
╔══════════════════════════════════════════════════════════════════╗
║  LAYER 5 — PRESENTATION                                         ║
║  React Kanban UI  ·  Observability Hub (/logs)  ·  Workspaces  ·  Shared Workspaces  ·  Notification Inbox  ║
╚══════════════════════════════════════════════════════════════════╝

║  LAYER 6 — MANAGEMENT                                           ║
║  Unified isli CLI  ·  Bootstrap Installer  ·  Backup/Restore  ·  Update Sequence  ║
╚══════════════════════════════════════════════════════════════════╝
```

---

## Component Map

### Management CLI (`isli`)
- **Runtime**: Python 3.12 (via isolated venv)
- **Responsibilities**:
  - Unified entry point for all operational tasks.
  - Interactive setup wizard for secret generation and environment config.
  - Hardened update sequence with automatic pre-update backups.
  - Data protection (PostgreSQL dump + workspace tar).
  - Environment reset with safety-gated destruction.
  - See `14-management-cli.md` for details.

### Core API (`isli-core`)
- **Runtime**: Python 3.12 + FastAPI + Uvicorn
- **Responsibilities**:
  - Agent registration and lifecycle management
  - Agent process management (spawning, monitoring, termination, restart, and image rebuild)
  - Task creation and state transitions
  - WebSocket event bus (agent → UI)
  - Skill invocation proxy
  - Auth (JWT-based, per agent)
  - Provider registry and permitted-model management
  - Settings management (API keys, model allow-lists)
  - **Notification Engine** (added 2026-06-01): Unified event-to-notification pipeline with preference-aware routing, quiet hours, digest batching, and Telegram escalation
  - **Scheduler Worker** (added 2026-06-02): Background job for one-time and recurring task activation. Handles atomic cloning for cron-based tasks.
  - **Audit Logging**: Cryptographically signed audit trail for system-level changes.
- **Startup Architecture** (refactored 2026-06-04): `main.py` is a thin app factory (~80 lines). All startup logic lives in the `startup/` package:
  - `startup/infra.py` — signal handling, shutdown coordination
  - `startup/notifications.py` — outbox handler registration
  - `startup/agents.py` — `AgentProcessManager` initialization, stuck-agent reset, container reconciliation, online-agent restart
  - `startup/workers.py` — `WorkerManager` that data-drives all 16 background loops via a single `_WORKER_SPECS` list
  - `startup/__init__.py` — FastAPI `lifespan` context manager orchestrating the above
- **Health Router** (refactored 2026-06-04): All `/health`, `/ready`, `/live`, and `/metrics` endpoints (v1 + legacy) live in `routers/health.py`.

### The Keeper (`isli-keeper`)
- **Runtime**: Python process → Ollama (local)
- **Responsibilities**: See `02-keeper.md`
- Runs as a **sidecar** to the Core API
- Never exposed to users or external channels

### Agent Runtime (`isli-agent`)
- Each agent is a **standalone Python process** running inside a Docker container (or directly on the host in native mode), managed and spawned by `isli-core`'s internal Process Manager.
- Connects to Core API via REST + WebSocket
- Has a unique `agent_id`, `agent_name`, `model_config`, `channel_config`
- Receives its **fully resolved API key** via `GET /v1/agents/{id}/config` (agent-scoped JWT)
- Gets pre-hydrated context from Keeper before each task execution
- **Model Routing (2026-05-31)**: When enabled, the agent receives a dynamically routed model (chosen by the Keeper based on task complexity) instead of its static default. The runner uses explicit fallback: routed → default → halt.

### Dashboard & Observability Hub (`isli-board`)
- **Frontend**: React + TypeScript + Vite + TailwindCSS
- **Backend**: Core API WebSocket endpoint
- **Kanban Board**: Real-time task card streaming via SSE/WebSocket. Columns: `Inbox → Assigned → In Progress → Blocked → Done → Archived`.
- **Observability Hub (`/logs`)**: Centralized dashboard for real-time diagnostic streams, audit trails, and memory journals. Follows the **Industrial** design anchor.

### Skills Registry (`isli-skills`)
- HTTP microservices (no AI, no API keys)
- Registered via YAML manifests
- Discoverable by agents at runtime
- Examples: web-fetch, pdf-extract, file-write, db-query, send-email

### Channel Gateway (`isli-channels`)
- Each channel is a thin adapter that forwards messages to a specific agent
- Telegram adapter (`python-telegram-bot`), Web Chat, Email
- Proxies WhatsApp requests to a dedicated Node.js sidecar
- See `07-channels.md`

### WhatsApp Sidecar (`isli-whatsapp-sidecar`)
- **Runtime**: Node.js + Express + `@whiskeysockets/baileys`
- **Responsibilities**:
  - Handles the complex WhatsApp Noise handshake and Protobuf schema
  - Maintains persistent WebSocket connections to WhatsApp servers
  - Manages per-agent session credentials (`creds.json`)
  - Forwards incoming messages and connection updates to `isli-channels` via authenticated webhooks (`X-Sidecar-Secret`)
  - Authenticates inbound REST calls via `Authorization: Bearer` middleware
  - Implements graceful shutdown (`SIGTERM`/`SIGINT`) to close sockets cleanly

### Notification System (Added 2026-06-01)

ISLI includes a **unified notification layer** that converts internal Redis events into user-facing alerts across multiple channels.

**Architecture:**
- **Single Redis consumer**: The existing `redis_listener` in `ws.py` dispatches events to both the Board WebSocket fan-out and the `NotificationEngine` via `asyncio.gather(..., return_exceptions=True)`. No second Redis connection is needed.
- **DB-as-authority**: PostgreSQL `notifications` and `notification_preferences` tables store all state. Redis is used only as a best-effort cache (5-min TTL) with anti-drift pattern.
- **Outbox delivery**: Durable `Outbox` pattern with `deliver_in_app` and `deliver_external` handlers, retry logic, and dead-letter status.

**Event Map** (examples):
| Event | Category | Channels | Recipient |
|-------|----------|----------|-----------|
| `agent:crash` | critical | in_app + telegram | agent owner |
| `task:completed` | high | in_app + telegram | task creator |
| `system:alert` | derived from payload | in_app + telegram | alert target |

**Features:**
- **Preference resolution**: Cached in Redis (`notif:pref:{user_id}`, 1h TTL). Global toggle, quiet hours (timezone-aware via `zoneinfo`), per-category overrides, exception list.
- **Quiet hours**: Non-critical events are suppressed during configured windows. Critical events always bypass.
- **Rate limiting**: `notif:agent_rate:{agent_id}:{user_id}` sliding window — max 20 agent-generated notifications per hour per user.
- **Digest batching**: Low-priority events accumulate in Redis lists (`notif:batch:{user_id}:low`) and are collapsed into summary digests by `DigestWorker` using `LRANGE` + `LTRIM` for idempotency.
- **Telegram escalation**: External channel delivery formats text as `🔔 *title*` with `parse_mode="Markdown"`. Presence suppression skips non-critical events if user hasn't read recent messages.

**Board UI:**
- `NotificationBell.tsx` — bell icon with red unread badge
- `NotificationDrawer.tsx` — slide-out inbox with all/unread/read filters, mark-all-read, per-row dismiss
- `DigestPage.tsx` — standalone `/digests` route for batched summaries
- `NotificationPreferences.tsx` — `/settings/notifications` with global toggle, quiet hours, timezone validation, per-category toggles

**REST Endpoints (`/v1/notifications`):**
| Method | Path | Purpose |
|--------|------|---------|
| GET | `?filter_status=` | List notifications (all/unread/read) |
| GET | `/unread-count` | Unread count (DB authority, Redis cache) |
| POST | `/{id}/read` | Mark single notification read |
| POST | `/read-all` | Mark all read |
| DELETE | `/{id}` | Dismiss notification |
| GET | `/preferences` | Get preferences |
| PATCH | `/preferences` | Update preferences (with `ZoneInfo` validation) |
| POST | `/send` | Agent-facing endpoint (`notify_user` SDK tool) |

---

### Audio Processing (`isli-audio`)
- **Runtime**: Python 3.12 + FastAPI
- **Responsibilities**:
  - Local speech-to-text (STT) via **faster-whisper** (CTranslate2, CPU-optimized `int8` quantization)
  - Local text-to-speech (TTS) via **piper-tts** (ONNX Runtime)
  - Model slot management (`stt` / `tts`) persisted to JSON — same lifecycle UI as Keeper's `gen`/`embed` slots
  - Per-language voice mapping (`tts_voices_by_language`) for multi-language TTS (e.g., Darija, French)
  - Multipart/form-data upload endpoint for inbound audio (e.g., Telegram voice messages)
  - Admin endpoints (`/admin/activate`, `/admin/pull`, `/admin/remove`) proxied by Core
- **Access**: JWT-verified (`python-jose`); never exposed externally. Core proxies agent skill calls and adapter transcription requests.
- **Port**: `8400` (Docker Compose service name: `audio`)

### Workspace Manager (`isli-workspace`)
- **Runtime**: Python 3.12 + FastAPI
- **Responsibilities**:
  - Sandboxed file management for agents (`agent` scope)
  - Task attachment storage (`attachment` scope, `_attachments/{task_id}`)
  - Shared collaborative workspaces (`shared` scope, `_shared/{workspace_id}`)
  - Quota enforcement per scope: 100MB default for agent scopes, configurable `quota_bytes` per shared workspace (default 500MB)
  - Secure file read/write/list/delete operations
  - File promotion across scopes (agent → attachment, agent → shared)
- **Access**: Proxied via `isli-core` with path traversal validation and member/ownership checks for shared workspaces.

---

## Data Flow: User Message → Agent Response

```
User sends message via Telegram
         │
         ▼
Telegram Channel Gateway
  → parses update
  → creates Task in Core API (status: inbox)
         │
         ▼
Core API
  → emits Kanban event (card appears on board)
  → notifies assigned agent via WebSocket
         │
         ▼
Keeper (pre-turn)
  → fetches pre-computed **Structured Session Journal** from Tier 1 memory
  → fetches last 3 raw messages for immediate context
  → fetches relevant episodic/semantic memories via vector search
  → assembles the **Fast-Path Context Block** (no LLM latency)
  → returns: { context_injection, relevant_memories }
         │
         ▼
Agent (e.g., Agent B)
  → receives task + Keeper context injection
  → calls its assigned model API (e.g., Claude, GPT-4o)
  → may invoke Skills (web search, file ops, etc.)
  → produces response
         │
         ▼
Core API
  → task status → Done
  → **JournalWorker** (background) triggers on task completion:
    → calls Keeper to update structured journal incrementally
    → truncates session messages to last 10 turns
  → Keeper stores result summary in episodic memory (Tier 2)
  → Kanban card updated (real-time)
         │
         ▼
Channel Gateway
  → sends response back to user via Telegram
```

### Session Streaming Flow (Added 2026-05-31)

When an agent is configured with a non-`silent` streaming mode, the session reply path emits live events:

```
User sends message
  └─→ Channel Gateway
        └─→ Core API: create/update Session (status: pending_context)
              ├─→ SessionContextInjectorWorker → Keeper context injection
              ├─→ Core emits "session:message" to Agent WebSocket
              └─→ Agent Runner receives event
                    ├─→ phase_start (context_inject)
                    ├─→ turn_start
                    ├─→ LLM generates response
                    │     ├─→ tool_call (started/done)
                    │     └─→ token_delta (chunked text)
                    ├─→ draft_complete
                    ├─→ cost_report
                    ├─→ turn_end
                    └─→ reply_to_session(text)
                          └─→ Agent WS loop emits "agent:stream_event"
                                └─→ Core WS gateway
                                      ├─→ appends token_delta to Redis draft
                                      ├─→ stores debug_prompt/debug_response in Redis trace
                                      └─→ fans out "session:stream_event" to Board WebSockets
                                              └─→ Board renders StreamingMessageBubble, ToolCallBar, ProcessTracePane
```

**Reconnect resilience:** The Redis draft (`session:{id}:draft`) persists partial text. A Board client reconnecting mid-stream fetches the draft via `GET /v1/sessions/{id}/draft` and resumes rendering from the last chunk.

**External channels:** Telegram and WhatsApp adapters only receive the final assembled text via `reply_to_session`. Streaming events are WebSocket-only and do not affect external channel UX.

---

### Board UI Voice Input Flow

When a user clicks the **mic button** in the Board's chat input (`SessionsPage` or `ConversationsPage`):

```
Board UI (Browser)
  → MediaRecorder captures audio (webm/opus)
  → Blob wrapped in FormData
  → POST /v1/stt/transcribe (multipart/form-data)
         │
         ▼
Core API (stt router)
  → Admin auth check (Bearer token)
  → Base64-encodes audio bytes
  → POST AUDIO_URL/stt/transcribe + X-Internal-Auth JWT
         │
         ▼
isli-audio
  → faster-whisper transcribes
  → returns {text, language, confidence, model}
         │
         ▼
Core API
  → returns JSON to Board UI
         │
         ▼
Board UI
  → inserts text into chat input
  → if auto-send ON → submits form → POST /v1/sessions/{id}/message
  → if auto-send OFF → user edits, then submits manually
```

---

## Inter-Agent Communication

ISLI **does not use direct agent-to-agent API calls**. All inter-agent communication goes through the Kanban board via **Task Delegation**:

```
Agent A needs Agent B to do something
  → Agent A creates a new Task card (type: delegation)
  → assigns to Agent B
  → waits for card status = Done (via polling or webhook)
  → reads result from task.output field
```

This design ensures:
- Full audit trail of every agent interaction
- No hidden message passing
- Human can inspect, pause, or redirect any delegation at any time

---

## Process Layout (Single Machine / Dev)

```
isli/
├── isli-core/          ← FastAPI core service (port 8000 internally)
├── isli-keeper/        ← Keeper sidecar (port 8001, isli-mesh only)
├── isli-audio/         ← Audio processing (STT/TTS) (port 8400, isli-mesh only)
├── isli-workspace/     ← Workspace manager (port 8300, isli-mesh only)
├── isli-board/         ← React frontend (served via Traefik, isli-public only)
├── isli-skills/        ← Skill microservices (port 8100, isli-mesh only)
├── isli-channels/      ← Channel adapters (port 8200, isli-mesh only)
├── isli-whatsapp-sidecar/ ← WhatsApp engine (port 3001, isli-mesh only)
└── docker-compose.yml  ← Full stack orchestration (3 networks, secrets, no host ports except Traefik)
```

---

## Security Boundaries

| Boundary | Policy |
|----------|--------|
| Keeper → outside world | **Never exposed**. Localhost only. |
| Audio → outside world | **Never exposed**. Localhost only. JWT-verified. |
| Agent ↔ Core API | JWT per agent. Scoped permissions. `token_issued_at` revocation on token recovery. |
| Skills → Core API | **JWT-verified** (`X-Internal-Auth` header). No empty-JWT god-mode in production. Core signs every proxy request. |
| Channels → Core API | **JWT-verified** (`X-Internal-Auth` header). `require_internal_auth` on `/send`. Webhook secret validation on inbound. |
| Workspace → Core API | **JWT-verified** (`X-Internal-Auth` header). No empty-JWT god-mode in production. |
| Keeper → Core API | **JWT-verified** (`X-Internal-Auth` header). No empty-JWT god-mode in production. |
| User ↔ Board | Session token. HTTPS only in production. |

---

## Network Segmentation (2026-06-03)

Production deployments use **three isolated Docker networks**:

```
isli-public   → Traefik only  (edge ingress, ports 80/443)
isli-mesh     → App services   (east-west traffic: core, keeper, skills, channels, workspace, audio)
isli-data     → Data stores    (postgres, redis, ollama; internal: true)
```

Rules:
- **Data services** attach **only** to `isli-data` — no direct external reachability
- **App services** attach to `isli-mesh` + `isli-data` (pragmatic; full isolation would require a service mesh)
- **Traefik** attaches to `isli-public` + `isli-mesh`
- **Board** attaches to `isli-public` only (static SPA)
- **Only Traefik binds host ports** in production. All internal services are container-network-only.

---

## Secret Management (2026-06-03)

ISLI uses **Docker Compose secrets** for bootstrap credentials. Secret files live in `secrets/` on the host and are mounted into containers as in-memory files under `/run/secrets/`.

| Secret | Used By | Purpose |
|--------|---------|---------|
| `jwt_secret` | core, keeper, channels, skills, workspace, audio | HS256 JWT signing/verification for all inter-service auth |
| `admin_api_key` | core | Board UI admin authentication |
| `pii_encryption_key` | core | AES-256-GCM for PII archive columns |

Each service's `config.py` uses a `@field_validator(mode="before")` that reads file paths starting with `/run/secrets/` and returns the file contents. `startup_validation.py` resolves the same paths before Pydantic loads to avoid short-circuit failures.

---

## Dynamic Runtime Configuration

ISLI exposes operational tuning knobs through a **database-backed settings store** with an in-memory cache. This allows administrators to change runtime behavior (timeouts, retry policies, circuit breaker thresholds) via the Board UI without redeploying.

### `SystemSetting` Store

| Field | Type | Purpose |
|-------|------|---------|
| `key` | `VARCHAR(128)` PK | Setting identifier (e.g. `session_idle_timeout_minutes`) |
| `scope` | `VARCHAR(32)` | Grouping tag (`general`, `provider`, etc.) |
| `value` | `JSON` | Scalar or structured value (int, float, string, list) |
| `description` | `TEXT` | Human-readable help text shown in UI |
| `updated_at` | `TIMESTAMPTZ` | Last mutation timestamp |
| `updated_by` | `VARCHAR(64)` | Actor identifier (for audit trail) |

### Dynamic Config Helper (`dynamic_config.py`)

A 30-second TTL in-memory cache sits in front of PostgreSQL to avoid hammering the DB on hot paths:

```python
async def get_setting(session, key, scope="global", default=None) -> Any
```

- **Priority**: Env vars (via `pydantic-settings`) take highest precedence. If unset, the helper reads from `SystemSetting`. If the row is missing, the hardcoded module-level constant is used as final fallback.
- **Invalidation**: `PUT /v1/settings/{key}` and `DELETE /v1/settings/{key}` call `invalidate_cache()` so the next read fetches fresh data.

### Exposed Operational Knobs (General Settings)

The **General Settings** page (`/settings/general` in the Board UI) exposes 12 runtime-tunable parameters:

| Setting | Default | Consumed By |
|---------|---------|-------------|
| `session_idle_timeout_minutes` | `30` | `SessionCronJob` |
| `task_lease_minutes` | `30` | `CheckpointRecoveryWorker` |
| `delegation_max_depth` | `3` | `tasks.py` router |
| `delegation_approval_depth` | `2` | `tasks.py` router |
| `cors_origins` | `""` | `main.py` lifespan (at startup) |
| `default_max_retries` | `3` | `exponential_backoff()` callers |
| `default_base_delay_seconds` | `1.0` | `exponential_backoff()` callers |
| `default_max_delay_seconds` | `60.0` | `exponential_backoff()` callers |
| `circuit_breaker_failure_threshold` | `5` | `CircuitBreaker` constructor (at call sites) |
| `circuit_breaker_recovery_timeout` | `30.0` | `CircuitBreaker` constructor (at call sites) |
| `bulkhead_max_queue` | `100` | `BulkheadRegistry.get_or_create()` |
| `bulkhead_timeout_seconds` | `10.0` | `BulkheadRegistry.get_or_create()` |

### Prompt Management (`/settings/prompts`)

Administrators can edit the shared `prompts.yaml` file directly from the Board UI without SSHing into the host. Changes are written to disk by Core, which then triggers Keeper to reload its in-memory cache.

**API endpoints (`isli-core`):**

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/v1/prompts` | admin | Read current prompts.yaml from disk (bypasses cache); returns `last_modified` timestamp from file mtime |
| PUT | `/v1/prompts` | admin | Merge updates into prompts.yaml, write to disk, clear Core cache, trigger Keeper reload. Returns `keeper_reloaded` flag. |

**Safety features:**
- **Optimistic locking**: `PUT` includes `last_modified` (file mtime). If the file was modified since the UI loaded it, Core returns `409 Conflict`.
- **Merge-on-write**: Only keys present in the payload are overwritten. Unknown/new keys in the YAML are preserved, preventing the UI from silently dropping newly added prompts.
- **Best-effort Keeper reload**: Core calls `POST /admin/reload-prompts` on Keeper after writing. If Keeper is restarting, the write succeeds but `keeper_reloaded: false` is returned, and the UI surfaces a warning toast.
- **Agent restart reminder**: The Board UI shows a persistent banner: "Agent runners load prompts at startup. Restart any running agent to apply changes." with a link to `/agents`.

**Board UI:** Three tabs (Keeper | Agent | Core) with structured card editors and a per-tab **Raw YAML** toggle. The Raw mode uses `js-yaml` for round-trip parse/serialize validation.

### Audit Trail

Every mutation writes a cryptographically signed audit log entry via `AuditWriter` (same pattern as provider settings). The audit record captures the old value, new value, actor, and timestamp.

---

## Dynamic Model Management
The system supports dynamic switching of local models via administrative endpoints. Configuration is persisted in `/app/data/model_config.json` (Keeper) and `/app/data/audio_config.json` (Audio), both mounted as Docker volumes.

**Keeper (`gen` / `embed` slots):**
- **Keeper**: Managed via `POST /admin/reload` and `POST /admin/pull` endpoints.
- **Core**: Proxies these requests and enforces concurrent-session validation (blocks switching if active sessions > 0).
- **UI**: Three-state picker (Active/Ready/Download) in Settings.

**Audio (`stt` / `tts` slots):**
- **Audio Service**: `POST /admin/activate`, `/admin/pull`, `/admin/remove` for faster-whisper and piper-tts models.
- **Core**: Routes audio slot requests to `isli-audio` via the same model-management router.
- **UI**: Third module "Audio Processing" (`[KM-03-AUD]`) on `/settings/keeper` with `stt`/`tts` sub-slots and per-language voice mapping.

Both services are managed from the same Board UI page (`/settings/keeper`).
EOF

The following gaps were identified during a parallel 12-agent research review. They represent the delta between documented architecture and production readiness:

### Critical
- ✅ ~~**Hardcoded service discovery**~~ — Resolved 2026-06-03. `SKILL_REGISTRY` consolidated from ~25 env vars to 4 upstreams (`SKILLS_URL`, `WORKSPACE_URL`, `AUDIO_URL`, `CHANNELS_URL`) + `ServiceDiscovery` utility in `isli-core/src/isli_core/discovery.py`.
- **No event schema registry** — WebSocket and Redis payloads are unversioned and unenforced.
- **Task state race conditions** — concurrent PATCH updates from agents and humans lack optimistic locking.
- ✅ ~~**Broken Docker networking**~~ — Resolved 2026-06-03. `docker-compose.yml` uses Compose service names (`postgres`, `redis`, `keeper`, `core`, etc.) with `docker-compose.override.yml` for dev overrides. `.env.example` documents both native dev (`localhost`) and Docker (`service-name`) modes.

### High
- **Missing backpressure/circuit breakers** on the Kanban event bus and WebSocket fan-out.
- **No API versioning contract** between Core API and agents.
- **Distributed tracing treated as optional** — OpenTelemetry is listed as "or Langfuse" rather than mandatory.
- ✅ ~~**Unauthenticated internal skill network**~~ — Resolved 2026-06-03. All inter-service calls now carry `X-Internal-Auth` JWTs. Empty-JWT god-mode fallback removed in production. Dev-mode bypass only activates when `ISLI_ENV=development` AND no header is present.

### Medium
- ✅ ~~**No load balancer or service mesh**~~ — Partially resolved 2026-06-03. Traefik is the edge LB. Application-layer auth + network segmentation (`isli-public` / `isli-mesh` / `isli-data`) replaces the need for a mesh on single-host Docker Compose. See `Docs/15-service-mesh-backlog.md` for when to revisit mTLS.
- **No graceful shutdown / connection draining** — in-flight tasks can lose state on restart.

> See `Memory/ISLI-Research-Report.md` for full details and recommendations.