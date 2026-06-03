# 02 — The Keeper (Hidden Local Agent)

## What Is the Keeper?

The Keeper is ISLI's **silent backbone**. It is a Python service running a small local Ollama model that performs all background AI work without consuming cloud API tokens. It is never assigned tasks directly, never speaks to users, and never appears on the Kanban board as an active agent.

> Think of it as the brain-stem — not the thinking mind, but the system that keeps everything alive, coherent, and connected.

---

## Recommended Local Models

The Keeper needs to be fast, small, and reliable for structured tasks. Based on current benchmarks:

| Task | Recommended Model | Size | Min Container Memory | Notes |
|------|------------------|------|---------------------|-------|
| Summarization + context compression | `qwen3:1.7b` (default) | ~1.1 GB | 2 GB | Faster, optimized for CPU inference |
| Embeddings | `nomic-embed-text` (default) | ~274 MB | 1 GB | Best local embedding model, 8K context |
| Heartbeat validation (JSON output) | `qwen3:1.7b` (default) | ~1.1 GB | 2 GB | Replaces qwen3:0.6b for better reliability |
| Fallback reasoning | `phi3:mini` (3.8B) | ~2.5 GB | 3.5 GB | Punches above weight |

**Recommended combo for most PCs:**
- Summarization: `qwen3:1.7b` (can be switched dynamically via Board UI)
- Embeddings: `nomic-embed-text` (can be switched dynamically via Board UI)

> **Note:** Ollama loads model weights into container RAM at runtime. The `deploy.resources.limits.memory` value in `docker-compose.yml` must exceed the model size. 

> **Hardware reality check:** On a 16-core CPU environment (ARM aarch64) with GPU passthrough, `qwen3:1.7b` takes **~3-4 seconds for TTFT** and generates at **~15 tokens/sec**. On CPU-only environments, inference can exceed **150 seconds** per call. We use `OLLAMA_KEEP_ALIVE=-1` to ensure models stay in RAM indefinitely, eliminating the 10-30s cold-start penalty. We pin Ollama to **8 threads** to balance speed with system stability.

---

## Keeper Responsibilities

### 1. Embeddings

Every piece of content that enters ISLI memory is embedded by the Keeper using `nomic-embed-text` via Ollama. This includes:
- User messages
- Agent responses
- Task outputs
- Skill results
- Uploaded documents

Embeddings are stored in **ChromaDB** (local vector database).

```python
# Keeper embedding call pattern
POST http://localhost:11434/api/embed
{
  "model": "nomic-embed-text",
  "input": "<text to embed>"
}
```

### 2. Context Injection (Fast-Path)

Before any agent executes a task, the Keeper is called to produce a **context injection block**. Unlike standard RAG, ISLI uses a **pre-computed fast-path** to eliminate LLM latency during the injection phase.

**Input to Keeper:**
- Agent metadata (Name, ID, Description)
- Current **Structured Session Journal** (from Session Tier 1)
- Last 3 raw messages (for immediate verbatim context)
- Top-K relevant episodic memories (retrieved by vector similarity)

**Output from Keeper (Immediate):**
```text
=== AGENT IDENTITY ===
Name: ...
ID: ...
Description: ...

=== SESSION JOURNAL ===
[Context]
...
[Decisions]
...
[Last State]
...

=== RECENT MESSAGES ===
User: ...
Agent: ...

=== HISTORICAL MEMORIES ===
- ...
```

The agent then injects this block into its system prompt prefix. **This is a zero-LLM-call operation for the Keeper, ensuring agents start reasoning instantly.**

### 3. Model Routing (Added 2026-05-31)

When an agent has `model_routing_enabled: true`, the Keeper is called to choose the best secondary model for each task or session before the agent begins reasoning.

**Input to Keeper (`POST /model/route`):**
- Task description (user message or task input)
- Complexity score and tier from Core's heuristic scorer (`local` | `standard` | `premium`)
- Filtered list of secondary models (prose-formatted: numbered lines with `model_id`, `label`, `description`, `cost_tier`)
- Agent's default model (fallback reference)

**Keeper Logic:**
The Keeper reads the task description, compares it against the complexity tier and available models, and returns a JSON decision:
```json
{
  "provider": "openai",
  "model_id": "gpt-4o",
  "reason": "Task requires structured reasoning and moderate context window; gpt-4o balances cost and capability."
}
```

