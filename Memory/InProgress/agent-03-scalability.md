# Agent 03 — Scalability & Performance Findings

## Domain Summary

ISLI is architected as a single-machine, layered multi-agent system centered on a local Ollama-based Keeper, Redis event bus, and a 4-tier memory hierarchy. Every design document explicitly optimizes for local developer-laptop deployment, which creates hard ceilings on concurrent agents, vector database concurrency, and horizontal growth that will manifest well before production load. The absence of connection pooling configuration, embedding caches, partitioning strategies, and cycle-safe delegation graphs are the dominant risk vectors.

---

## Findings Table

| ID | Severity | Category | Description | Evidence | Recommendation |
|----|----------|----------|-------------|----------|----------------|
| F01 | **Critical** | Infrastructure | ChromaDB embedded mode prevents concurrent vector access across services; file-level locking will corrupt or block when Core API and Keeper both hold the embedded client. | `03-memory.md` Tier 3 stored in ChromaDB collections; `09-tech-stack.md` states "ChromaDB runs in the same process"; both `isli-core` and `isli-keeper` declare `chromadb` dependency. | Switch to ChromaDB server mode or migrate Tier 3 to PostgreSQL pgvector with connection pooling. |
| F02 | **Critical** | Bottleneck | Ollama is a single-process local inference runtime with no request queue visibility; multiple concurrent agents will saturate VRAM/CPU and cause Keeper timeouts. | `02-keeper.md` shows embedding, summarization, heartbeat, and compaction all route through `POST http://localhost:11434/api/embeddings` or generation endpoints; no timeout, batch, or queue config present. | Add an Ollama-side request queue with explicit timeout budgets in Keeper config; consider embedding batching or a dedicated embedding service. |
| F03 | **High** | Scaling | There is no horizontal scaling path; Kubernetes is explicitly rejected and all services are singletons in docker-compose. | `09-tech-stack.md` states "Not Kubernetes: ISLI targets single-machine deployment. K8s would be overkill"; `01-architecture.md` shows single ports for each service. | Design a stateless service tier (Core API, Skills) behind a load balancer with shared Redis/PostgreSQL; keep Keeper singleton but add circuit breakers. |
| F04 | **High** | Storage | Tier 4 archival memory is append-only with no partitioning, retention policy, or cold-storage offload; disk will exhaust and query performance will degrade. | `03-memory.md` defines `task_archive` and `message_archive` as "append-only, no UPDATE/DELETE"; `09-tech-stack.md` recommends only 50GB disk; no retention or partitioning mentioned. | Implement time-based PostgreSQL table partitioning (e.g., monthly) and an S3/Glacier offload for segments older than N months. |
| F05 | **High** | Caching | No semantic or embedding cache exists; identical strings are re-embedded on every Keeper call, wasting Ollama cycles and adding latency. | `02-keeper.md` embedding call pattern shows direct `POST` with no cache layer; `03-memory.md` only mentions Redis caching for Tier 3 *retrieval*, not embedding generation. | Add a Redis-backed embedding cache keyed by content hash (e.g., SHA-256 of prompt) with TTL; expect 20-40% hit rate per 2026 MAS norms. |
| F06 | **High** | Resilience | Redis pub/sub and Streams are single-instance with no cluster or Sentinel configuration; agent heartbeat and Kanban events have no failover. | `09-tech-stack.md` shows `redis:7-alpine` single container; `01-architecture.md` shows WebSocket event bus and pub/sub for heartbeats with no replication. | Deploy Redis Sentinel or Redis Cluster for HA; add graceful degradation (local SQLite fallback for session buffer) when Redis is unreachable. |
| F07 | **Medium** | Database | PostgreSQL connection pooling is not configured; default asyncpg pool sizes may exhaust under burst agent registrations and archival writes. | `09-tech-stack.md` lists `asyncpg==0.30.x` but `.env` only provides `DATABASE_URL` with no pool min/max; `01-architecture.md` shows many concurrent agents writing to PostgreSQL. | Explicitly configure asyncpg pool (`min_size`, `max_size`, `max_inactive_time`) in Core API and Keeper; set `max_size >= 2x expected agent count`. |
| F08 | **Medium** | Memory Pressure | Session memory (Tier 1) uses Redis Hash with 24h TTL but no maxmemory policy or eviction strategy; unbounded growth under many active sessions risks OOM. | `03-memory.md` TTL = 24 hours by default; `09-tech-stack.md` minimum RAM is 8GB; no Redis `maxmemory` or eviction policy mentioned. | Configure Redis `maxmemory-policy allkeys-lru` and cap `maxmemory` per deployment tier; add session GC metrics and alerts. |
| F09 | **Medium** | Topology | Agent delegation via Kanban board creates cyclic delegation graphs; the system lacks inter-agent cycle detection, risking infinite loops and 100% error infection per 2026 research. | `01-architecture.md` shows Agent A creates task for Agent B and waits; Keeper loop detection only covers *individual* agent state revisits (`loop_detection_max_revisits: 3`), not cross-agent cycles. | Build a delegation DAG tracker (task.parent_chain) and reject or pause tasks that would create a cycle; cap delegation depth. |
| F10 | **Medium** | Observability | Langfuse is marked optional with no fallback telemetry; under load, missing tracing will prevent diagnosing which tier or agent is failing. | `09-tech-stack.md` "Langfuse (optional)" and `.env` keys are empty; `01-architecture.md` Langfuse listed under Tracing/Observability with no required alternative. | Make OpenTelemetry traces mandatory with a lightweight stdout/OTLP fallback so load-related regressions are always observable. |
| F11 | **Low** | Compute | Model tiering is not implemented; every agent uses its configured cloud model regardless of task complexity, missing 15x cost savings potential. | `01-architecture.md` agents have `model_config` but no task-router; `02-keeper.md` Keeper could classify tasks but no routing logic exists. | Route simple tasks (summarization, formatting) to Keeper-tier local models and reserve expensive APIs for reasoning-heavy tasks. |

