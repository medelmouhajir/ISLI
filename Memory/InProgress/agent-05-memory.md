# Agent 05 — Memory System Integrity Findings Report

**Date:** 2026-05-11
**Scope:** ISLI memory architecture (Tier 1–4), Keeper compaction/embedding pipeline, and cross-tier data integrity.
**Sources:** `03-memory.md`, `02-keeper.md`

---

## Domain Summary

ISLI implements a 4-tier memory hierarchy (Session, Episodic, Semantic, Archival) backed by Redis, PostgreSQL, and ChromaDB, with a local Ollama-based Keeper service handling summarization, embeddings, and compaction. While the design is principled, the documentation reveals critical gaps in versioning, consistency validation, garbage collection, and vector-store resilience that expose the system to silent data corruption and unbounded growth at production scale.

---

## Findings Table

| ID | Severity | Category | Description | Evidence | Recommendation |
|----|----------|----------|-------------|----------|----------------|
| F01 | **Critical** | Versioning / Vectors | **Embedding model version drift is completely unhandled.** Updating `nomic-embed-text` changes vector semantics and invalidates the entire corpus, yet there is no model versioning, migration pipeline, or compatibility gate. | `keeper.config.yaml` references `nomic-embed-text` without version pin or migration plan; schema hardcodes `VECTOR(768)`. | Pin embedding model versions; implement a vector re-computation migration job triggered on model change; store model identifier alongside each vector. |
| F02 | **Critical** | Resilience / Vectors | **No backup or restore strategy exists for ChromaDB vectors.** The vector store lives at `./data/vectors` with no snapshots, replication, or documented restore procedure. | `vector_store.path: ./data/vectors`; zero mention of backups in `03-memory.md` or `02-keeper.md`. | Schedule periodic ChromaDB snapshots to object storage; document point-in-time restore procedures; test recovery drills. |
| F03 | **High** | Consistency / Embeddings | **No guarantee that an episodic memory summary is semantically consistent with its embedding.** Summary generation (qwen3:1.7b) and embedding generation (nomic-embed-text) are separate, unvalidated steps. | `POST /embed` and `POST /compact` are independent calls with no round-trip validation, checksum, or semantic similarity gate between summary text and its vector. | Add a validation step that embeds the summary and asserts cosine similarity against the original message embedding exceeds a threshold before write. |
| F04 | **High** | Quality / Compaction | **Compaction information loss rate is unmeasured.** The 1.7B parameter model compresses raw sessions to ≤200 tokens with no benchmarks, regression tests, or key-decision survival metrics. | `compaction.summary_max_tokens: 200`; no evaluation pipeline, no human-in-the-loop audit, no "information loss" metric cited. | Establish a compaction quality benchmark: sample summaries against raw sessions and measure decision/outcome recall; set a minimum survival threshold. |
| F05 | **High** | Growth / Archival | **Tier 4 archival data is append-only with no pruning or partitioning.** The docs state "Never deleted" with no retention policy, table partitioning, or cold storage migration. | `task_archive` and `message_archive` are append-only; no partitioning keys, TTL, or archiving to cheaper storage mentioned. | Implement time-based table partitioning (e.g., monthly); define a retention SLA with automated migration to cold storage after N months. |
| F06 | **High** | Resilience / Session | **Redis session data has no documented persistence guarantee.** If Redis restarts without RDB/AOF, all active Tier 1 session context is lost instantly. | Redis is described as "in-memory, fast, TTL-controlled"; no mention of RDB, AOF, or replication in `03-memory.md`. | Enforce RDB+AOF persistence in Redis config; document failover to a replicated Redis node; treat session memory as ephemeral but disclose the risk. |
| F07 | **High** | Isolation / Security | **Vector DB lacks agent-level isolation; contamination prevention is query-filter dependent.** Cross-agent guards rely solely on application-layer `agent_id` filtering in SQL, not on ChromaDB namespaces or collections. | Read discipline says "Filtered by agent_id"; no per-agent ChromaDB collection or metadata-enforced isolation documented. | Create per-agent collections or enforce metadata-filter isolation in ChromaDB queries; add integration tests that verify Agent A cannot retrieve Agent B vectors. |
| F08 | **High** | Consistency / Cross-Tier | **No memory inconsistency detection or repair mechanism exists.** There are no checksums, cross-tier reconciliation jobs, or drift audits between summaries, embeddings, and raw archive data. | "Memory Hygiene Rules" list intent but no operational validation; Keeper heartbeat validates agent health, not memory integrity. | Implement a periodic reconciliation job that samples episodic memories and verifies alignment against Tier 4 archive payloads; publish consistency SLAs. |
| F09 | **High** | Atomicity / Transactions | **Episodic memory dual-write lacks atomicity guarantees.** Writes go to both PostgreSQL and ChromaDB with no transaction coordinator or rollback logic. | `episodic_memories` schema spans SQL and vector store; no mention of two-phase commit, outbox pattern, or compensating transactions. | Adopt an outbox pattern or saga orchestrator for dual writes; retry failed ChromaDB writes asynchronously from PostgreSQL. |
| F10 | **Medium** | Hygiene / Semantic | **Semantic memory has no deduplication logic.** Explicit saves (via `memory/save` or pinning) can create duplicate or near-duplicate vectors for the same fact. | Semantic memory write discipline is "explicit, not automatic"; no deduplication gate, vector similarity check, or merge logic described. | Add a pre-write deduplication step: query ChromaDB for near-duplicates at a similarity threshold and merge or reject redundant inserts. |
| F11 | **Medium** | Hygiene / Episodic | **Episodic importance decay is mentioned but undefined.** There is no algorithm, rate, schedule, or physical garbage collection for low-importance memories. | "Importance decay" is listed as a hygiene rule with no implementation detail; schema defines `importance FLOAT DEFAULT 0.5` but no decay function. | Define an exponential or linear decay function with a scheduled job; set a minimum threshold and physically delete or archive memories below it. |
| F12 | **Medium** | Resilience / Cache | **Semantic memory Redis cache has no invalidation logic.** Semantic data is cached for 1 hour, but updates to ChromaDB do not invalidate the cache. | "Cached in Redis for 1 hour after first retrieval"; no cache invalidation on write or event bus mentioned. | Implement cache invalidation on `memory/save` writes, or use a short TTL (e.g., 5 min) if invalidation is not feasible. |
| F13 | **Medium** | Schema / Guardrails | **Hardcoded vector dimension lacks model-change guard.** `VECTOR(768)` is fixed in schema with no runtime check against the active embedding model's output size. | `embedding VECTOR(768)` in `episodic_memories` schema; model config in `keeper.config.yaml` is decoupled from DDL. | Add a startup guard that asserts the active embedding model outputs 768 dimensions; abort or warn on mismatch. |
| F14 | **High** | Observability / SLAs | **No consistency regression framework despite known industry failure mode.** The CLEAR framework shows consistency degrades from 60% to ~25% at scale, yet ISLI has no internal metrics or SLAs. | No metrics, dashboards, or regression tests for memory retrieval accuracy, compaction fidelity, or embedding drift are documented. | Define memory consistency KPIs (e.g., retrieval precision, compaction recall); build a regression test suite that fails builds on SLA breach. |
| F15 | **Medium** | Performance / Archival | **Archival PostgreSQL tables lack performance optimizations for scale.** Large append-only tables have no mentioned indexes or partitioning strategy beyond primary keys. | `task_archive` and `message_archive` schemas show only primary keys; no indexes on `agent_id`, `created_at`, or `task_id` for query performance. | Add composite indexes on `(agent_id, created_at)` and `(task_id, event_type)`; monitor query plans as table size grows. |

