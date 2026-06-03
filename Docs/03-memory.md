# 03 — Memory System

## Design Philosophy

ISLI's memory system is built on three lessons from existing systems:

- **OpenClaw**: Memory lives in files (SOUL.md, Memory.md). Simple but unstructured. Agents write ad-hoc. No retrieval discipline.
- **Claude Code**: Hierarchical scoped memory (global → project → local). Auto-memory writes based on recurrence likelihood. Compaction survives session resets.
- **Hermes Agent**: SQLite-backed session persistence + RL loop for self-improvement. Strong agent-level isolation.

**ISLI's synthesis**: A **4-tier memory hierarchy** where each tier has a clear write discipline, a clear read discipline, and is managed by a specific system component.

---

## The 4-Tier Memory Model

```
┌─────────────────────────────────────────────────────┐
│  TIER 1 — SESSION MEMORY (Hot)                      │
│  Raw message buffer · Redis · TTL: session duration  │
├─────────────────────────────────────────────────────┤
│  TIER 2 — EPISODIC MEMORY (Warm)                    │
│  Task summaries · Key decisions · PostgreSQL + Vec   │
│  Written by: Keeper (post-task compaction)           │
├─────────────────────────────────────────────────────┤
│  TIER 3 — SEMANTIC MEMORY (Cold)                    │
│  Skills, domain facts, user preferences              │
│  ChromaDB vectors · Written by: explicit save ops    │
├─────────────────────────────────────────────────────┤
│  TIER 4 — ARCHIVAL MEMORY (Frozen)                  │
│  Full task history · Skill outputs · Audit log       │
│  PostgreSQL append-only · Never deleted              │
└─────────────────────────────────────────────────────┘
```

---

## Tier 1 — Session Memory

**Purpose**: Holds the active conversation context and the pre-computed structured journal for a running session.

**Storage**: Redis (for hot messages) + PostgreSQL `sessions` table (for journal and full buffer).

**Structure**:
```json
{
  "session_id": "sess_abc123",
  "agent_id": "agent_sales",
  "journal": "[Context]\n...\n[Decisions]\n...\n[Last State]\n...",
  "journal_updated_at": "2026-05-17T01:30:00Z",
  "messages": [
    { "role": "user", "content": "...", "ts": 1715300000 },
    ...
  ],
  "token_count": 1840
}
```

**Write discipline**:
- Every message appended immediately.
- **JournalWorker** (background) triggers on:
  - `task:done` event (task-based sessions), OR
  - New message activity (`last_message_at > journal_updated_at`) for direct user-to-agent sessions.
- Keeper updates the `journal` incrementally using the last 10 messages.
- Buffer is truncated to the **last 10 messages** after a successful journal update.

**Keep-Alive vs Activity**:
- `last_activity_at`: Updated by agent heartbeats. Used for idle detection and session expiration. Does **not** trigger the JournalWorker.
- `last_message_at`: Updated only when messages are added to the session. Used specifically to trigger the **JournalWorker**.

**Read discipline**:
- `context/inject` reads the `journal` + the **last 3 messages**.
- **JournalWorker** reads the **last 10 messages** for incremental compacting.

---

## Tier 2 — Episodic Memory

**Purpose**: Summaries of what happened in past sessions — decisions, outcomes, errors.

**Storage**: PostgreSQL table + ChromaDB vectors (for similarity search)

**Schema**:
```sql
CREATE TABLE episodic_memories (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  agent_id    VARCHAR(64) NOT NULL,
  session_id  VARCHAR(64),
  summary     TEXT NOT NULL,         -- Keeper-generated summary
  tags        TEXT[],                -- e.g. ["sales", "client:acme", "error"]
  importance  FLOAT DEFAULT 0.5,     -- 0.0–1.0, used for retrieval ranking
  embedding   VECTOR(768),           -- from nomic-embed-text
  created_at  TIMESTAMPTZ DEFAULT NOW()
);
```

**Write discipline** (Keeper writes, not agents):
- Written after task completion (post-turn compaction)
- Written after session end (session summary)
- Importance score set by Keeper based on outcome (success, error, user feedback)

**Read discipline**:
- Semantic search via `pgvector` cosine distance (`<=>`) in Keeper.
- Triggered when `task_description` is provided to `context/inject`.
- **Similarity Threshold**: Results are filtered by a cosine distance threshold (default `< 0.4`). Only memories that actually meet the relevance criteria are returned.
- **Conditional Fallback**:
  - If semantic search returns matches, they are used.
  - If semantic search yields no results above the threshold OR an error occurs, the system falls back to the **3 most recent** episodic memories (down from 5) to provide some context while minimizing noise.
  - If **no** `task_description` is provided, no episodic memories are injected (unlike the previous unconditional fallback to the last 5).
