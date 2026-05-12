# Agent 11 — Keeper Reliability & Local Model Ops

## Domain Summary

The Keeper is ISLI's silent backbone — a single Python service running local Ollama models (qwen3 family + nomic-embed-text) that handles embeddings, context summarization, heartbeat validation, and memory compaction. Because it is a single-machine, single-process dependency with no described failover, every Keeper failure becomes a system-wide degradation event.

---

## Findings Table

| ID | Severity | Category | Description | Evidence | Recommendation |
|----|----------|----------|-------------|----------|----------------|
| K01 | Critical | Reliability | No measured accuracy data for qwen3:0.6b structured JSON output under load. The documentation asserts it is the "smallest reliable JSON model" but provides no benchmarks, success-rate curves, or load-test results. | `02-keeper.md` lines 17-20: heartbeat model recommended with no quantitative justification. | Run a structured-output benchmark (n=1,000+ requests, varying concurrency) for qwen3:0.6b and qwen3:1.7b. Enforce schema validation with at least one retry before accepting output. |
| K02 | Critical | Reliability | No fallback exists if Ollama or the Keeper fails. Context injection, heartbeat validation, and compaction all cease, and agents are not described as having a degraded mode. | `02-keeper.md`: Keeper is the "silent backbone" with no redundancy or failover architecture described. `09-tech-stack.md`: single-machine target. | Implement a circuit-breaker that falls back to a cloud model (e.g., Claude Haiku or GPT-4o-mini) for summarization and heartbeat validation when Ollama is unreachable. |
| K03 | High | Performance | No warm-up or keep-alive strategy prevents cold-start latency after restarts. Ollama must load models into RAM/VRAM on first request. | `02-keeper.md` and `09-tech-stack.md`: no warm-up scripts, no `ollama pull` in startup, no keep-alive endpoints described. `docker-compose.yml` skeleton has no init container or health-check warm-up. | Add a startup probe that pre-loads all three models (`ollama pull` + dummy inference) before marking the Keeper as ready. |
| K04 | High | Reliability | Malformed JSON from local models has no described fallback or retry path. Heartbeat validation and context injection depend on parseable JSON, yet no error handling is documented. | `02-keeper.md` lines 61-68: shows ideal JSON output schema with no malformed-output handling. Heartbeat validation flow (`02-keeper.md` lines 76-91) assumes clean JSON. | Wrap every local-model JSON call in a retry loop (max 3) with exponential backoff. If all retries fail, fall back to a regex-safe heuristic or cloud model. |
| K05 | High | Operations | Model versions are not pinned. The Ollama runtime image uses `ollama/ollama:latest`, and model tags (e.g., `qwen3:0.6b`) are mutable aliases that can shift on upstream re-publishes. | `09-tech-stack.md` line 181: `image: ollama/ollama:latest`. `02-keeper.md` line 131: `heartbeat: qwen3:0.6b` with no digest or manifest hash. | Pin the Ollama container image to a specific digest. Pin each model to a specific manifest digest (Ollama supports `@sha256-...` references) and verify on startup. |
| K06 | High | Performance | Concurrent Keeper workloads (embeddings + summarization + heartbeat + compaction) hit a single Ollama instance with no concurrency controls, queue depth limits, or request prioritization. | `02-keeper.md`: lists five concurrent responsibilities. `09-tech-stack.md`: Ollama runs as a single container with no request-queuing configuration. | Add an async request queue in the Keeper (e.g., `asyncio.Semaphore` or a dedicated worker pool) that limits in-flight Ollama requests and prioritizes heartbeat validation over compaction. |
| K07 | Medium | Observability | Compaction summary quality is completely unmonitored. There is no metric, human review loop, or automated score to verify that summaries preserve critical information. | `02-keeper.md` lines 94-99: compaction described but no quality gate. `03-memory.md` line 91: "importance score set by Keeper" with no validation of score accuracy. | Introduce a summary-quality metric (e.g., ROUGE-L against a reference cloud-model summary, or a semantic similarity score) and alert when it drops below a threshold. |
| K08 | Medium | Performance | No latency SLOs or measured distributions exist for any Keeper endpoint. | `02-keeper.md` lines 111-120: API endpoints listed with no latency targets. `09-tech-stack.md`: FastAPI throughput cited for Core API, not Keeper/Ollama. | Define p50/p95/p99 SLOs for `/embed`, `/summarize`, and `/context/inject`. Instrument them and add a latency budget alert. |
| K09 | Medium | Scalability | The architecture explicitly rules out scaling beyond a single machine, making Ollama a hard capacity ceiling with no horizontal path. | `09-tech-stack.md` line 65: "Not Kubernetes: ISLI targets single-machine deployment. K8s would be overkill." `02-keeper.md`: single localhost Ollama host. | Document a future scaling path (e.g., Ollama replica set behind a local load balancer, or remote Ollama via LAN) even if not implemented today. |
| K10 | Medium | Reliability | No resource limits or contention management for Ollama CPU/GPU memory. Running multiple models concurrently can cause thrashing or OOM kills. | `09-tech-stack.md` line 184: GPU reservation commented out. No memory or CPU limits in docker-compose skeleton. `02-keeper.md`: three distinct models recommended. | Add Docker `deploy.resources.limits` for memory and (if GPU available) VRAM. Consider running embeddings on CPU-only to reserve GPU for summarization. |
| K11 | Medium | Reliability | ChromaDB runs in embedded mode inside the Keeper process, creating a single-process vector-store SPOF. | `09-tech-stack.md` lines 42-44: "Embedded mode (no server needed)... ChromaDB runs in the same process." | Evaluate switching to ChromaDB server mode or another vector DB with a standalone process so the vector store survives Keeper restarts. |
| K12 | Low | Observability | Langfuse observability is optional and may be absent in default deployments, leaving Keeper operations untraced. | `09-tech-stack.md` lines 131-134: Langfuse keys are empty in the `.env` template. `02-keeper.md`: no Keeper-specific logging or metrics described. | Make structured logging (JSON) mandatory for the Keeper and export basic metrics (request count, latency, Ollama errors) to Prometheus or stdout even when Langfuse is disabled. |
| K13 | Low | Reliability | Session memory grows unbounded if compaction fails because the Keeper is the sole component that trims Redis buffers. | `03-memory.md` lines 59-62: "Keeper trims buffer when token_count > compaction_threshold." No Core API fallback trimming described. | Add a Core API safety valve that trims the oldest messages from Redis when the buffer exceeds a hard ceiling, even if the Keeper is unreachable. |