**Validation & Fallback:**
- Core validates the returned `model_id` against the agent's configured `secondary_models` list.
- If the Keeper returns invalid JSON, an unknown model, or a model outside the filtered tier, Core **fail-opens** to the agent's default model.
- The chosen model is stored in `tasks.routed_model_id` or `sessions.routed_model_id` and locked for the lifetime of that task/session.

**Performance Notes:**
- The routing call runs **in parallel** with context injection (`asyncio.gather`) so it adds no wall-clock latency to the critical path.
- On slow CPU-only hardware where the Keeper takes 150s+ per inference, the Core scorer's heuristic result is still usable immediately; the LLM decision simply refines it.
- Session-lifetime lock means routing is invoked **once per session**, not on every message.

### 4. Journal Maintenance (Incremental Compacting)

Instead of generic summarization, the Keeper maintains an incremental **Structured Session Journal**. This happens in the background via the `JournalWorker` whenever:
- A task is completed (`status == "done"`), OR
- A chat session has new activity since the last journal update (`last_activity_at > journal_updated_at`)

**Input to Keeper (`/journal/update`):**
- Old Journal content
- Last 10 raw messages

**Keeper Logic:**
The Keeper uses its currently active generation model (default `qwen3:1.7b`, dynamically switchable) to extract new facts and update the structured sections:
- **[Context]**: Environment, active versions, user preferences.
- **[Decisions]**: Key decisions, agreed-upon constraints.
- **[Last State]**: What was being done most recently.

**Output from Keeper:**
The updated structured journal string, which is then persisted to the `sessions` table in Tier 1 memory. After a successful update, raw messages are truncated to the last 10.

---

### 5. Agent Heartbeats

Each registered agent sends a heartbeat signal to the Core API every 180 seconds. Instead of a simple `200 OK` ping, ISLI uses **intelligent heartbeats**:

```
Agent → Core API: { agent_id, status, current_task_id, last_action_ts }
Core API → Keeper: "validate this heartbeat"
Keeper → Core API: { is_healthy, anomaly_detected, warning? }
Core API → Kanban: update agent status indicator
```

The Keeper checks for anomalies:
- **Stuck agent**: same `current_task_id` for too long
- **Silent agent**: no heartbeat for > threshold
- **Loop detection**: agent revisiting same task state > N times
- **Token runaway**: agent reporting abnormally high token usage

**Temporal context (Implemented 2026-05-28):**
- Each log entry is prefixed with its timestamp (`[YYYY-MM-DD HH:MM]`) so the LLM can distinguish stale from recent events.
- The prompt explicitly instructs the LLM to disregard entries older than 24 hours unless they show a persistent pattern.
- This prevents false positives from ancient episodic memories (e.g., a resolved API-key error from a week ago) being misclassified as an ongoing anomaly.

**False-positive guard (Implemented 2026-05-28):**
- The 1.7B validator model frequently hallucinates benign states as anomalies (e.g., "waiting for user input", "heartbeat received multiple times").
- The Keeper applies a post-processing whitelist: only anomaly strings containing keywords like `crash`, `fatal`, `infinite loop`, `stuck`, `repeated error`, or `loop` are trusted.
- All other anomaly descriptions are logged as false positives and overridden to `is_valid: true`.
- This makes the validator pragmatically useful while still catching real crashes and stuck loops.

If an anomaly is detected, the Core API flags the agent card on the Kanban board and optionally pauses the agent.

### 6. Memory Compaction

Periodically (or when a session context grows beyond a threshold), the Keeper runs **compaction**:
- Reads raw session messages
- Produces a compressed summary (≤ 200 tokens)
- Writes summary to episodic memory
- Prunes raw message buffer

This mirrors Claude Code's compaction concept but happens locally, for free.

### 7. Skill Result Summarization

When a skill returns a large payload (e.g., a 10,000-word web scrape), the Keeper summarizes it to a compact form before it enters the agent's context window. This is the **"RAG gate"** — the Keeper acts as a retrieval pre-processor.

---

## CPU-Only Optimizations (Implemented 2026-05-19)