---

## Cross-Cutting Concerns

1. **Single-Machine Assumption Collides with MAS Concurrency Needs**
   The entire stack—docker-compose, embedded ChromaDB, single Ollama, single Redis—is designed for a developer laptop. A multi-agent system with more than a handful of active agents will hit simultaneous ceilings on CPU (Ollama), RAM (Redis + ChromaDB in-memory), and I/O (PostgreSQL WAL). The architecture needs a "scale-out" lane even if the default remains single-machine.

2. **Keeper Is a Hidden Singleton Bottleneck**
   Every task turn, every heartbeat, and every compaction routes through the Keeper → Ollama pipeline. There is no Keeper replica, no load balancing, and no async queue between Core API and Keeper. Under concurrent load, Keeper latency will cascade into agent timeouts and Kanban stalls.

3. **No Data Lifecycle Management**
   Tiers 1, 2, and 4 all accumulate data indefinitely (Tier 1 for 24h, others forever). There is no compaction for Tier 4, no archiving to object storage, and no retention SLAs. This is a time-bomb for disk cost and query latency.

4. **Cyclic Delegation Risk**
   The "From Spark to Fire" paper (2026) demonstrates that cyclic topologies in MAS reach 100% error infection. ISLI’s Kanban delegation model is inherently graph-forming; without cycle detection, a misconfigured agent delegation chain (A→B→C→A) will saturate the task queue and Redis Streams with no automatic recovery.

---

## Confidence per Finding

| Finding | Confidence | Rationale |
|---------|------------|-----------|
| F01 | **95%** | Embedded ChromaDB is process-bound by design; two Python processes holding the same SQLite/HNSW backend is a documented anti-pattern. |
| F02 | **90%** | Ollama’s local inference concurrency is bounded by VRAM/CPU; the docs show all Keeper functions are synchronous HTTP calls with no queue abstraction. |
| F03 | **95%** | The rejection of Kubernetes and the docker-compose singleton layout are explicit in `09-tech-stack.md`. |
| F04 | **90%** | Append-only tables without partitioning inevitably degrade; 50GB recommended disk is incompatible with "never deleted" archival at scale. |
| F05 | **85%** | No cache layer is visible in any code snippet or config; embedding caches are standard 2026 practice but absence here is an inference gap. |
| F06 | **90%** | Single Redis container is shown; no Sentinel or Cluster config exists. |
| F07 | **80%** | asyncpg defaults exist but are not shown; this is a probable gap rather than a confirmed misconfiguration. |
| F08 | **85%** | Redis defaults to no maxmemory; the explicit 24h TTL helps but burst sessions can still exceed RAM. |
| F09 | **85%** | Loop detection is intra-agent only; inter-agent cycle risk is architecturally present but would need code review to confirm exploitability. |
| F10 | **80%** | Optional observability is declared; impact under load is inferred from operational best practices. |
| F11 | **75%** | Model tiering is not mentioned; recommendation is speculative based on 2026 cost-savings norms, though easily implementable via Keeper. |

---

*Report generated by Research Agent 3 (Scalability & Performance) on 2026-05-11.*
