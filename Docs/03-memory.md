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

**Purpose**: Holds the active conversation context for a running session.

**Storage**: Redis (in-memory, fast, TTL-controlled)

**Structure**:
```json
{
  "session_id": "sess_abc123",
  "agent_id": "agent_sales",
  "messages": [
    { "role": "user", "content": "...", "ts": 1715300000 },
    { "role": "agent", "content": "...", "ts": 1715300010 }
  ],
  "token_count": 1840,
  "created_at": 1715299900,
  "expires_at": 1715385900
}
```

**Write discipline**:
- Every user message appended immediately
- Every agent response appended immediately
- Keeper trims buffer when `token_count > compaction_threshold`

**Read discipline**:
- Always read last N messages (configurable, default 20)
- Keeper reads full buffer for compaction

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
- Semantic search via embedding similarity (top-K retrieval)
- Filtered by `agent_id` to avoid cross-agent pollution
- Used in Keeper's `context/inject` pre-turn call

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

## Scoped Memory: Agent vs Global

| Scope | What it contains | Who can read | Who can write |
|-------|-----------------|-------------|--------------|
| `global` | ISLI system config, shared skills | All agents | Admin only |
| `agent:{id}` | Agent persona, preferences, history | That agent + Keeper | That agent + Keeper |
| `channel:{name}` | Channel-specific context | Assigned agent | Assigned agent |
| `session:{id}` | Active session messages | Assigned agent | Assigned agent |

---

## Memory Injection Flow

```
Task arrives at Agent X
      │
      ▼
Keeper.context/inject(agent_id, session_id, task_description)
      │
      ├─ Fetch last 20 messages from Session Memory (Tier 1)
      ├─ Vector search Episodic Memory (Tier 2) → top 5 relevant
      ├─ Vector search Semantic Memory (Tier 3) → top 3 relevant
      │
      ▼
Keeper summarizes into injection block (≤ 500 tokens)
      │
      ▼
Agent prepends injection to system prompt
Agent calls its model API with: [injection] + [agent persona] + [task]
```

---

## Memory Hygiene Rules

1. **Agents do not write directly to Episodic or Archival memory.** Only the Keeper does (post-turn).
2. **Session memory expires.** Redis TTL = 24 hours by default.
3. **No raw message content in Episodic memory.** Only Keeper-generated summaries.
4. **Importance decay**: episodic memories lose importance weight over time unless re-accessed.
5. **Cross-agent contamination prevention**: Agent A cannot read Agent B's episodic memory without explicit delegation.

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
- **No ChromaDB backup/restore strategy** — vectors live at `./data/vectors` with zero snapshots or tested recovery.

### High
- **No guarantee that episodic summary matches its embedding** — summary generation and embedding are separate, unvalidated steps.
- **Compaction information loss rate unmeasured** — a 1.7B model compresses to 200 tokens with no benchmarks.
- **Tier 4 archival append-only with no partitioning/retention** — violates GDPR Art. 5(1)(e); no cold storage migration.
- **Redis session data has no persistence guarantee** — RDB/AOF not mentioned; restart wipes active sessions.
- **Vector DB lacks agent-level isolation** — cross-agent guard is query-layer `agent_id` filter only, not DB-level.
- **No memory inconsistency detection or repair** — no checksums, reconciliation jobs, or cross-tier audits.
- **Dual-write (PostgreSQL + ChromaDB) lacks atomicity** — no transaction coordinator, outbox, or saga.

### Medium
- **Semantic memory deduplication missing** — explicit saves can create redundant vectors.
- **Episodic importance decay undefined** — mentioned as hygiene rule but no algorithm or physical GC.
- **Semantic cache no invalidation** — Redis 1-hour cache not invalidated on ChromaDB updates.
- **Hardcoded vector dimension without guard** — `VECTOR(768)` is fixed with no runtime model-size check.
- **Archival tables lack performance indexes** — no composite indexes on `(agent_id, created_at)`.

> See `Memory/ISLI-Research-Report.md` for full details and recommendations.