In environments without a GPU, the following optimizations are applied:

1. **Permanent Model Loading**: `OLLAMA_KEEP_ALIVE=-1` ensures the model stays in RAM.
2. **Thread Pinning**: `OLLAMA_NUM_THREADS=8` pins Ollama to half of the available 16 cores to prevent context switching overhead and leave room for other services.
3. **API Context Cap**: The Keeper client enforces `num_ctx: 4096` and `num_batch: 512` to maintain sub-second ingestion and steady throughput on CPU.
4. **Model Tiering**: Using `1.5B` parameter models allows for high-speed local inference that competes with cloud speeds for small background tasks.

---

## Model Management (Implemented 2026-05-22)

The Keeper supports dynamic model switching via a runtime `ModelManager` that reads from `/app/data/model_config.json`. This allows operators to switch gen/embed models without restarting the service.

### Model Slots

| Slot | Purpose | Default | Permitted |
|------|---------|---------|-----------|
| `gen` | Generation (summarize, journal, heartbeat, PII) | `qwen3:1.7b` (env override via `OLLAMA_GEN_MODEL`) | `qwen3:1.7b`, `qwen3:4b`, `mistral:7b`, `qwen2.5-coder:1.5b` |
| `embed` | Embeddings (semantic search, memory) | `nomic-embed-text` (env override via `OLLAMA_EMBED_MODEL`) | `nomic-embed-text`, `mxbai-embed-large` |

### Admin Endpoints (Internal Auth Required)

