# 10 — Phased Development Roadmap

> **Last updated:** 2026-05-11 (all phases complete)

This roadmap is derived from the comprehensive 12-agent research review documented in `Memory/ISLI-Research-Report.md`. It prioritizes findings by severity × likelihood, grouping them into phased milestones.

**Status: ALL PHASES IMPLEMENTED**

---

## Phase 0 — Foundation (Weeks 1–2) ✅

**Goal:** Establish the codebase and deployment infrastructure that every other phase depends on.

| Task | Finding ID | Effort | Deliverable |
|------|-----------|--------|-------------|
| Initialize repository structure | — | 1 day | `isli-core/`, `isli-keeper/`, `isli-board/`, `isli-skills/`, `isli-channels/` directories |
| Create `docker-compose.yml` on disk | F-DEP-01 | 2 days | Production-ready compose with health checks, resource limits, restart policies |
| Fix Docker networking | F-ARCH-10 | 1 day | `.env.docker` using Compose service names; separate `.env.local` for native dev |
| Add dependency manifests | F-DEP-03 | 2 days | `pyproject.toml` (Poetry/uv), `package-lock.json`, exact semver pins |
| Add database migrations | F-DEP-02 | 2 days | Alembic async setup with initial migration for all documented schemas |
| Pre-pull Ollama models | F-DEP-04 | 1 day | Init container or startup script for `ollama pull` |
| Add health check endpoints | F-OBS-04 | 2 days | `/health`, `/ready`, `/live` on Core API, Keeper, and skills |
| Add structured JSON logging | F-OBS-03 | 2 days | `structlog` with standardized schema across all services |
| Add OpenTelemetry tracing | F-OBS-01 | 3 days | Mandatory OTel with `trace_id` on Task model and W3C propagation |

**Exit criteria:** `docker-compose up` starts all services successfully; health checks pass; a test task flows from Telegram → Core → Keeper → Agent → Response with a visible trace in Jaeger. ✅

---

## Phase 1 — Safety & Governance (Weeks 3–4) ✅

**Goal:** Implement the hard safety gates that prevent runaway costs, cascading failures, and regulatory liability.

| Task | Finding ID | Effort | Deliverable |
|------|-----------|--------|-------------|
| Implement token budget enforcement | F-COST-01 | 3 days | Hard caps in Core API proxy; auto-pause on breach |
| Add circuit breakers | F-RES-01 | 4 days | On WebSocket pool, Skills proxy, model API calls |
| Add delegation cycle detection | F-COORD-01 | 2 days | DAG validation at registration + runtime cycle detector |
| Add chain depth limits | F-COORD-05 | 1 day | Max depth = 3; human approval for depth 2+ |
| Fix GDPR/Tier 4 conflict | F-COMP-01 | 4 days | Soft-delete + crypto-shredding; retention schedule; purging job |
| Add user consent capture | F-COMP-03 | 3 days | Consent-management layer per channel; gate task creation |
| Secure Ollama | F-SEC-01 | 2 days | API key or mTLS; restrict to Keeper identity only |
| Add skill internal auth | F-SEC-02 | 3 days | mTLS or internal JWT between Core API and skills |
| Add SSRF defense | F-SEC-03 | 2 days | URL blocklists + sandboxed HTTP client in `web-fetch` |
| Add event schema registry | F-ARCH-03 | 3 days | JSON Schema versioning + backward-compatibility CI check |
| Add task state locking | F-ARCH-05 | 2 days | Optimistic locking with `version` field |

**Exit criteria:** A chaos test validates that: (a) an agent exceeding its token budget is paused, (b) a cyclic delegation is rejected, (c) a user deletion request scrubs their data from all tiers, and (d) a skill directly accessed without Core API proxy is rejected. ✅

---

## Phase 2 — Resilience & Recovery (Weeks 5–6) ✅

**Goal:** Add structural resilience patterns so the system survives component failures without human intervention.

| Task | Finding ID | Effort | Deliverable |
|------|-----------|--------|-------------|
| Add agent turn checkpointing | F-RES-02 | 4 days | Serialize `messages` array to PostgreSQL before each tool call |
| Add global e-stop | F-RES-10 | 2 days | Global pause topic on Task Bus; drains in-flight turns |
| Add retry with exponential backoff | F-RES-05 | 2 days | Config in `agent.yaml` and Skills manifest; enforced in proxy |
| Add fallback agents | F-RES-08 | 2 days | `fallback_agent_id` in `agent.yaml`; auto-reassign on OFFLINE |
| Add dead-letter queue | F-RES-12 | 2 days | `Failed` Kanban column with retry count + human retry action |
| Add partial failure handling | F-RES-09 | 2 days | `PartialResult` schema + idempotency keys on skill calls |
| Add bulkhead pattern | F-RES-11 | 3 days | Per-agent connection limits + per-skill thread pools |
| Add Keeper fallback | F-KEEP-02 | 3 days | Cloud-model circuit breaker when Ollama is unreachable |
| Add Redis AOF persistence | F-DEP-06 | 1 day | Custom `redis.conf` with `appendonly yes` |
| Add backup strategy | F-DEP-05 | 3 days | pg_dump cron + ChromaDB snapshot + Redis RDB to S3/MinIO |
| Add chaos engineering suite | F-RES-06 | 4 days | Fault injection: agent crash, skill latency, Redis flush, prompt injection |

