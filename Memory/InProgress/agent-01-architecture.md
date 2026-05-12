# Research Agent 1 — Architecture & Integration Findings

**Date:** 2026-05-11
**Scope:** `01-architecture.md`, `04-agents.md`, `09-tech-stack.md` (with supporting evidence from `05-kanban.md`, `06-skills.md`, `08-failure-modes.md`)

---

## Domain Summary

ISLI is designed as a layered, event-driven multi-agent system built around a FastAPI Core API, a local Ollama-based Keeper sidecar, and Redis-backed real-time Kanban events. While the architecture correctly avoids a central orchestrator in favor of sovereign agents communicating through a shared task board, the infrastructure layer relies on hardcoded localhost URLs, static ports, and implicit single-machine Docker Compose networking. There are no documented mechanisms for service discovery, schema evolution, backpressure, circuit breakers, or graceful rolling updates — all of which are prerequisites for production multi-agent reliability in 2026.

---

## Findings Table

| ID | Severity | Category | Description | Evidence | Recommendation |
|----|----------|----------|-------------|----------|----------------|
| F-ARCH-01 | Critical | Gap | Hardcoded service discovery via `localhost` and static ports. If ports shift or services move to separate hosts, every agent YAML manifest, `.env` file, and skill endpoint must be updated manually. | `.env`: `KEEPER_URL=http://localhost:8001`; `skill.yaml`: `endpoint: http://localhost:8101`; `docker-compose.yml` maps static ports `8000`, `8001`, `8100-8199`, `8200+`. | Replace hardcoded `localhost` with Docker Compose service names for internal traffic. Introduce a lightweight service registry (e.g., Consul, or Traefik + labels) for skill health-check-based discovery. |
| F-ARCH-02 | Critical | Gap | Keeper restart mid-task loses episodic memory writes and blocks new context injection. `store_episodic()` is fire-and-forget (`asyncio.create_task`) with no retry, idempotency key, or outbox pattern. If Keeper restarts before the background task completes, the write is silently lost. | `04-agents.md`: "`asyncio.create_task(keeper.store_episodic(task, response))`". `08-failure-modes.md`: "After turn: Keeper.store_episodic() → writes to Tier 2 memory." No retry or fallback logic shown. | Use a durable outbox pattern or message queue for Keeper writes. Add retry with exponential backoff and a degraded-mode fallback (agent runs without Keeper enrichment if unavailable). |
| F-ARCH-03 | Critical | Gap | No event schema registry for WebSocket or Redis Stream payloads. Breaking changes to `Task`, `BoardEvent`, or agent registration shapes will silently break connected agents and the Kanban UI. | `05-kanban.md`: BoardEvent types are inline TypeScript unions with no version field. `09-tech-stack.md`: "Pydantic models prevent malformed payloads" but no schema registry or backward-compatibility enforcement mentioned. | Adopt JSON Schema or protobuf with a central schema registry. Version every event type (e.g., `task:updated/v1`). Enforce backward compatibility in CI/CD before deployment. |
| F-ARCH-04 | High | Gap | Missing backpressure and circuit breakers on the Kanban event bus. Redis Streams broadcast to all WebSocket clients with no documented consumer groups, buffer limits, or circuit breakers. Slow consumers can cause unbounded memory growth. | `09-tech-stack.md`: "Redis Streams: Used for task event broadcasting to all connected WebSocket clients." No `MAXLEN`, consumer group, or circuit breaker mentioned. External context: production MAST failures require circuit breakers from day one. | Configure Redis Streams with explicit consumer groups, `MAXLEN` trimming, and pending-list limits. Add circuit breakers on WebSocket fan-out and on external model API calls. |
| F-ARCH-05 | Critical | Gap | Task state machine is vulnerable to race conditions during concurrent updates. Multiple actors (agents via API, humans via drag-and-drop, background jobs) can PATCH the same task simultaneously with no optimistic locking or atomic transition validation. | `05-kanban.md`: "PATCH /api/tasks/{id} — Update task (status, assignment)" and human drag-and-drop reassignment shown. `04-agents.md`: "State transitions are managed by Core API" but no locking primitives mentioned. | Implement optimistic locking with a `version` field on tasks, or use PostgreSQL `SELECT FOR UPDATE` during transition validation. Enforce state-machine rules in a single atomic database transaction. |
| F-ARCH-06 | High | Future Risk | No API versioning contract between Core API and agents. Endpoints lack version prefixes, and the agent SDK has no compatibility matrix. Future breaking changes will orphan deployed agents. | `04-agents.md`: `POST /api/agents/register` with no version prefix. Agent SDK uses generic `httpx`/`websockets` with no contract layer. | Introduce `/v1/` API versioning. Publish an OpenAPI specification and an agent SDK compatibility matrix. Use consumer-driven contract tests. |
| F-ARCH-07 | High | Future Risk | No strategy for rolling updates or graceful shutdown of Core API. Persistent WebSocket connections from agents will be abruptly dropped on restart with no connection draining or agent reconnection logic. | `04-agents.md`: "Agent opens WebSocket connection to /ws/agents/{agent_id}" and begins heartbeat loop. No reconnection or draining mentioned. `09-tech-stack.md`: Uvicorn single-process startup in docker-compose. | Implement graceful shutdown with SIGTERM handling and WebSocket draining. Add agent SDK auto-reconnection with exponential backoff and jitter. Consider a lightweight reverse proxy for zero-downtime reloads. |
| F-ARCH-08 | Medium | Future Risk | No service mesh or load balancer. Architecture explicitly targets single-machine Docker Compose, blocking horizontal scaling, health-check routing, and mTLS between services. | `09-tech-stack.md`: "Not Kubernetes: ISLI targets single-machine deployment. K8s would be overkill." Skills listen on ports `8100-8199` with no load balancer. | Even for single-machine, deploy Traefik or nginx with health checks. Internal services should register via the proxy rather than static ports. Prepare a `docker-compose.prod.yml` with replica profiles. |
| F-ARCH-09 | High | Gap | Distributed tracing is optional and LLM-centric, not cross-service. Langfuse is LLM-focused; OpenTelemetry is listed as an optional alternative. No trace context injection across Core API → Agent → Skill → Keeper boundaries. | `09-tech-stack.md`: "Langfuse (self-hosted) or OpenTelemetry". No mention of trace propagation in WebSocket payloads, Redis metadata, or HTTP headers. | Mandate OpenTelemetry from day one. Inject trace context into all WebSocket messages, Redis Stream metadata, and HTTP headers. Use Jaeger or OTLP collector for visualization. |
| F-ARCH-10 | Critical | Gap | Docker Compose `.env` uses `localhost` for inter-service URLs, which breaks container-to-container networking. `postgres`, `redis`, and `isli-keeper` run in separate containers where `localhost` resolves to the container itself. | `.env` in `09-tech-stack.md`: `DATABASE_URL=postgresql://isli:password@localhost:5432/isli`, `REDIS_URL=redis://localhost:6379`, `KEEPER_URL=http://localhost:8001`. `docker-compose.yml` defines these as separate services. | Provide separate `.env.docker` and `.env.local` files. In Docker mode, use Compose service names (`postgres`, `redis`, `isli-keeper`) and internal networking. |
| F-ARCH-11 | Medium | Gap | Unauthenticated internal skill network creates lateral movement risk. Skills have "No auth internally" with RBAC enforced only at the Core API proxy. A compromised container can invoke any skill directly on its hardcoded port. | `01-architecture.md`: "Skills | No auth internally. RBAC enforced by Core API proxy." `06-skills.md`: `endpoint: http://localhost:8101` exposed without credentials. | Add mTLS or a shared internal JWT between Core API and skills. Restrict skill ports to the internal Docker network and avoid exposing them on the host. |

