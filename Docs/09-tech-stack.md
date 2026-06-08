# 09 — Technology Stack

## Stack Summary

```
Layer               | Technology
--------------------|---------------------------------------------
Local AI            | Ollama (runtime) + dynamic gen/embed models via ModelManager
Local STT           | faster-whisper (CTranslate2, CPU int8)
Local TTS           | piper-tts (ONNX Runtime)
Vector Store        | ChromaDB (local, embedded)
Core API               | Python 3.12 + FastAPI + Uvicorn
Task Queue             | Redis (pub/sub + stream)
Push Notifications     | Web Push API (pywebpush, py-vapid)
Primary Database       | PostgreSQL 16 (pgvector extension)
Session Cache          | Redis
Agent SDK              | Python (custom, minimal)
Frontend            | React 18 + TypeScript + Vite + TailwindCSS
WebSocket           | FastAPI native WebSocket
Container           | Docker + docker-compose
Tracing/Observ.     | Langfuse (self-hosted) or OpenTelemetry
Channels            | python-telegram-bot, pyaileys, Twilio SDK, smtplib
Browser Automation  | Playwright (async API, Chromium headless)
PII Mesh            | Keeper SLM (Ollama) + regex pre-filter + local re-hydration
Workspace VCS       | GitPython (libgit2 bindings) + system `git` binary
```

---

## Why These Choices

### Python + FastAPI (Core API)
- **Reason**: Python has the richest AI/LLM ecosystem. FastAPI is the de-facto standard for async AI agent backends in 2026.
- **Benchmarks**: FastAPI handles 15,000–20,000 req/s — vastly more than needed.
- **Async-first**: Critical for WebSocket management and concurrent agent handling.
- **Type safety**: Pydantic models prevent malformed payloads from reaching agents.
- **Alternative considered**: Go (faster but no AI ecosystem), Node.js (fine but Python is better for AI-adjacent code).

### Ollama (Local Model Runtime)
- **Reason**: One-command model management. Supports all major quantized models. REST API at `localhost:11434`. No Python dependency conflicts.
- **Key models used**:
  - `nomic-embed-text` (274MB, 8K context, best local embedding quality)
  - Default generation: `qwen3:1.7b` (summarization, JSON output, fast CPU inference); switchable via Board UI
- **Optimizations**:
  - `OLLAMA_KEEP_ALIVE=-1`: Permanent memory loading to eliminate cold-start lag.
  - `OLLAMA_NUM_THREADS=8`: Pinning to half of available cores for balanced performance.
  - `num_ctx: 4096`: Optimized context window for CPU throughput.
- **Alternative considered**: llama.cpp directly (more control but more ops overhead).

### faster-whisper (Local STT)
- **Reason**: CPU-optimized Whisper implementation via CTranslate2. `int8` quantization gives real-time transcription on consumer hardware. No GPU required.
- **Key models used**:
  - `whisper-tiny` (39MB, fastest, good for short voice messages)
  - `whisper-base` (74MB, better accuracy for longer audio)
- **Integration**: Lives in `isli-audio` service. Telegram adapter uploads voice messages via multipart/form-data to `/stt/transcribe`. Agents can also call `speech-to-text` explicitly.
- **Alternative considered**: OpenAI Whisper API (cloud, costs money); Ollama does not natively support Whisper.

### piper-tts (Local TTS)
- **Reason**: Lightweight, high-quality neural TTS using ONNX Runtime. Voices are ~50–150MB each. Runs entirely offline.
- **Key models used**:
  - `piper-en-us-lessac-medium` (default English voice)
  - Additional voices downloaded on-demand from HuggingFace
- **Integration**: Lives in `isli-audio` service. Agents call `text-to-speech` via Core skill proxy. Language-aware voice selection via `tts_voices_by_language` mapping.
- **Alternative considered**: Coqui TTS (larger, slower); Azure/Google TTS (cloud, costs money).