---

## Cross-Cutting Concerns

1. **Single Point of Failure Cascade**: The Keeper failure does not just stop one service — it eliminates context injection (agents lose coherence), heartbeat validation (anomaly detection goes blind), compaction (memory costs balloon), and embeddings (RAG stalls). These are not independent failures; they cascade.

2. **Local Model Trust Boundary**: ISLI places high-trust system functions (anomaly detection, health validation) on a 0.6B parameter model with no accuracy verification. In production, this is equivalent to running a monitoring system on an uncalibrated sensor.

3. **Observability Blind Spot**: The Keeper is described as "silent" and "never appears on the Kanban board." This design philosophy risks operational invisibility — if it is intentionally hidden from users, it must be doubly visible to operators via metrics and alerts.

---

## Confidence per Finding

| ID | Confidence | Rationale |
|----|------------|-----------|
| K01 | High | The docs make qualitative claims with zero quantitative evidence; absence of benchmarks is verifiable. |
| K02 | High | No failover architecture is described in any of the three documents; the single-machine constraint is explicit. |
| K03 | High | Docker-compose and configs contain no warm-up logic; Ollama's cold-start behavior is a known runtime characteristic. |
| K04 | High | JSON schemas are shown but no error-handling paths are documented; absence of fallback is verifiable. |
| K05 | High | `ollama/ollama:latest` is literal text in the docker-compose; model tag mutability is a known Ollama behavior. |
| K06 | High | Multiple workloads target one Ollama instance; no rate-limit or queue configuration is present. |
| K07 | Medium | It is possible quality checks exist in unreviewed code, but no documentation mentions them. |
| K08 | High | No latency metrics or SLOs are present in any reviewed file. |
| K09 | High | Single-machine targeting is explicitly stated; no future scaling path is mentioned. |
| K10 | High | Resource limits are commented out or absent in the provided docker-compose skeleton. |
| K11 | High | Embedded mode is explicitly chosen; no HA alternative is discussed. |
| K12 | Medium | Langfuse optional status is clear, but the team may have other logging not documented here. |
| K13 | Medium | The Redis trimming dependency is documented, but unreviewed code might contain a fallback. |

---

*Report generated by Agent 11 (Keeper Reliability & Local Model Ops) on 2026-05-11.*
