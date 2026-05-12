# Agent 04 — Observability & Debugging Findings Report

**Date:** 2026-05-11  
**Analyst:** Research Agent 4 (Observability & Debugging)  
**Scope:** ISLI documentation review for observability gaps  

---

## Domain Summary

ISLI is a layered multi-agent system with a FastAPI Core, local Keeper sidecar, React Kanban frontend, and independent agent runtimes. Observability is mentioned (Langfuse, OpenTelemetry) but treated as optional infrastructure rather than a first-class system concern, with no distributed trace IDs, structured logging schemas, health checks, or operational SLOs defined in the architecture docs.

---

## Findings Table

| ID | Severity | Category | Description | Evidence | Recommendation |
|----|----------|----------|-------------|----------|----------------|
| OBS-01 | Critical | Distributed Tracing | No unified `trace_id` or `correlation_id` spans the full request path (Telegram Gateway → Core → Keeper → Agent → Skill → Response). | `01-architecture.md` shows data flow but Task model only has `id`, `parent_task_id`, `child_task_ids`. No trace context propagation mentioned. | Add a `trace_id` field to the Task model and propagate W3C trace context headers across all internal HTTP and WebSocket calls. |
| OBS-02 | Critical | Observability Stack | Langfuse is listed as "or OpenTelemetry" in the tech stack, creating ambiguity. No commitment to OpenTelemetry instrumentation for distributed tracing. | `09-tech-stack.md` line 18: "Langfuse (self-hosted) or OpenTelemetry". No OTel SDK or instrumentation mentioned in dependencies. | Mandate OpenTelemetry as the primary distributed tracing layer alongside Langfuse for LLM-specific observability. Instrument Core, Keeper, and all agents. |
| OBS-03 | High | Logging | No structured JSON logging schema is defined anywhere in the documentation. | All four docs mention no logging format. `09-tech-stack.md` dependencies omit structured logging libraries (e.g., `structlog`, `python-json-logger`). | Define a JSON logging schema with mandatory fields: `timestamp`, `level`, `service`, `trace_id`, `agent_id`, `task_id`, `event_type`, `message`. Use `structlog` or equivalent. |
| OBS-04 | High | Health Checks | No health check endpoints (`/health`, `/ready`, `/live`) are defined for any microservice. | `01-architecture.md` component map and `09-tech-stack.md` docker-compose skeleton show no health check endpoints or Docker `healthcheck` configs. | Add FastAPI health check routers to Core, Keeper, and each skill. Expose liveness (`/health/live`) and readiness (`/health/ready`) checks in docker-compose. |
| OBS-05 | High | SLOs/SLIs | No SLOs or latency SLIs are defined for task creation-to-completion. The only timeout is a hard `task_timeout_seconds` (5 min). | `08-failure-modes.md` line 87: "task auto-expires after `task_timeout_seconds` (default: 5 minutes)". No p50/p95/p99 targets per component. | Define SLIs: e.g., p95 task latency < 30s, p95 Keeper context injection < 500ms, p95 skill invocation < 2s. Export as Prometheus metrics. |
| OBS-06 | High | Metrics — Keeper Degradation | No metrics or early-warning indicators for Keeper degradation before it becomes a system failure. | `01-architecture.md` describes Keeper responsibilities but lists no metrics (e.g., Ollama queue depth, embedding latency, compaction duration). `08-failure-modes.md` mentions anomaly detection but without metrics. | Export Keeper metrics: Ollama request queue depth, model load time, embedding generation latency, vector search latency, context injection duration, compaction time. Alert on thresholds. |
| OBS-07 | High | WebSocket Observability | WebSocket disconnections and reconnections are not described as being logged or alerted. | `05-kanban.md` describes WebSocket event types but omits connection lifecycle events. No reconnection backoff or connection-count metrics mentioned. | Add WebSocket connection metrics: active_connections, disconnect_rate, reconnection_latency, connection_duration. Log disconnect reasons and alert on abnormal disconnect spikes. |
| OBS-08 | Medium | Token Anomaly Detection | Token runaway detection is mentioned but lacks concrete thresholds, detection logic, and alerting pathways. | `08-failure-modes.md` line 121: "runaway token usage (3x expected) triggers Kanban alert". No definition of "expected" baseline, no alerting channel, no escalation. | Implement per-agent token baselines using historical rolling averages. Alert via a dedicated `system:alert` severity level (not just Kanban UI). Add a token-budget circuit breaker that pauses the agent. |
| OBS-09 | Medium | MTTR / Recovery | No mean-time-to-recovery (MTTR) plans or automated recovery runbooks are defined for any component. | `08-failure-modes.md` lists mitigations (e.g., loop detection, task expiry) but no recovery procedures (e.g., "If Keeper Ollama timeout > 30s, restart Ollama container"). | Create per-component MTTR runbooks in `Docs/`. Add automated recovery: restart Ollama if Keeper heartbeat fails, circuit-break to cloud model if local model degrades, replay failed tasks to a fallback agent. |
| OBS-10 | Medium | Delegation Chain Tracing | Agent-to-agent delegation chains are visualized on the Kanban board, but there is no evidence they are linked as distributed traces in Langfuse or OpenTelemetry. | `05-kanban.md` shows UI-linked cards. No mention of linking `parent_task_id` traces in Langfuse or OTel. | In Langfuse/OTel, create parent-child trace relationships for delegation chains so a single trace view shows the full chain across agents. |
| OBS-11 | Medium | Infrastructure Observability | System-level infrastructure monitoring (CPU, RAM, GPU VRAM, disk I/O) is completely absent from documentation. | `09-tech-stack.md` lists hardware requirements but no monitoring. Docker-compose has no resource limits or monitoring sidecars. | Add `cAdvisor` or `node_exporter` metrics. Expose GPU VRAM usage for Ollama. Alert on disk space (ChromaDB/pgvector growth) and memory pressure. |
| OBS-12 | Low | Channel Gateway Observability | No per-channel observability (message ingress rate, delivery success/failure, latency per channel) is documented. | `01-architecture.md` mentions Telegram, WhatsApp, Web, Email channels but defines no metrics for them. | Add per-channel metrics: messages_received, messages_delivered, delivery_latency, delivery_failures. Include `channel` tag in all trace spans. |
| OBS-13 | Low | Skill Invocation Observability | Skill invocations lack explicit observability: no mention of skill-level latency percentiles, error rates, or payload size logging. | `01-architecture.md` describes Skills Registry but no observability. `09-tech-stack.md` agent dependencies list `httpx` but no interceptors for metrics. | Instrument all skill HTTP calls with OTel spans capturing: skill_name, latency, status_code, payload_size, retry_count. Log structured skill_call events. |
| OBS-14 | Low | Session Memory Observability | No Redis session memory observability (TTL hit/miss, eviction rate, buffer size) is documented. | `01-architecture.md` mentions Redis for session memory but defines no metrics. `08-failure-modes.md` (F8) mentions Redis TTL but no monitoring. | Export Redis metrics: session_hit_rate, eviction_rate, average_ttl, buffer_size_per_session. Alert on high eviction rates that could cause context loss. |