All admin endpoints require a valid `X-Internal-Auth` JWT signed with `JWT_SECRET`.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/admin/config` | GET | Return current `{gen, embed}` model config |
| `/admin/activate` | POST | Activate a pulled model for a slot |
| `/admin/remove` | POST | Remove a model from Ollama (with active-model guard) |
| `/admin/pull` | POST | Trigger async Ollama pull for a slot/model |

### Model Management Flow

```
Board UI → Core API (/v1/model-management/*)
               → validates admin auth + active sessions = 0 (409 if busy)
               → forwards to Keeper (/admin/*) with X-Internal-Auth
               → UI polls /v1/model-management/status for state
```

**Actions:**
- **Pull** — Downloads a missing model into Ollama and sets it as the active model for the slot.
- **Activate** — Switches the active model for a slot to an already-downloaded model.
- **Remove** — Deletes a model from Ollama. If the model is currently active, the slot is reset to the default fallback model (verified to exist first).

**Constraints:**
- Pull and Activate are blocked when any active sessions exist (to prevent mid-inference model swaps).
- Only models in the `PERMITTED_MODELS` list are accepted.
- Remove refuses to delete the last available model for a slot unless the fallback exists.

### Keeper Settings UI

The React board exposes a **"Local Model Management"** page at `/settings/keeper` that shows:
- Current active models for `gen` and `embed` slots (green checkmark)
- Available models that are pulled but not active (Activate + Remove buttons)
- Missing models (Download button)
- Global "Pull in progress..." state that disables actions during pulls

---

## Keeper API (Internal Only)

The Keeper exposes a minimal internal HTTP API on `localhost:8001`:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/ready` | GET | Readiness check (probes Ollama model list) |
| `/dashboard` | GET | Full telemetry snapshot (identity, health, stats, config) |
| `/embed` | POST | Embed text, return vector |
| `/summarize` | POST | Summarize arbitrary text |
| `/journal/update` | POST | Update the structured session journal |
| `/context/inject` | POST | Fast-path: Build context block (identity + memories). Records inference telemetry with `model="retrieval-only"`. |
| `/model/route` | POST | Choose best secondary model for a task/session. Receives `{task_description, complexity_score, complexity_tier, secondary_models, default_model}`. Returns `{provider, model_id, reason}`. |
| `/heartbeat` | POST | Validate an agent heartbeat |
| `/heartbeat/validate` | POST | Deep heartbeat validation with LLM judge. Timeout: **180s** (was 30s). Records inference telemetry on failure. |
| `/pii/scrub` | POST | Regex + LLM PII masking |
| `/pii/unscrub` | POST | Restore masked PII placeholders |
| `/skill/clean` | POST | Extract structured data from raw skill output |
| `/verify/logic` | POST | LLM-based logic verification |
| `/models` | GET | List available Ollama models |
| `/admin/config` | GET | Return current `{gen, embed}` model config |
| `/admin/activate` | POST | Activate a pulled model for a slot |
| `/admin/remove` | POST | Remove a model from Ollama (with active-model guard) |
| `/admin/pull` | POST | Trigger async model pull |

**Admin endpoint details:**

- **`/admin/activate`** — Receives `{slot, model_name}`. Validates the model exists in Ollama, then calls `ModelManager.set_model(slot, model_name)` and persists to `/app/data/model_config.json`. Returns `{status: "ok", slot, model}`.
- **`/admin/remove`** — Receives `{model_name}`. Verifies the model exists in Ollama. If the model is currently active for any slot, looks up the fallback default from settings and validates it exists in Ollama before proceeding. If the fallback is missing, returns `409 Cannot remove active model: fallback default not available`. Otherwise deletes the model via Ollama `/api/delete` and resets the active slot to the fallback if needed. Returns `{status: "ok", removed, was_active}`.
- **`/admin/config`** — Returns the current runtime config directly from `ModelManager.config`: `{config: {gen: "...", embed: "..."}}`.
- **`/admin/pull`** — Receives `{slot, model_name}`. Pulls the model via Ollama `/api/pull`, then sets it as the active model for the slot.

> **Important:** Every endpoint except `/health` and `/ready` requires the `X-Internal-Auth` header containing a valid JWT signed with the shared `JWT_SECRET`. The Core API generates these tokens automatically when proxying requests to the Keeper.

---

## Keeper Configuration (`keeper.config.yaml`)

```yaml
keeper:
  ollama_host: http://localhost:11434

  models:
    embedding: nomic-embed-text
    generation: qwen3:1.7b  # Default; runtime value comes from ModelManager / Board UI

  journal:
    trigger: task_completion
    lookback_messages: 10     # messages used to update journal
    injection_last_messages: 3 # messages injected into raw context

  context:
    top_k_episodic: 5            # episodic memories to retrieve
    max_injection_tokens: 1000   # total context block cap
```

---

## Prompt Configuration (`prompts.yaml`)

All Keeper prompts live in a single `prompts.yaml` at the repo root and are loaded at runtime. Each service has a symlink (`isli-keeper/prompts.yaml → ../prompts.yaml`) so Docker builds pick it up automatically. The file is mounted as a volume in `docker-compose.yml` so you can edit prompts without rebuilding.

**Search order for the loader:**
1. `PROMPTS_FILE` env var
2. `/app/prompts.yaml` (Docker default)
3. `./prompts.yaml` relative to the service root

**Important:** Prompts that contain JSON examples (e.g. `{"is_valid": true}`) must use **double braces** (`{{"is_valid": true}}`) because the loader uses Python `.format()` for variable substitution. Single braces are interpreted as format placeholders and will raise `KeyError` at runtime.

**Keeper prompts you can override:**

| Key | Endpoint | Variables |
|-----|----------|-----------|
| `keeper.summarize` | `/summarize` | `{max_length}`, `{text}` |
| `keeper.journal_update` | `/journal/update` | `{old_journal}`, `{recent_messages}` |
| `keeper.heartbeat_anomaly` | `/heartbeat` | `{agent_id}`, `{status}`, `{activity}` |
| `keeper.heartbeat_validate` | `/heartbeat/validate` | `{agent_id}`, `{heartbeat_at}`, `{compressed_log}` |
| `keeper.pii_scrub` | `/pii/scrub` | `{text}` |
| `keeper.skill_clean` | `/skill/clean` | `{extraction_goal}`, `{raw_data}` |
| `keeper.verify_logic` | `/verify/logic` | `{context}`, `{text}` |
| `keeper.model_router` | `/model/route` | `{task_description}`, `{complexity_score}`, `{complexity_tier}`, `{model_list}`, `{default_model}` |

### Editing Prompts via Board UI (2026-05-31)

Administrators can edit `prompts.yaml` directly from the Board at **Settings → Prompts** (`/settings/prompts`). The UI provides:

- **Structured cards** — one textarea per prompt with monospace font and spell-check disabled
- **Three tabs** — Keeper, Agent, Core
- **Per-tab Raw YAML toggle** — switches between structured cards and a single raw YAML editor; validates on switch-back using `js-yaml`
- **Optimistic locking** — `PUT /v1/prompts` carries `last_modified` (file mtime). If another process changed the file, Core returns `409 Conflict` and the UI prompts to refresh.
- **Merge-on-write** — only keys present in the payload are overwritten; unknown/new keys in the YAML are preserved
- **Best-effort Keeper reload** — after writing, Core calls `POST /admin/reload-prompts` on Keeper to clear its LRU cache. If Keeper is unreachable, the UI shows a warning toast but the file is still saved.
- **Agent restart reminder** — a banner reminds that agent runners load prompts at startup and need a restart to see changes.

**API endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| GET | `/v1/prompts` | Read prompts.yaml from disk (bypasses cache) |
| PUT | `/v1/prompts` | Merge, write, clear cache, trigger Keeper reload |
| POST | `/admin/reload-prompts` | Keeper internal — clear `get_prompts` LRU cache |

**Example: manual override (alternative to UI)**

```yaml
keeper:
  summarize: |
    Summarize the following text in under {max_length} words.
    Be concise and factual:

    {text}

    Summary:
```

If editing manually, restart the Keeper container (`docker compose restart keeper`) to pick up changes. The Board UI path handles cache clearing automatically.

## Workload Prioritization & Monitoring (Implemented 2026-06-02)

To ensure system responsiveness in CPU-bound environments, the Keeper utilizes an internal asynchronous priority queue and latency monitoring system.

### 1. Priority Tiers

Tasks are assigned a priority from **P0 (Highest)** to **P3 (Lowest)**. High-priority tasks bypass the background backlog to ensure agent starts and heartbeats are processed immediately.

| Tier | Name | Endpoints | Default Timeout |
|------|------|-----------|-----------------|
| **P0** | **Critical** | `/context/inject`, `/model/route` | 45s (Fail-Fast) |
| **P1** | **High** | `/heartbeat`, `/pii/scrub` | 120s |
| **P2** | **Standard** | `/summarize`, `/skill/clean`, `/verify/logic` | 120s |
| **P3** | **Background** | `/journal/update`, `/embed` | 300s |

### 2. Adaptive Throttling

To prevent resource exhaustion during heavy batch operations, the Keeper applies **Adaptive Throttling** to P3 tasks:
- If the **P3 Queue Depth exceeds 50**, new requests to `/embed` or `/journal/update` are rejected with **HTTP 429 Too Many Requests**.
- This protects the CPU/RAM for P0-P2 tasks, ensuring the "critical path" remains healthy even during mass document ingestion.

### 3. Latency SLOs & Telemetry

The `/dashboard` endpoint now provides granular visibility into the Keeper's internal performance:

- **Queue Depths:** Real-time count of pending tasks per priority (`p0_depth` through `p3_depth`).
- **Latency Percentiles:** In-memory calculation of **p50, p95, and p99** latencies.
- **Wait vs. Inference:** Metrics distinguish between **Queue Wait Time** (time spent waiting for a worker) and **Pure Inference Time** (time spent inside Ollama).
- **SLO Status:** Automatic health status based on p95 latency:
    - `healthy`: p95 < 30s
    - `degraded`: p95 > 30s
    - `critical`: p95 > 60s

---

## Keeper Reliability Gaps (2026-05-11 Research)

The Keeper is ISLI's silent backbone, but the following production gaps were identified:

### Critical
- **No fallback if Ollama/Keeper fails** — context injection, heartbeat validation, and compaction all cease simultaneously with no degraded mode.

### Fixed (2026-06-02)
- **Unbounded concurrent workloads** — Fixed via **Internal Priority Queue** and **Worker Loop**. Ollama calls are now serialized (or concurrency-limited) to prevent CPU thrashing.
- **Workload Prioritization** — Fixed via **P0-P3 Tiers**. Critical path tasks (P0) now bypass background tasks (P3).
- **No latency SLOs** — Fixed. Dashboard now tracks **p50/p95/p99** and reports an automated **SLO Status**.
- **Hidden Backlog** — Fixed. Dashboard now reports **Queue Depths** per priority.
- **Adaptive Throttling** — Fixed. P3 tasks are rejected with **429** if the backlog exceeds 50 items.

### High
- ~~**No warm-up strategy**~~ — **Fixed 2026-05-22**. `ollama-init` container pre-pulls all permitted models before Keeper starts; `OLLAMA_KEEP_ALIVE=-1` keeps models in RAM indefinitely.
- **Malformed JSON has no fallback** — heartbeat and context injection depend on parseable JSON with no error-handling path.
- ~~**Unbounded concurrent workloads**~~ on a single Ollama instance with no queue or prioritization. (Moved to Fixed)
- ~~**Broad `except Exception` in `fallback.py` hides real errors**~~ — **Fixed 2026-05-19**. `fallback.py` deleted entirely; Keeper now returns honest 503 errors with no hidden cloud fallback chain.

### Medium
- **Compaction summary quality is unmonitored** — no metric or human review loop validates that summaries preserve critical decisions.
- ~~**No latency SLOs**~~ — no p50/p95/p99 targets for `/embed`, `/summarize`, or `/context/inject`. (Moved to Fixed)
- **Architecture rules out scaling beyond single machine** — no documented path for Ollama replicas or remote inference.
- **ChromaDB embedded mode** creates a single-process vector-store SPOF.

### Removed (2026-06-03)
- ~~**Circuit breaker**~~ — `isli_keeper/circuit_breaker.py` deleted. Keeper's charter is "honest 503": local Ollama failures surface immediately so Core and callers can react. A circuit breaker would mask outages for 30+ seconds and create false confidence. Resilience lives in `isli_core.circuit_breaker` (Core API / Skills proxy) and `isli_agent_sdk` (agent runner cloud-model calls), not in the local Ollama proxy.

### Fixed (2026-05-22)
- **Model Bootstrap Race Condition** — Added `ollama-init` container that pulls all permitted models before the Keeper starts.
- **Unreliable Heartbeat Validation** — Standardized on `qwen3:1.7b` as the default (replacing the unreliable 0.6B model) and improved telemetry to show the model name in the dashboard.
- **Weak Healthchecks** — Updated Ollama healthcheck to verify model presence with generous retries and start periods for slow downloads.
- **Docker Resource Limits** — Set explicit CPU (8.0) and Memory (8GB) limits for Ollama and (512MB) for Keeper in `docker-compose.yml`.
- **Prompt JSON Brace Escaping** — `prompts.yaml` prompts with JSON examples (`heartbeat_validate`, `verify_logic`) now use double braces (`{{"is_valid": ...}}`) to prevent `KeyError` from Python `.format()`.
- **Heartbeat Validation Timeout** — Increased Keeper→Ollama timeout from 30s to **180s** to accommodate slow CPU-only inference.
- **Dashboard Telemetry Gaps** — `heartbeat/validate` and `context/inject` now record endpoint-level inference metrics so the dashboard shows model names and failure reasons instead of empty fields.

### Fixed (2026-05-18)
- **Timeout chain too short for slow hardware** — Core→Keeper timeouts increased to 180s (journal/heartbeat validate) and 120s (context injection); Keeper→Ollama to 120s; Ollama client timeout raised to 300s. This prevents ReadTimeout cascades on hardware where `qwen3:1.7b` takes 30-90+s per inference.
- **Chat sessions never got journals** — `JournalWorker` now triggers on `last_activity_at > journal_updated_at` for sessions without completed tasks.
- **Task path ignores pre-computed context** — Agent SDK `runner.py` now reads `task.context_summary` instead of making redundant HTTP calls.
- **Checkpoint recovery crashes every 5 min** — `CheckpointRecoveryWorker` in `isli_core/jobs/checkpoint_recovery.py` had a tuple unpacking bug: `rows_map[task.id] = (task, agent)` was iterated with `for _, agent in rows_map.items()`, so `agent` received the tuple instead of the Agent object. Fixed by unpacking `for _, (task, agent) in rows_map.items()`.

> **Recommendation:** The Keeper should be treated as a Tier-0 critical service — not "silent" to operators. Add RED metrics, latency SLOs, structured logging, and tighten exception handling in `ollama_client.py`.

> See `Memory/ISLI-Research-Report.md` for full details.