- Filtered by `agent_id` to avoid cross-agent pollution.

---

## Tier 3 — Semantic Memory

**Purpose**: Stable knowledge — user preferences, domain facts, agent-specific learned behaviors, skill documentation.

**Storage**: ChromaDB collections (by category)

**Collections**:
```
isli_preferences     → user/agent configuration preferences
isli_domain_{name}   → domain knowledge per topic
isli_skills          → skill documentation and usage examples
isli_patterns        → recurring successful task patterns
```

**Write discipline** (explicit, not automatic):
- Written by agent via `memory/save` skill call (manual)
- Written by user via Kanban board "pin this memory" action
- Never auto-written from raw conversation

**Read discipline**:
- Queried by agents during planning ("what do I know about this client?")
- Queried by Keeper for context injection
- Cached in Redis for 1 hour after first retrieval

---

## Tier 4 — Archival Memory

**Purpose**: Immutable audit trail. Everything that ever happened.

**Storage**: PostgreSQL (append-only, no UPDATE/DELETE)

**Key tables**:
```sql
-- Full task history
CREATE TABLE task_archive (
  id           UUID PRIMARY KEY,
  task_id      UUID NOT NULL,
  agent_id     VARCHAR(64),
  event_type   VARCHAR(32),  -- created, assigned, started, completed, failed
  payload      JSONB,
  created_at   TIMESTAMPTZ DEFAULT NOW()
);

-- Full message log
CREATE TABLE message_archive (
  id           UUID PRIMARY KEY,
  session_id   VARCHAR(64),
  agent_id     VARCHAR(64),
  channel      VARCHAR(32),
  role         VARCHAR(16),
  content      TEXT,
  token_count  INTEGER,
  created_at   TIMESTAMPTZ DEFAULT NOW()
);
```

**Write discipline**: Append-only. Core API writes on every state change.

**Read discipline**: Admin/debug use only. Never loaded into agent context.

---

## Memory Observability

To mitigate **Context Drift (F4)** and **History Loss (F8)**, ISLI provides real-time and historical visibility into the memory lifecycle via the Kanban Board UI. Memory events are persisted in a bounded Redis List (last 50 events) to ensure state survives UI reloads.

### 1. Structured Journal Diffs
Visualizes the compaction process from Tier 1 (Session) to Tier 2 (Episodic).
- **Log Event**: `memory:journal_updated`
- **UI View**: Side-by-side line-level diff showing what the Keeper added or removed from the persistent session journal.

### 2. RAG Retrieval Inspector
Exposes the specific memories retrieved from Tier 2 and Tier 3 during context injection.
- **Log Event**: `memory:context_injected`
- **UI View**: Confidence bars showing cosine similarity scores, source tiers, and the raw memory fragments.
- **Metrics**: Total tokens injected vs. available context window.

### 3. Context Truncation Alerts
Warns when the agent's memory exceeds the model's `max_injection_tokens`.
- **Log Event**: `memory:context_truncated`
- **UI View**: Warning banner showing token counts before and after pruning, ensuring operators know when critical history was discarded to fit the window.

---

## Scoped Memory: Agent vs Global

| Scope | What it contains | Who can read | Who can write |
|-------|-----------------|-------------|--------------|
| `global` | ISLI system config, shared skills | All agents | Admin only |
| `agent_{id}` | Agent persona, preferences, history | That agent + Keeper | That agent + Keeper |
| `channel:{name}` | Channel-specific context | Assigned agent | Assigned agent |
| `session:{id}` | Active session messages | Assigned agent | Assigned agent |

---

## Memory Injection Flow

```
Task arrives at Agent X
      │
      ▼
Keeper.context/inject(agent_id, session_id, task_description, memory_similarity_threshold)
      │
      ├─ Fast-fetch Journal from Session (Tier 1)
      ├─ Fast-fetch last 3 messages from Session (Tier 1)
      ├─ Vector search Episodic Memory (Tier 2)
      │   ├─ Filter by distance < threshold (default 0.4)
      │   └─ If empty, fallback to 3 most recent (Conditional Fallback)
      ├─ Vector search Semantic Memory (Tier 3) → top 3 relevant
      │
      ▼
Keeper assembles Fast-Path Block (Zero LLM Latency)
      │
      ▼
Agent prepends block to system prompt
Agent prepends the block to its system prompt (which already contains persona via the SDK) and calls its model API.
```

