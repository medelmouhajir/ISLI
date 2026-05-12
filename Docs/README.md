# ISLI — Intelligent System for Local Intelligence

> **"A swarm of specialized minds, governed by a quiet local keeper."**

ISLI is a modular, production-grade multi-agent digital assistant system where **no single powerful model acts as orchestrator**. Instead, a lightweight local model (the *Keeper*) handles all background intelligence — embeddings, context summarization, heartbeats, and routing signals — while any number of specialized agents use their own assigned API-based models for their domain work.

---

## Documentation Index

| File | Description |
|------|-------------|
| [`README.md`](./README.md) | This file — overview and index |
| [`01-architecture.md`](./01-architecture.md) | System architecture, component map, data flow |
| [`02-keeper.md`](./02-keeper.md) | The Keeper — local hidden agent specification |
| [`03-memory.md`](./03-memory.md) | Memory system — 4-tier design (session / episodic / semantic / archival) |
| [`04-agents.md`](./04-agents.md) | Agent specification — roles, configs, lifecycle |
| [`05-kanban.md`](./05-kanban.md) | Kanban board — real-time task visibility UI |
| [`06-skills.md`](./06-skills.md) | Skills system — microservice design and registry |
| [`07-channels.md`](./07-channels.md) | Channels & gateways — Telegram, WhatsApp, and more |
| [`08-failure-modes.md`](./08-failure-modes.md) | 14 killing points and ISLI mitigations |
| [`09-tech-stack.md`](./09-tech-stack.md) | Full technology stack rationale |
| [`10-roadmap.md`](./10-roadmap.md) | Phased development roadmap — **all phases complete** |
| [`11-dpo-assessment.md`](./11-dpo-assessment.md) | GDPR Art. 37 DPO necessity assessment |
| [`12-scale-out-topology.md`](./12-scale-out-topology.md) | Production scale-out architecture |

---

## Core Concepts at a Glance

```
┌─────────────────────────────────────────────────────┐
│                     USER / UI                       │
│               React Kanban Dashboard                │
└──────────────────────┬──────────────────────────────┘
                       │ WebSocket (SSE)
┌──────────────────────▼──────────────────────────────┐
│                  ISLI CORE API                      │
│           FastAPI  ·  Redis  ·  PostgreSQL          │
│    Cost Control · Circuit Breakers · OTel Traces   │
└──────┬────────────┬───────────────┬─────────────────┘
       │            │               │
  ┌────▼───┐  ┌─────▼────┐  ┌──────▼──────┐
  │KEEPER  │  │ AGENT A  │  │  AGENT B    │  ...
  │(Local) │  │(API key) │  │ (API key)   │
  │Ollama  │  │Claude/   │  │GPT-4o/      │
  └────────┘  │Gemini/...│  │Mistral/...  │
              └──────────┘  └─────────────┘
```

**The Keeper never speaks to the user.** It runs silently: compressing memory, generating embeddings, writing heartbeat summaries, and injecting minimal context into agents before each turn.

---

## Design Principles

1. **No God-Model** — There is no expensive orchestrator model. The Keeper is cheap, fast, and local.
2. **Heartbeat-first** — Every agent proves liveness via a Keeper-validated heartbeat, not a full LLM round-trip.
3. **Kanban as nervous system** — All inter-agent communication surfaces as task cards. No hidden message passing.
4. **Skills are dumb** — Skills are pure utility microservices: no AI, no API keys, minimal tokens.
5. **Channels are first-class** — Each agent can own one or more channels (Telegram, WhatsApp, email) as its primary interface.
6. **Failure is designed for** — Every known multi-agent failure mode (MAST taxonomy) has an explicit architectural counter-measure.

---

## Implementation Status

All 7 implementation phases are **complete** (2026-05-11):

| Phase | Theme | Status |
|-------|-------|--------|
| 0 | Foundation | Complete — docker-compose, Alembic, OTel, health checks |
| 1 | Safety & Governance | Complete — token budgets, GDPR fix, circuit breakers, SSRF |
| 2 | Resilience & Recovery | Complete — checkpoints, e-stop, fallback, chaos suite |
| 3 | Channels & Delivery | Complete — idempotency, retry DLQ, ordering, chunking |
| 4 | Memory & Integrity | Complete — model versioning, outbox, dedup, partitioning |
| 5 | Cost Optimization | Complete — rate card, tiering, semantic cache, TCO |
| 6 | Compliance | Complete — SAR pipeline, audit hashes, AES-256-GCM, TIA |
| 7 | Scale-Out | Complete — Traefik, Terraform, ECS Fargate, blue/green, CI/CD |

## Research & Improvement Tracking

A comprehensive 12-agent parallel research review was conducted on 2026-05-11. It identified **142 findings** across architecture, security, scalability, observability, memory, coordination, resilience, deployment, cost, compliance, keeper reliability, and channels.

- **Full Report:** `Memory/ISLI-Research-Report.md` — executive summary, risk heat map, and prioritized recommendations
- **Phased Roadmap:** `Docs/10-roadmap.md` — 8-phase implementation plan (all phases now complete)

**Key themes addressed:**
1. ~~The "dev-only" single-machine assumption blocks production scaling~~ → Terraform + ECS Fargate + Traefik LB
2. ~~Documented mitigations (F1–F16) exist as architectural intent with zero implementation code~~ → All mitigations implemented
3. ~~The Keeper is an unmonitored single point of failure~~ → Circuit breaker + cloud fallback (Anthropic/OpenAI)
4. ~~GDPR Article 17 directly conflicts with append-only Tier 4 archival memory~~ → Soft-delete + crypto-shredding + purge job
5. ~~Structural resilience patterns (circuit breakers, checkpointing, BICR governance) are absent~~ → All patterns implemented
