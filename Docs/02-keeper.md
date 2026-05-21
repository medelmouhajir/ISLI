# 02 — The Keeper (Hidden Local Agent)

## What Is the Keeper?

The Keeper is ISLI's **silent backbone**. It is a Python service running a small local Ollama model that performs all background AI work without consuming cloud API tokens. It is never assigned tasks directly, never speaks to users, and never appears on the Kanban board as an active agent.

> Think of it as the brain-stem — not the thinking mind, but the system that keeps everything alive, coherent, and connected.

---

## Recommended Local Models

The Keeper needs to be fast, small, and reliable for structured tasks. Based on current benchmarks:

| Task | Recommended Model | Size | Min Container Memory | Notes |
|------|------------------|------|---------------------|-------|
| Summarization + context compression | `qwen2.5-coder:1.5b` | ~1.1 GB | 2 GB | Faster, optimized for CPU inference |
| Embeddings | `nomic-embed-text` | ~274 MB | 1 GB | Best local embedding model, 8K context |
| Heartbeat validation (JSON output) | `qwen2.5-coder:1.5b` | ~1.1 GB | 2 GB | Replaces qwen3:0.6b for better reliability |
| Fallback reasoning | `phi3:mini` (3.8B) | ~2.5 GB | 3.5 GB | Punches above weight |

**Recommended combo for most PCs:**
- Summarization: `qwen2.5-coder:1.5b`
- Embeddings: `nomic-embed-text`

> **Note:** Ollama loads model weights into container RAM at runtime. The `deploy.resources.limits.memory` value in `docker-compose.yml` must exceed the model size. 

> **Hardware reality check:** On a 16-core CPU environment (ARM aarch64), `qwen2.5-coder:1.5b` takes **~3-4 seconds for TTFT** and generates at **~15 tokens/sec**. We use `OLLAMA_KEEP_ALIVE=-1` to ensure models stay in RAM indefinitely, eliminating the 10-30s cold-start penalty. We pin Ollama to **8 threads** to balance speed with system stability.

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
- Agent metadata (Name, ID, Description, Persona)
- Current **Structured Session Journal** (from Session Tier 1)
- Last 3 raw messages (for immediate verbatim context)
- Top-K relevant episodic memories (retrieved by vector similarity)

**Output from Keeper (Immediate):**
```text
=== AGENT IDENTITY ===
Name: ...
ID: ...
Description: ...
Persona: ...

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

### 3. Journal Maintenance (Incremental Compacting)

Instead of generic summarization, the Keeper maintains an incremental **Structured Session Journal**. This happens in the background via the `JournalWorker` whenever:
- A task is completed (`status == "done"`), OR
- A chat session has new activity since the last journal update (`last_activity_at > journal_updated_at`)

**Input to Keeper (`/journal/update`):**
- Old Journal content
- Last 10 raw messages

**Keeper Logic:**
The Keeper uses its local model (`qwen2.5-coder:1.5b`) to extract new facts and update the structured sections:
- **[Context]**: Environment, active versions, user preferences.
- **[Decisions]**: Key decisions, agreed-upon constraints.
- **[Last State]**: What was being done most recently.

**Output from Keeper:**
The updated structured journal string, which is then persisted to the `sessions` table in Tier 1 memory. After a successful update, raw messages are truncated to the last 10.

---

## CPU-Only Optimizations (Implemented 2026-05-19)

In environments without a GPU, the following optimizations are applied:

1.  **Permanent Model Loading**: `OLLAMA_KEEP_ALIVE=-1` ensures the model stays in RAM.
2.  **Thread Pinning**: `OLLAMA_NUM_THREADS=8` pins Ollama to half of the available 16 cores to prevent context switching overhead and leave room for other services.
3.  **API Context Cap**: The Keeper client enforces `num_ctx: 4096` and `num_batch: 512` to maintain sub-second ingestion and steady throughput on CPU.
4.  **Model Tiering**: Using `1.5B` parameter models allows for high-speed local inference that competes with cloud speeds for small background tasks.

### 4. Agent Heartbeats

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

If an anomaly is detected, the Core API flags the agent card on the Kanban board and optionally pauses the agent.

### 4. Memory Compaction

Periodically (or when a session context grows beyond a threshold), the Keeper runs **compaction**:
- Reads raw session messages
- Produces a compressed summary (≤ 200 tokens)
- Writes summary to episodic memory
- Prunes raw message buffer

This mirrors Claude Code's compaction concept but happens locally, for free.

### 5. Skill Result Summarization

When a skill returns a large payload (e.g., a 10,000-word web scrape), the Keeper summarizes it to a compact form before it enters the agent's context window. This is the **"RAG gate"** — the Keeper acts as a retrieval pre-processor.

---

## Keeper API (Internal Only)

The Keeper exposes a minimal internal HTTP API on `localhost:8001`:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/embed` | POST | Embed text, return vector |
| `/journal/update` | POST | Update the structured session journal |
| `/context/inject` | POST | Fast-path: Build context block (identity + memories) |
| `/summarize` | POST | Summarize arbitrary text |
| `/heartbeat` | POST | Validate an agent heartbeat |
| `/health` | GET | Keeper health check |