---

## Memory Hygiene Rules

1. **Agents do not write directly to Episodic or Archival memory.** Only the Keeper does (post-turn).
2. **Session memory expires.** Redis TTL = 24 hours by default.
3. **No raw message content in Episodic memory.** Only Keeper-generated summaries.
4. **Importance decay**: episodic memories lose importance weight over time unless re-accessed.
5. **Scheduled physical deletion**: `MemoryGCWorker` (Core) runs every 24 hours, applying exponential-decay importance scoring (30-day half-life) and hard-deleting memories that fall below threshold `0.1`. Soft-deleted rows are purged after 30 days.
6. **Cross-agent contamination prevention**: Agent A cannot read Agent B's episodic memory without explicit delegation.

---

## Comparing to Source Systems

| Feature | OpenClaw | Claude Code | Hermes | ISLI |
|---------|----------|-------------|--------|------|
| Persistence | Markdown files | CLAUDE.md + auto-memory | SQLite | PostgreSQL + Redis + ChromaDB |
| Vectors | ❌ | ❌ | ❌ | ✅ (ChromaDB) |
| Auto-compaction | ❌ | ✅ | Partial | ✅ (Keeper) |
| Scoped isolation | Partial | ✅ | Partial | ✅ (4 scopes) |
| Audit trail | ❌ | ❌ | Partial | ✅ (append-only) |
| Cross-agent guard | ❌ | N/A | ❌ | ✅ |
| Local model compression | ❌ | ❌ | ❌ | ✅ (Keeper) |

---

## Memory System Gaps (2026-05-11 Research)

The following gaps were identified during a parallel 12-agent research review:

### Critical
- **Embedding model version drift unhandled** — updating `nomic-embed-text` invalidates the entire vector corpus with no migration pipeline.
- ~~**No ChromaDB backup/restore strategy**~~ — **Fixed 2026-05-30**. `scripts/chromadb_backup.py` supports backup/restore with SHA-256 integrity verification. `scripts/backup.sh` includes ChromaDB snapshots with sidecar checksums and S3 upload. `ChromaBackupWorker` runs every 6 hours, stores metadata in `chromadb_backups` table, auto-verifies checksums, and enforces retention. Admin endpoints (`POST /v1/admin/backups/chromadb/trigger`, `GET /v1/admin/backups/chromadb`, `POST /v1/admin/backups/chromadb/restore`) provide on-demand control and restore runbook URL.

### High
- **No guarantee that episodic summary matches its embedding** — summary generation and embedding are separate, unvalidated steps.
- **Compaction information loss rate unmeasured** — a 1.7B model compresses to 200 tokens with no benchmarks.
- **Tier 4 archival append-only with no partitioning/retention** — violates GDPR Art. 5(1)(e); no cold storage migration.
- ~~**Redis session data has no persistence guarantee**~~ — **Fixed**. `docker-compose.yml` configures Redis with `--appendonly yes` (AOF persistence); `docker-compose.scale-out.yml` replicates with AOF.
- **Vector DB lacks agent-level isolation** — cross-agent guard is query-layer `agent_id` filter only, not DB-level.
- **No memory inconsistency detection or repair** — no checksums, reconciliation jobs, or cross-tier audits.
- ~~**Dual-write (PostgreSQL + ChromaDB) lacks atomicity**~~ — **Fixed 2026-05-19**. `OutboxPublisher` + `OutboxWorker` (`isli_core/memory/outbox.py` and `jobs/outbox_worker.py`) provide atomic outbox pattern with retry logic.

### Medium
- **Semantic memory deduplication missing** — explicit saves can create redundant vectors.
- ~~**Episodic importance decay undefined**~~ — **Fixed 2026-05-28**. `MemoryGCWorker` runs every 24h, applies exponential-decay importance scoring (30-day half-life), and physically deletes memories below threshold `0.1`. Soft-deleted rows are purged after 30 days.
- **Semantic cache no invalidation** — Redis 1-hour cache not invalidated on ChromaDB updates.
- ~~**Hardcoded vector dimension without guard**~~ — **Fixed 2026-05-19**. SQLAlchemy model strictly enforces `VECTOR(768)`; dimension mismatch is rejected at the DB layer.
- ~~**Archival tables lack performance indexes**~~ — **Fixed 2026-05-30**. `episodic_memories` has `ix_episodic_memories_agent_id_created_at`; `channel_messages` has `ix_channel_messages_session_seq` and `ix_channel_messages_channel`.

> See `Memory/ISLI-Research-Report.md` for full details and recommendations.