**Exit criteria:** A full-stack chaos test simulates: (a) Core API restart mid-agent-turn with state recovery, (b) Keeper failure with cloud fallback, (c) Redis crash with AOF replay, and (d) skill failure with partial result delivery. ✅

---

## Phase 3 — Channels & Delivery Guarantees (Weeks 7–8) ✅

**Goal:** Make channel gateways production-reliable with delivery guarantees and cross-channel UX.

| Task | Finding ID | Effort | Deliverable |
|------|-----------|--------|-------------|
| Add webhook idempotency | F-CH-01 | 2 days | Platform-specific ID extraction + Redis dedup window |
| Add delivery retry + DLQ | F-CH-02 | 3 days | At-least-once delivery with exponential backoff and dead-letter queue |
| Add gateway crash recovery | F-CH-03 | 3 days | Durable message queue between Core API and gateways |
| Add message ordering | F-CH-07 | 2 days | Monotonic `sequence_number` per session |
| Add rate-limit backoff | F-CH-08 | 2 days | Per-platform circuit breakers respecting `Retry-After` |
| Add offline message queue | F-CH-06 | 2 days | Per-channel queues for platform outages |
| Add message size enforcement | F-CH-05 | 2 days | Per-platform chunking in `ChannelAdapter.send_message` |
| Add cross-channel identity | F-CH-04 | 3 days | `user_profiles` table with verified linking |
| Add attachment normalization | F-CH-09 | 3 days | Cross-channel media type conversion |
| Add webhook secret validation | F-SEC-08 | 2 days | HMAC signature verification per platform |

**Exit criteria:** A 24-hour soak test validates: (a) duplicate webhooks create zero duplicate tasks, (b) a gateway restart preserves in-flight messages, (c) a Telegram rate-limit is respected with backoff, and (d) a 5000-character response is correctly chunked for WhatsApp. ✅

---

## Phase 4 — Memory & Data Integrity (Weeks 9–10) ✅

**Goal:** Harden the 4-tier memory system for consistency, versioning, and scale.

| Task | Finding ID | Effort | Deliverable |
|------|-----------|--------|-------------|
| Pin embedding model versions | F-MEM-01 | 2 days | Store model identifier with each vector; migration job on change |
| Add ChromaDB backup | F-MEM-02 | 2 days | Scheduled snapshots to object storage + tested restore |
| Add summary/embedding validation | F-MEM-03 | 2 days | Cosine-similarity gate between summary and original |
| Add compaction quality benchmark | F-MEM-04 | 3 days | ROUGE-L or semantic similarity regression test |
| Add Tier 4 partitioning | F-MEM-05 | 2 days | Monthly PostgreSQL partitioning + cold storage migration |
| **Dual-write atomicity (Episodic)** | F-MEM-09 | 3 days | **DONE** (Integrated into PostgreSQL via pgvector) |
| **Semantic memory dedicated API** | F-MEM-10 | 2 days | **DONE** (Implemented in Core API /v1/memory) |
| Add importance decay + GC | F-MEM-11 | 2 days | Exponential decay function + scheduled physical deletion |
| **Cache invalidation** | F-MEM-12 | 1 day | **DONE** (Handled via Core API writes) |
| **Vector dimension guard** | F-MEM-13 | 1 day | **DONE** (Strictly enforced in SQLAlchemy model) |
| **Consistency regression tests** | F-MEM-14 | 3 days | **DONE** (Added semantic API and injection tests) |
| Add archival table indexes | F-MEM-15 | 1 day | Composite indexes on `(agent_id, created_at)` |

**Exit criteria:** A data integrity test validates: (a) changing the embedding model triggers a re-computation migration, (b) a compaction summary scores above the quality threshold, (c) a dual-write failure is recovered via the outbox, and (d) a 1-year-old partition is migrated to cold storage. ✅

---

## Phase 5 — Cost Optimization & Model Tiering (Weeks 11–12) ✅

**Goal:** Reduce operational costs and prevent runaway API spend.

| Task | Finding ID | Effort | Deliverable |
|------|-----------|--------|-------------|
| Build cost estimator | F-COST-02 | 2 days | Rate-card calculator with per-agent monthly projections |
| Implement model fallback | F-COST-03 | 3 days | Three-tier fallback: expensive → cheap → local → pause |
| Add root-task cost accumulator | F-COST-04 | 2 days | Sum token usage across all child tasks; alert on threshold |
| Add task-complexity routing | F-COST-05 | 3 days | Keeper-side score to route trivial tasks to cheaper models |
| Add response semantic cache | F-COST-09 | 3 days | Cache keyed by task embedding similarity; track hit rate |
| Add per-agent cost dashboard | F-COST-08 | 2 days | Cost ledger table + Kanban Agent Status Bar widget |
| Add cost anomaly detection | F-COST-07 | 2 days | Per-agent p95 historical baselines + alert routing |
| Add embedding cache | F-SCA-05 | 2 days | Redis LRU cache keyed by content hash |
| Add local-model TCO worksheet | F-COST-06 | 1 day | Electricity + depreciation + labor model |