### Playwright (Browser Automation)
- **Reason**: The industry-standard browser automation library. Supports headless Chromium with full JavaScript execution, accessibility tree snapshots, and persistent browser contexts (cookies/localStorage survive across calls).
- **Architecture**: Lives in `isli-skills` service. Each agent gets a `BrowserContext` via `launch_persistent_context(user_data_dir=...)`. Sessions are in-memory (Playwright objects can't be serialized); Redis used only for TTL heartbeats.
- **Key features used**:
  - `page.accessibility.snapshot()` — accessibility tree for compact text representation
  - `page.goto(wait_until="networkidle")` — full JS-rendered page loads
  - `page.keyboard.press()` — key input for form submission
  - `page.screenshot()` — base64 PNG for vision fallback
  - `page.on("console", ...)` — continuous JS log capture
- **Snapshot format**: Hermes-style compact text with `@eN` ref IDs on interactive elements. Default `full=false` returns only actionable nodes; `full=true` includes all semantic content.
- **Resource limits**: `BROWSER_MAX_CONCURRENT_SESSIONS=5` per `isli-skills` instance; memory limit bumped to `1G` for Chromium.
- **Alternative considered**: Selenium (heavier, slower), Puppeteer (Node-only), browser-use (higher-level but less granular control).

### ChromaDB (Vector Store)
- **Reason**: Embedded mode (no server needed). Python-native. Excellent for local deployment. Supports cosine similarity + metadata filtering.
- **Why not Weaviate/Qdrant?**: Overkill for a personal/small-team assistant. ChromaDB runs in the same process.
- **Why not PostgreSQL pgvector only?**: pgvector is good for archival but ChromaDB gives better ANN performance for real-time retrieval.

### PostgreSQL 16 (Primary Database)
- **Reason**: The proven choice for durable state in AI agent systems. JSON/JSONB support for flexible task payloads. `pgvector` extension for storing dense embeddings alongside relational data (episodic memory).
- **pgvector**: Used for episodic memory semantic search (Tier 2). Implemented using cosine similarity (`<=>`) retrieval.

### Redis (Cache + Event Bus)
- **Reason**: Session memory (Tier 1) needs sub-millisecond reads. Pub/Sub for real-time Kanban events. Stream for task queue.
- **Redis Streams**: Used for task event broadcasting to all connected WebSocket clients.
- **Redis Pub/Sub**: Used for agent heartbeat events.
- **Redis Hash**: Used for session message buffers (with TTL).
- **Redis Blob Store (DB 10)** (Added 2026-06-07): Dedicated database index for transient binary data (audio, screenshots) and persistent binary identity data (agent avatars). Uses opaque tokens to implement the Claim Check pattern, reducing network and logging overhead.
- **Redis Draft + Debug Trace** (2026-05-31): `session:{id}:draft` stores partial streaming text for reconnect resilience. `session:{id}:debug_trace` stores `debug_prompt`/`debug_response` events (admin-only REST access, never broadcast over WS).

### React + TypeScript + Vite (Board Frontend)
- **Reason**: Best DX for real-time UIs. Vite gives fast dev builds. TypeScript prevents UI bugs from bad API responses.
- **@dnd-kit**: Lightweight drag-and-drop for Kanban. No heavy framework.
- **TailwindCSS**: Rapid UI development without fighting CSS.
- **Lucide React**: Comprehensive icon set used for system observability and navigation.
- **Framer Motion**: Used for fluid animations, including the "stagger-in" transitions in the Observability Hub.
- **Streaming Components** (2026-05-31): `StreamingMessageBubble` (monospace text + blinking cursor), `ToolCallBar`/`ToolCallCard` (spinner→checkmark), `ProcessTracePane` (collapsible timeline) — all driven by WebSocket `session:stream_event` events.
- **Prompt Management** (2026-05-31): `PromptsPage.tsx` with per-tab structured/raw-YAML editing using `js-yaml` for round-trip parse validation; `usePrompts` / `useUpdatePrompts` TanStack Query hooks.
- **Why not Next.js?**: ISLI board is a single-page app talking to a local API. No SSR needed.


### Docker + docker-compose
- **Reason**: Every component runs in isolation. Easy to start all services with one command. Keeps your PC clean.
- **Not Kubernetes**: ISLI targets single-machine deployment. K8s would be overkill.

### Langfuse (Observability)
- **Reason**: Open-source LLM observability. Traces every agent turn, token usage, latency. Self-hosted.
- **Alternative**: OpenTelemetry + Jaeger (more generic, less LLM-focused).

---

## Dynamic Configuration

### `SystemSetting` Model

Stored in PostgreSQL with a JSON `value` column (accepts scalars or objects) and indexed by `scope`:

```python
class SystemSetting(Base):
    __tablename__ = "system_settings"
    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    scope: Mapped[str] = mapped_column(String(32), default="global")
    value: Mapped[Any] = mapped_column(JSON, default=dict)
    description: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_by: Mapped[str | None] = mapped_column(String(64))
```

### Dynamic Config Helper

`isli-core/src/isli_core/dynamic_config.py` provides:

- `get_setting(session, key, scope="global", default=None)` — DB read with 30s in-memory TTL cache
- `invalidate_cache(key, scope)` — Cache invalidation on mutation

**Read priority (highest → lowest)**:
1. Environment variable (via `pydantic-settings` in `config.py`)
2. `SystemSetting` row in PostgreSQL
3. Hardcoded module-level constant (fallback)

### Settings API Endpoints

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/v1/settings` | admin | List all settings; `?scope=general` filters |
| GET | `/v1/settings/{key}` | admin | Get single setting |
| PUT | `/v1/settings/{key}` | admin | Upsert value; writes audit log; invalidates cache |
| DELETE | `/v1/settings/{key}` | admin | Remove row → revert to code default |

### Prompts API Endpoints (2026-05-31)

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/v1/prompts` | admin | Read `prompts.yaml` from disk; returns `keeper`, `agent`, `core` sections + `last_modified` |
| PUT | `/v1/prompts` | admin | Merge payload into existing YAML, write to disk, clear Core cache, trigger Keeper reload. Returns `keeper_reloaded` + new `last_modified`. `409` on mtime conflict. |

### Board UI — General Settings

`isli-board/src/components/GeneralSettingsPage.tsx` renders grouped sections:

- **Session & Delegation** — timeouts and depth limits
- **Resilience & Retries** — retry count, base/max delay, circuit breaker knobs
- **Load Management** — bulkhead queue size and timeout
- **CORS Origins** — comma-separated allowed origins

Each field is a debounced native input backed by `useUpdateSetting()` mutation (TanStack Query). Mutations invalidate the `['settings']` query cache.

### Board UI — System & Environment Settings (Added 2026-06-07)

`isli-board/src/components/SystemSettingsPage.tsx` (`/settings/system`) provides:

- **PII Mesh Defaults** — `pii_mesh_default_enabled`, `pii_use_slm_default`, `pii_regex_pre_filter`, `pii_token_ttl_hours`
- **Infrastructure** — `keeper_timeout_seconds`, `agent_spawn_timeout_seconds`

All settings are toggle switches or numeric inputs backed by `useUpdateSetting()` with the same TanStack Query invalidation pattern as General Settings.

### Board UI — Prompts Management

`isli-board/src/components/PromptsPage.tsx` (`/settings/prompts`) provides:

- **Three tabs** — Keeper, Agent, Core
- **Structured cards** — one textarea per prompt with monospace font
- **Per-tab Raw YAML toggle** — switches to a single raw editor; `js-yaml` validates on switch-back; parse errors block the toggle
- **Agent restart banner** — persistent reminder that agent runners load prompts at startup
- **Dirty detection** — Save button disabled until changes exist; Discard reverts to server state
- **409 conflict modal** — if another process modified the file, the UI prompts to refresh
- **Keeper reload warning** — toast if file saved but Keeper could not be notified

---

## Model Management

The stack includes a full model lifecycle system for local models:

**Core API (`isli-core`):**
- `GET /v1/model-management/status` — current active models, permitted list, available list
- `POST /v1/model-management/pull` — download and activate a model
- `POST /v1/model-management/activate` — switch active model without re-downloading
- `POST /v1/model-management/remove` — delete a model

**Keeper (`isli-keeper`) — `gen` / `embed` slots:**
- `GET /admin/config` — runtime model config
- `POST /admin/activate` — set active model for a slot
- `POST /admin/remove` — delete from Ollama with fallback validation
- `POST /admin/pull` — download and set active model

**Audio (`isli-audio`) — `stt` / `tts` slots:**
- `GET /admin/config` — runtime audio config (STT model, TTS model, language, voice mapping)
- `POST /admin/activate` — set active model for `stt` or `tts` slot
- `POST /admin/remove` — delete a piper voice or whisper model
- `POST /admin/pull` — download and set active model

**Board UI (`isli-board`):**
- `/settings/keeper` page with three modules: Local Generation (`[KM-01-GEN]`), Local Embeddings (`[KM-02-EMB]`), and Audio Processing (`[KM-03-AUD]`)
- Model cards showing active/available/missing states
- Activate, Remove, and Download actions per model
- Global "Pull in progress" guard

### Model Routing (Added 2026-05-31)

When enabled per agent, ISLI dynamically routes tasks and sessions to the most cost-effective model from a user-defined secondary list:

**Core Heuristic Scorer (`isli-core`):**
- `TaskComplexityScorer.score_task_input()` — fast zero-cost analysis using keyword matching + message length heuristics
- Returns `complexity_score` (0.0–1.0) and `complexity_tier` (`local` | `standard` | `premium`)
- `filter_models_by_tier()` drops models whose `cost_tier` is strictly more expensive than the computed tier

**Keeper LLM Router (`isli-keeper`):**
- `POST /model/route` — receives prose-formatted task description, score, tier, and filtered model list
- Uses the local generation model (default `qwen3:1.7b`) to return `{provider, model_id, reason}` JSON
- Core validates the returned `model_id` against the agent's `secondary_models` whitelist

**Agent SDK (`isli-agent-sdk`):**
- `_resolve_model(config, routed)` — builds LiteLLM model string from routed or default config
- `_model_with_fallback()` — explicit three-tier fallback: routed → default → halt
- Startup guard requires `model_provider` and `model_id` to be non-null

**Parallel execution:** The routing call runs in `asyncio.gather()` alongside context injection, adding zero wall-clock latency to the critical path.

---

## Dependency Summary

### `isli-core` (Core API)
```
fastapi==0.115.x
uvicorn[standard]==0.30.x
pydantic==2.x
asyncpg==0.30.x       # async PostgreSQL
redis==5.0.x          # async Redis
chromadb==0.5.x
langfuse==2.x
python-jose[cryptography]  # JWT
httpx==0.27.x         # async HTTP for skill calls
pyyaml==6.0.x         # prompt config loader
```

### `isli-keeper`
```
httpx              # Ollama API calls
chromadb           # vector store
asyncpg            # episodic memory writes
numpy              # embedding operations
fastapi            # keeper internal API
pyyaml==6.0.x      # prompt config loader
```

### `isli-board` (Frontend)
```
react@18
typescript@5
vite@5
tailwindcss@3
@dnd-kit/core
@tanstack/react-query@5
date-fns@3
js-yaml@4          # prompt management raw-YAML editor
```

### `isli-audio` (Audio Processing)
```
faster-whisper     # CTranslate2-based STT
piper-tts          # ONNX-based TTS
fastapi            # admin endpoints
uvicorn            # ASGI server
python-jose        # JWT verification
httpx              # HTTP client
opentelemetry-api  # tracing
```

### Agent SDK
```
httpx              # Core API calls
websockets         # WebSocket connection
pydantic           # config validation
pyyaml             # prompt config loader
litellm            # LLM abstraction layer
google-genai>=0.8.0 # required for Gemini tool calling
anthropic / openai  # other model clients
```

**Tool Call Format Fallbacks (Added 2026-05-29):**
The SDK supports three input formats for tool calls:
1. **OpenAI structured** (`message.tool_calls[]`) — native for GPT-4, Claude API, Gemini
2. **Anthropic-style XML** (`<function_calls>...</invoke>`) — fallback for Qwen 2.5 via Ollama
3. **JSON-in-text blob** (`{"name":"...","arguments":{...}}`) — fallback for models that output raw JSON inline

Both fallback parsers are implemented in `isli-agent-sdk/src/isli_agent/runner.py` using only stdlib (`xml.etree.ElementTree` and `json`). They activate automatically when `message.tool_calls` is empty, validate extracted calls against the registered tool registry, strip markup from the final response, and inject synthetic `tool_calls` into conversation history to preserve LiteLLM replay compatibility.

---

## Environment Variables (`.env`)

```env
# Core API
DATABASE_URL=postgresql://isli:password@localhost:5432/isli
REDIS_URL=redis://localhost:6379
JWT_SECRET=<generate with: openssl rand -hex 32>
KEEPER_URL=http://localhost:8001

# Keeper
OLLAMA_HOST=http://localhost:11434
VECTOR_DB_PATH=./data/vectors

# Langfuse (optional)
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_HOST=http://localhost:3000

# Provider API Keys (legacy fallback; prefer Settings UI)
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
GOOGLE_API_KEY=
OLLAMA_API_KEY=
DEEPSEEK_API_KEY=

# Channels (add as needed)
TELEGRAM_BOT_TOKEN=
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=

# Internal Service Auth (required in production Docker)
WEBHOOK_SECRET=<generate with: openssl rand -hex 32>
SKILL_REGISTRY_TOKEN=<generate with: openssl rand -hex 32>

# Default agent ID for static agent-runner service (optional)
AGENT_ID=kimi-02

# WhatsApp Channel
WHATSAPP_ENABLED=false
SIDECAR_WEBHOOK_SECRET=<generate with: openssl rand -hex 32>
SIDECAR_API_TOKEN=<generate with: openssl rand -hex 32>

# Audio Processing (isli-audio)
AUDIO_STT_MODEL=whisper-tiny
AUDIO_TTS_MODEL=piper-en-us-lessac-medium
AUDIO_LANGUAGE=en

# PII Mesh Defaults
PII_MESH_DEFAULT_ENABLED=false
PII_USE_SLM_DEFAULT=false
PII_REGEX_PRE_FILTER=true
PII_TOKEN_TTL_HOURS=24

# Development
AGENT_SDK_HOST_PATH=         # Absolute host path to isli-agent-sdk/src for live volume mount into agent containers
AGENT_RUNNER_BUILD_CONTEXT=  # Absolute host path to isli-agent-sdk root for Docker image rebuilds
```

---

## Minimum Hardware Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| RAM | 8GB | 16GB |
| GPU VRAM (for Keeper models) | 0GB (CPU mode) | 4GB |
| Disk | 10GB | 50GB |
| CPU | 4 cores | 8+ cores |

The full stack runs comfortably on a developer laptop. The Keeper local models (`qwen3:1.7b` + `nomic-embed-text`) together need ~4GB RAM in CPU mode, ~3GB VRAM in GPU mode. The audio service (`faster-whisper` + `piper-tts`) adds ~500MB RAM and runs well within a 4GB container limit.

---

## docker-compose.yml (Skeleton)

```yaml
services:
  postgres:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_DB: ${POSTGRES_DB:-isli}
      POSTGRES_USER: ${POSTGRES_USER:-isli}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?error}
    volumes: [postgres_data:/var/lib/postgresql/data]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-isli}"]
    networks: [isli-data]

  redis:
    image: redis:7-alpine
    command: redis-server --appendonly yes
    volumes: [redis_data:/data]
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
    networks: [isli-data]

  core:
    build: ./isli-core
    environment:
      ISLI_ENV: production
      DATABASE_URL: postgresql+asyncpg://.../isli
      REDIS_URL: redis://redis:6379/0
      JWT_SECRET: /run/secrets/jwt_secret
      PII_ENCRYPTION_KEY: /run/secrets/pii_encryption_key
      ADMIN_API_KEY: /run/secrets/admin_api_key
      WEBHOOK_SECRET: ${WEBHOOK_SECRET}
      SKILL_REGISTRY_TOKEN: ${SKILL_REGISTRY_TOKEN}
      AGENT_NETWORK: ${COMPOSE_PROJECT_NAME:-isli}_isli-mesh
      SKILLS_URL: http://skills:8100
      WORKSPACE_URL: http://workspace:8300
      AUDIO_URL: http://audio:8400
      PII_MESH_DEFAULT_ENABLED: ${PII_MESH_DEFAULT_ENABLED:-false}
      PII_USE_SLM_DEFAULT: ${PII_USE_SLM_DEFAULT:-false}
      PII_REGEX_PRE_FILTER: ${PII_REGEX_PRE_FILTER:-true}
      PII_TOKEN_TTL_HOURS: ${PII_TOKEN_TTL_HOURS:-24}
    secrets: [jwt_secret, admin_api_key, pii_encryption_key]
    networks: [isli-mesh, isli-data]
    depends_on:
      postgres: { condition: service_healthy }
      redis:    { condition: service_healthy }

  skills:
    build: ./isli-skills
    environment:
      ISLI_ENV: production
      JWT_SECRET: /run/secrets/jwt_secret
      SKILL_REGISTRY_TOKEN: ${SKILL_REGISTRY_TOKEN}
    secrets: [jwt_secret]
    networks: [isli-mesh, isli-data]

  board:
    build: ./isli-board
    networks:
      - isli-public   # Traefik ingress
      - isli-mesh     # Required: nginx proxy_pass to core:8000
    depends_on:
      core: { condition: service_healthy }

  ollama-init:
    image: ollama/ollama:latest
    depends_on:
      ollama: { condition: service_healthy }
    command: "ollama pull qwen3:1.7b && ollama pull nomic-embed-text"
    environment:
      OLLAMA_HOST: ollama:11434
    networks:
      - isli-data
      - isli-mesh   # Required: internet access for model downloads
    restart: 'no'

  # ... (channels, workspace, keeper, audio, traefik)

secrets:
  jwt_secret:
    file: ./secrets/jwt_secret.txt
  admin_api_key:
    file: ./secrets/admin_api_key.txt
  pii_encryption_key:
    file: ./secrets/pii_encryption_key.txt

volumes:
  postgres_data:
  redis_data:

networks:
  isli-public:
    driver: bridge
  isli-mesh:
    driver: bridge
  isli-data:
    driver: bridge
    internal: true
```

---

## Known Infrastructure Gaps (2026-05-11 Research)

The following production-grade infrastructure items were identified during the research review. Many have since been implemented (marked ✅ below).

| Item | Status | Priority | Note |
|------|--------|----------|------|
| `docker-compose.yml` | ✅ **Implemented** | Critical | Full production compose with health checks, resource limits, restart policies, and init containers |
| `.env.example` | ✅ **Implemented** | Critical | `.env.example` and `.env.production` templates at repo root |
| `requirements.txt` / `pyproject.toml` | ✅ **Implemented** | Critical | Every Python service has both `pyproject.toml` (local dev) and `requirements.txt` (Docker) |
| `package.json` (board) | ✅ **Implemented** | Critical | `isli-board/package.json` with exact lockfile (`package-lock.json`) |
| Alembic / Flyway migrations | ✅ **Implemented** | Critical | `isli-core/alembic/versions/` contains 20+ migrations; other services manage schemas on startup |
| Health check endpoints | ✅ **Implemented** | High | `/health` on Core, Keeper, and all skills; `/ready` on Keeper probing Ollama |
| OpenTelemetry instrumentation | ✅ **Implemented** | High | `instrument_fastapi()` helper in every service; Jaeger at `localhost:16686` |
| CI/CD pipeline | ✅ **Implemented** | Medium | `.github/workflows/ci.yml` (lint + test) and `deploy.yml` (multi-service matrix build/push) |
| Terraform / Pulumi IaC | ✅ **Implemented** | Medium | `infra/` contains Terraform modules and Traefik/nginx configs |
| Secret management (Vault / Docker Secrets) | ✅ **Implemented** | High | Bootstrap secrets via Docker Compose secrets (`secrets/` directory, mounted to `/run/secrets/`). Runtime per-agent vault via `get-secret` skill (AES-256-GCM in PostgreSQL). Admin-only Board UI. Every read is audit-logged. |
| Redis AOF persistence | **Missing** | High | `redis:7-alpine` runs without `appendonly`; data loss on unclean shutdown |
| Backup/restore strategy | ✅ **Implemented** | High | Runbooks in `Docs/runbooks/backup-restore.md` with pg_dump, ChromaDB snapshot, and Redis RDB procedures |
| Ollama model pre-pull | ✅ **Implemented** | Critical | `isli-ollama-init-1` init container pulls `qwen3:1.7b` and `nomic-embed-text` before Keeper starts |
| Exact semver lockfiles | ✅ **Implemented** | Critical | `package-lock.json` for board; `requirements.txt` with exact pins for Python services |

### Remaining Gaps (2026-06-03)

| Item | Status | Priority | Note |
|------|--------|----------|------|
| Redis AOF persistence | ✅ **Implemented** | High | `redis:7-alpine` command is `redis-server --appendonly yes`; AOF enabled in `docker-compose.yml` |
| `.env.dev` / `.env.prod` split | ✅ **Implemented** | Medium | `docker-compose.yml` for production; `docker-compose.override.yml` for dev overrides (live mounts, dev ports). `.env.example` documents both modes. |
| Network segmentation | ✅ **Implemented** | High | Three networks (`isli-public`, `isli-mesh`, `isli-data` with `internal: true`) active in both `docker-compose.yml` and `docker-compose.scale-out.yml` |
| Inter-service mTLS | **Deferred** | Medium | Application-layer JWT auth + network segmentation is sufficient for single-host Docker Compose. See `Docs/15-service-mesh-backlog.md` for Kubernetes/Swarm migration path. |

> **Research finding (resolved):** The original skeleton used `localhost` for inter-service URLs. The current `docker-compose.yml` correctly uses Compose service names (`postgres`, `redis`, `keeper`, `core`) with an `.env.example` template that documents both native dev (`localhost`) and Docker (`service-name`) modes.