---

## Cross-Cutting Concerns

1. **Observability is treated as a bolt-on, not a design pillar.** The tech stack lists Langfuse/OpenTelemetry as optional ("or") rather than mandatory. In a production multi-agent system, observability must be as critical as the API itself. Every component should emit traces, metrics, and structured logs by default.

2. **The Kanban board is not a substitute for observability.** While the board provides human-visible task state and token usage, it cannot replace time-series metrics, distributed traces, or automated alerts. Relying on a UI for failure detection introduces human latency and misses infrastructure-level failures (e.g., Redis memory pressure, Ollama GPU OOM) that never surface as task cards.

3. **Local model opacity.** The Keeper relies on Ollama local models. Without model-level metrics (queue depth, inference latency, token throughput), Keeper degradation is invisible until tasks start failing or timing out. This is especially risky given that 16% of failures in production MAS are infrastructure issues.

4. **No correlation between business events and technical signals.** A task moving from `in_progress` to `blocked` is a business event, but the underlying cause (network partition, skill timeout, model hallucination) requires technical traces. Currently there is no bridge between Kanban task state and underlying distributed trace spans.

5. **Single-machine deployment ≠ no observability.** The docs justify omitting Kubernetes, but docker-compose on a single machine still requires container health monitoring, resource usage tracking, and log aggregation. The absence of these creates blind spots that will delay incident response.

---

## Confidence per Finding

| ID | Confidence | Rationale |
|----|------------|-----------|
| OBS-01 | Very High | Task model explicitly lacks `trace_id`; architecture diagram shows no trace propagation. |
| OBS-02 | Very High | Tech stack literally says "or OpenTelemetry"; no OTel in dependency lists. |
| OBS-03 | Very High | Zero mention of logging format or schema in any document. |
| OBS-04 | Very High | No health endpoints in architecture or docker-compose. |
| OBS-05 | High | Timeout exists but no SLO/SLI language used; inference from absence. |
| OBS-06 | High | Keeper described functionally but no operational metrics listed. |
| OBS-07 | High | WebSocket events defined but connection lifecycle omitted. |
| OBS-08 | Medium | "3x expected" mentioned but threshold baseline undefined; partial evidence. |
| OBS-09 | High | Mitigations listed but no recovery procedures or runbooks referenced. |
| OBS-10 | Medium | UI visualization exists; trace linking not mentioned — inference from absence. |
| OBS-11 | Very High | No infrastructure monitoring mentioned at all. |
| OBS-12 | High | Channels mentioned functionally but no metrics defined. |
| OBS-13 | High | Skills described as HTTP microservices with no observability layer mentioned. |
| OBS-14 | Medium | Redis used for session memory but no Redis-specific metrics documented. |

---

*End of Report*