---

## Keeper Configuration (`keeper.config.yaml`)

```yaml
keeper:
  ollama_host: http://localhost:11434

  models:
    embedding: nomic-embed-text
    generation: qwen3:1.7b  # Used for /journal/update and /summarize

  journal:
    trigger: task_completion
    lookback_messages: 10     # messages used to update journal
    injection_last_messages: 3 # messages injected into raw context

  context:
    top_k_episodic: 5            # episodic memories to retrieve
    max_injection_tokens: 1000   # total context block cap
```

---

## What the Keeper Does NOT Do

- It does **not** route tasks or make decisions about which agent should handle what
- It does **not** write to the Kanban board directly
- It does **not** call external APIs
- It does **not** speak to users directly (only via agents)
- It does **not** stream responses to the UI

---

## Keeper Reliability Gaps (2026-05-11 Research)

The Keeper is ISLI's silent backbone, but the following production gaps were identified:

### Critical
- **No measured accuracy data** for `qwen3:0.6b` structured JSON output under load. Benchmarks are needed before trusting heartbeat validation to a 0.6B model.
- **No fallback if Ollama/Keeper fails** — context injection, heartbeat validation, and compaction all cease simultaneously with no degraded mode.

### High
- **No warm-up strategy** — Ollama cold-start latency after restarts is unaddressed.
- **Malformed JSON has no fallback** — heartbeat and context injection depend on parseable JSON with no error-handling path.
- **Model versions not pinned** — `ollama/ollama:latest` and mutable tags (`qwen3:0.6b`) can shift silently.
- **Unbounded concurrent workloads** on a single Ollama instance with no queue or prioritization.
- **Broad `except Exception` in `fallback.py` hides real errors** — an `AttributeError` from calling a non-existent method on `OllamaClient` was silently swallowed, triggering a broken cloud fallback chain. The fix was to use the public `client.generate()` API.

### Medium
- **Compaction summary quality is unmonitored** — no metric or human review loop validates that summaries preserve critical decisions.
- **No latency SLOs** — no p50/p95/p99 targets for `/embed`, `/summarize`, or `/context/inject`.
- **Architecture rules out scaling beyond single machine** — no documented path for Ollama replicas or remote inference.
- **~~No Docker resource limits~~** — *Partially addressed:* memory limit is now set to 6 GB, but Ollama model size must be checked against it.
- **ChromaDB embedded mode** creates a single-process vector-store SPOF.

### Implemented
- **Circuit breaker** — `isli_keeper/circuit_breaker.py` implements CLOSED/OPEN/HALF_OPEN states with recovery timeout.

### Fixed (2026-05-18)
- **Timeout chain too short for slow hardware** — Core→Keeper timeouts increased to 180s (journal/heartbeat validate) and 120s (context injection); Keeper→Ollama to 120s; circuit breaker recovery to 120s. This prevents ReadTimeout cascades on hardware where `qwen3:1.7b` takes 30-90+s per inference.
- **Chat sessions never got journals** — `JournalWorker` now triggers on `last_activity_at > journal_updated_at` for sessions without completed tasks.
- **Task path ignores pre-computed context** — Agent SDK `runner.py` now reads `task.context_summary` instead of making redundant HTTP calls.
- **Checkpoint recovery crashes every 5 min** — `CheckpointRecoveryWorker` in `isli_core/jobs/checkpoint_recovery.py` had a tuple unpacking bug: `rows_map[task.id] = (task, agent)` was iterated with `for _, agent in rows_map.items()`, so `agent` received the tuple instead of the Agent object. Fixed by unpacking `for _, (task, agent) in rows_map.items()`.

> **Recommendation:** The Keeper should be treated as a Tier-0 critical service — not "silent" to operators. Add RED metrics, latency SLOs, structured logging, and tighten exception handling in `fallback.py`.

> See `Memory/ISLI-Research-Report.md` for full details.