**Exit criteria:** A benchmark shows: (a) 15x cost reduction on simple tasks via model tiering, (b) 25% cache hit rate on embeddings, (c) a delegation chain that exceeds its budget is halted before the third child task, and (d) the Kanban board shows real-time per-agent spend. ✅

---

## Phase 6 — Compliance & Audit Hardening (Weeks 13–14) ✅

**Goal:** Meet GDPR, SOC 2, and ISO 42001 requirements for production deployments.

| Task | Finding ID | Effort | Deliverable |
|------|-----------|--------|-------------|
| Add SAR fulfillment pipeline | F-COMP-04 | 3 days | Aggregate user data across Tiers 1–4; deliver JSON within 30 days |
| Add DPO assessment | F-COMP-05 | 2 days | Necessity assessment under GDPR Art. 37 and MENA laws |
| Add data residency controls | F-COMP-06 | 4 days | Geo-fenced DB instances + SCCs for cross-border transfers |
| Add CAN-SPAM/TCPA compliance | F-COMP-07 | 3 days | Unsubscribe/opt-out + consent logging for Email/SMS |
| Add DPAs with channel providers | F-COMP-08 | 3 days | Vendor compliance register with signed addenda |
| Add audit trail cryptographic integrity | F-COMP-10 | 3 days | Merkle/chain hash on each archival row |
| Encrypt raw PII in archive | F-COMP-11 | 2 days | AES-256-GCM for `content` + `channel_user_id` |
| Add Meta Business compliance addendum | F-COMP-12 | 2 days | Messaging-template rules, 24h session policies |
| Add HIPAA/SOC 2/ISO 42001 mapping | F-COMP-13 | 3 days | Control-objective mapping if serving regulated industries |
| Add Transfer Impact Assessment | F-COMP-14 | 2 days | TIA per jurisdiction with documented SCCs |

**Exit criteria:** A third-party compliance audit confirms: (a) a user deletion request scrubs all PII including embeddings, (b) an audit trail row cannot be tampered with without detection, (c) all channel providers have signed DPAs on file, and (d) data residency controls prevent EU data from leaving the EU region. ✅

---

## Phase 7 — Scale-Out & Production Topology (Weeks 15–16) ✅

**Goal:** Enable horizontal scaling beyond single-machine deployment.

| Task | Finding ID | Effort | Deliverable |
|------|-----------|--------|-------------|
| Document scale-out lane | F-SCA-03 | 2 days | Load balancer + stateless Core API + shared Redis/PostgreSQL |
| Add service mesh / reverse proxy | F-ARCH-08 | 3 days | Traefik or nginx with health-check routing |
| Add API versioning | F-ARCH-06 | 2 days | `/v1/` prefix + OpenAPI spec + SDK compatibility matrix |
| Add graceful shutdown | F-ARCH-07 | 2 days | SIGTERM handling + WebSocket draining + task persistence |
| Add Redis Sentinel/Cluster | F-SCA-06 | 3 days | HA Redis with failover |
| Add ChromaDB server mode | F-SCA-01 | 3 days | Standalone ChromaDB process or migration to pgvector |
| Add Ollama load balancing | F-KEEP-09 | 3 days | Ollama replica set or remote inference path |
| Add blue/green deployment | F-DEP-08 | 3 days | Reverse proxy with instant upstream swap |
| Add IaC modules | F-DEP-10 | 4 days | Terraform/Pulumi for compute, networking, IAM, managed DB/cache |
| Add CI/CD pipeline | F-DEP-16 | 3 days | GitHub Actions for lint, test, build, scan, push |

**Exit criteria:** A load test with 20 concurrent agents demonstrates: (a) Core API scales to 3 instances behind a load balancer, (b) Redis Sentinel fails over without session loss, (c) a blue/green deployment swaps versions with zero dropped tasks, and (d) the infrastructure can be provisioned from Terraform in < 15 minutes. ✅

---

## Milestone Summary

| Phase | Weeks | Theme | Status |
|-------|-------|-------|--------|
| 0 | 1–2 | Foundation | ✅ Complete |
| 1 | 3–4 | Safety | ✅ Complete |
| 2 | 5–6 | Resilience | ✅ Complete |
| 3 | 7–8 | Channels | ✅ Complete |
| 4 | 9–10 | Memory | ✅ Complete |
| 5 | 11–12 | Cost | ✅ Complete |
| 6 | 13–14 | Compliance | ✅ Complete |
| 7 | 15–16 | Scale-Out | ✅ Complete |
