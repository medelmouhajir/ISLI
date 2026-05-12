# 02 — The Keeper (Hidden Local Agent)

## What Is the Keeper?

The Keeper is ISLI's **silent backbone**. It is a Python service running a small local Ollama model that performs all background AI work without consuming cloud API tokens. It is never assigned tasks directly, never speaks to users, and never appears on the Kanban board as an active agent.

> Think of it as the brain-stem — not the thinking mind, but the system that keeps everything alive, coherent, and connected.

---

## Recommended Local Models

The Keeper needs to be fast, small, and reliable for structured tasks. Based on current benchmarks:

| Task | Recommended Model | VRAM | Notes |
|------|------------------|------|-------|
| Summarization + context compression | `qwen3:1.7b` or `llama3.2:3b` | ~3GB | Fast, instruction-following |
| Embeddings | `nomic-embed-text` | ~274MB | Best local embedding model, 8K context |
| Heartbeat validation (JSON output) | `qwen3:0.6b` | ~1.5GB | Smallest reliable JSON model |
| Fallback reasoning | `phi3:mini` (3.8B) | ~2.5GB | Punches above weight |

**Recommended combo for most PCs:**
- Summarization: `qwen3:1.7b`
- Embeddings: `nomic-embed-text`
- Heartbeat: `qwen3:0.6b`

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
POST http://localhost:11434/api/embeddings
{
  "model": "nomic-embed-text",
  "prompt": "<text to embed>"
}
```

### 2. Context Summarization (Pre-turn Injection)

Before any agent executes a task, the Keeper is called to produce a **context injection block**. This is a compact summary the agent receives alongside the user message.

**Input to Keeper:**
- Last N raw messages from session memory (sliding window)
- Top-K relevant episodic memories (retrieved by vector similarity)
- Agent's current task description

**Output from Keeper:**
```json
{
  "context_summary": "...",
  "relevant_memories": ["...", "..."],
  "token_estimate": 420,
  "confidence": 0.87
}
```

The agent then injects `context_summary` into its system prompt prefix.

**This means even agents using expensive models like GPT-4o or Claude Opus only consume tokens for actual reasoning, not for reconstructing context from scratch.**

### 3. Agent Heartbeats

Each registered agent sends a heartbeat signal to the Core API every N seconds. Instead of a simple `200 OK` ping, ISLI uses **intelligent heartbeats**:

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
| `/summarize` | POST | Summarize text to N tokens |
| `/heartbeat/validate` | POST | Validate an agent heartbeat |
| `/context/inject` | POST | Build context injection for agent pre-turn |
| `/compact` | POST | Compact a session's message buffer |
| `/health` | GET | Keeper health check |

---

## Keeper Configuration (`keeper.config.yaml`)

```yaml
keeper:
  ollama_host: http://localhost:11434

  models:
    embedding: nomic-embed-text
    summarization: qwen3:1.7b
    heartbeat: qwen3:0.6b

  heartbeat:
    interval_seconds: 30
    stuck_threshold_seconds: 300
    loop_detection_max_revisits: 3

  context:
    max_session_messages: 20     # raw messages to include
    top_k_episodic: 5            # episodic memories to retrieve
    max_injection_tokens: 500    # cap on injection block size

  compaction:
    trigger_message_count: 40    # compact after N messages
    summary_max_tokens: 200

  vector_store:
    provider: chromadb
    path: ./data/vectors
    collection_prefix: isli_
```

---

## What the Keeper Does NOT Do

- It does **not** route tasks or make decisions about which agent should handle what
- It does **not** write to the Kanban board directly
- It does **not** call external APIs
- It does **not** have a persona or visible identity
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

### Medium
- **Compaction summary quality is unmonitored** — no metric or human review loop validates that summaries preserve critical decisions.
- **No latency SLOs** — no p50/p95/p99 targets for `/embed`, `/summarize`, or `/context/inject`.
- **Architecture rules out scaling beyond single machine** — no documented path for Ollama replicas or remote inference.
- **No Docker resource limits** for Ollama CPU/GPU memory, risking OOM kills.
- **ChromaDB embedded mode** creates a single-process vector-store SPOF.

> **Recommendation:** The Keeper should be treated as a Tier-0 critical service — not "silent" to operators. Add RED metrics, latency SLOs, structured logging, and a cloud-model fallback circuit breaker.

> See `Memory/ISLI-Research-Report.md` for full details.