---

## Cross-Cutting Concerns

1. **Local-Model Production Risk:** Relying on a 1.7B parameter local model (`qwen3:1.7b`) for compaction and heartbeat validation without A/B testing against cloud models means information loss and false anomaly rates are unknown quantities. At scale, small model errors compound across tiers.

2. **Implicit Single-Node Assumption:** The architecture (`localhost:11434`, `./data/vectors`, single Redis) assumes a single-node deployment. Without documented horizontal scaling strategies, redundancy, or sharding, the memory system has no production-grade resilience path.

3. **Security vs. Convenience Tension:** The `agent_id` filter is convenient for shared queries but brittle for multi-agent security. Application-layer filtering is prone to developer error; database-layer isolation (per-agent collections or row-level security in PostgreSQL) would be safer.

4. **External Context Alignment:** The CLEAR framework's reported 60%→25% consistency degradation strongly suggests ISLI needs proactive measurement before scale, not after. The absence of any embedded evaluation framework is a strategic gap.

---

## Confidence per Finding

| Finding | Confidence | Rationale |
|---------|------------|-----------|
| F01 | **High** | Explicit model name without version or migration plan in config. |
| F02 | **High** | Explicit local path with zero backup/restore documentation. |
| F03 | **High** | Architecture shows independent endpoints with no validation step. |
| F04 | **High** | Token limit is explicit; evaluation pipeline is absent. |
| F05 | **High** | "Never deleted" and append-only are explicit design choices. |
| F06 | **High** | Redis described only as "in-memory"; persistence not mentioned. |
| F07 | **High** | Only `agent_id` filter is documented; no DB-level isolation. |
| F08 | **High** | No validation, audit, or reconciliation process is described anywhere. |
| F09 | **High** | Dual-write architecture is clear; transactionality is not. |
| F10 | **Medium** | Write discipline is explicit but dedupe is not mentioned; may exist in code. |
| F11 | **Medium** | Rule is stated but implementation is omitted; may exist in code. |
| F12 | **Medium** | Cache behavior is documented; invalidation may exist in code. |
| F13 | **High** | Schema and config are decoupled with no guard documented. |
| F14 | **High** | No metrics section exists; external evidence is strong. |
| F15 | **Medium** | Indexes may exist in actual DDL; only simplified schema shown in docs. |

---

## Summary

ISLI's memory system has a clean conceptual architecture but is currently documented as a **single-node, best-effort design** with no production-grade safeguards for consistency, versioning, backup, or scale. The most urgent risks are **embedding model version drift (F01)**, **lack of vector backup (F02)**, and **unmeasured compaction loss (F04)**, which together threaten the fundamental reliability of the memory hierarchy. Addressing the dual-write atomicity gap (F09), cross-tier reconciliation (F08), and Redis persistence (F06) would significantly improve production resilience.