---

## Cross-Cutting Concerns

- **F-ARCH-02** (Keeper restart) overlaps with the Memory domain (`03-memory.md`, Tier 2 persistence) and Keeper domain (`02-keeper.md`). A durable outbox for Keeper writes will require changes to both memory storage and Keeper API semantics.
- **F-ARCH-05** (task race conditions) overlaps with the Kanban domain (`05-kanban.md`) because human drag-and-drop reassignment and agent background completion are concurrent mutation paths on the same PATCH endpoint.
- **F-ARCH-04** (backpressure) overlaps with the Tech Stack domain (`09-tech-stack.md`) for Redis Stream configuration and with the Channels domain (`07-channels.md`) because real-time delivery guarantees to Telegram/WhatsApp webhooks are also subject to overload.
- **F-ARCH-10** (Docker networking) overlaps with DevOps/deployment configuration and impacts every downstream service (agents, skills, channels) that reads `.env`.

---

## Confidence per Finding

| ID | Confidence | Rationale |
|----|------------|-----------|
| F-ARCH-01 | High | Explicit hardcoded URLs and ports in `.env`, `docker-compose.yml`, and `skill.yaml`. |
| F-ARCH-02 | High | Explicit fire-and-forget pattern (`asyncio.create_task`) with no retry or outbox documented. |
| F-ARCH-03 | High | Inline TypeScript unions with no version field; no schema registry tool mentioned anywhere. |
| F-ARCH-04 | High | Redis Streams usage is explicit; absence of backpressure/circuit breakers is a documented omission. |
| F-ARCH-05 | High | PATCH endpoint and drag-and-drop are explicit; absence of locking is a documented omission. |
| F-ARCH-06 | High | No version prefix in any endpoint listed across architecture and agent docs. |
| F-ARCH-07 | Medium-High | No mention of graceful shutdown or reconnection; inference from standard WebSocket behavior is reliable. |
| F-ARCH-08 | High | Explicit "Not Kubernetes / single-machine" statement in `09-tech-stack.md`. |
| F-ARCH-09 | High | Observability section explicitly lists Langfuse first and OpenTelemetry as optional alternative. |
| F-ARCH-10 | High | `.env` contents and `docker-compose.yml` service definitions are explicit and contradictory. |
| F-ARCH-11 | High | Explicit "No auth internally" statement in security boundaries table. |

---

## Summary

Out of 11 findings, **5 are Critical** and relate to production-stopping risks: hardcoded service discovery (F-ARCH-01), Keeper restart data loss (F-ARCH-02), missing schema registry (F-ARCH-03), task state race conditions (F-ARCH-05), and broken Docker networking (F-ARCH-10). The architecture is well-suited for a local developer workstation but lacks the resiliency primitives required for a production multi-agent system. Addressing the Critical gaps before adding new agent types or scaling beyond a single machine will prevent the specification-level failures that account for 41.77% of MAST taxonomy incidents.
