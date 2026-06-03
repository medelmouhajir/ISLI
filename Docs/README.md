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
| [`05-kanban.md`](./05-kanban.md) | Dashboards — Kanban, system telemetry, and **Observability Hub** (`/logs`) |
| [`06-skills.md`](./06-skills.md) | Skills system — microservice design and registry |
| [`07-channels.md`](./07-channels.md) | Channels & gateways — Telegram, WhatsApp, and more |
| [`08-failure-modes.md`](./08-failure-modes.md) | 28 documented failure modes and ISLI mitigations (MAST taxonomy + ISLI-specific) |
| [`09-tech-stack.md`](./09-tech-stack.md) | Full technology stack rationale |
| [`10-roadmap.md`](./10-roadmap.md) | Phased development roadmap — **all phases complete** |
| [`11-dpo-assessment.md`](./11-dpo-assessment.md) | GDPR Art. 37 DPO necessity assessment |
| [`12-scale-out-topology.md`](./12-scale-out-topology.md) | Production scale-out architecture |
| [`13-immersive-chat-ui.md`](./13-immersive-chat-ui.md) | Agent-driven UI components inline in chat |
| [`14-management-cli.md`](./14-management-cli.md) | Management CLI (`isli`) — installer and operational tool |

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
  ┌─────────────────────────────────────────┐
  │  AUDIO (Local) — STT · TTS              │
  │  faster-whisper · piper-tts             │
  └─────────────────────────────────────────┘
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

All implementation phases are **complete** (2026-06-01):

| Phase | Theme | Status |
|-------|-------|--------|
| 0 | Foundation | Complete — docker-compose, Alembic, OTel, health checks |
| 1 | Safety & Governance | Complete — token budgets, GDPR fix, circuit breakers, SSRF |
| 2 | Resilience & Recovery | Complete — checkpoints, e-stop, fallback, chaos suite |
| 3 | Channels & Delivery | Complete — idempotency, retry DLQ, ordering, chunking |
| 4 | Memory & Integrity | Complete — model versioning, outbox, dedup, partitioning |
| 5 | Cost Optimization | Complete — rate card, tiering, semantic cache, TCO, **cost analytics dashboard** (`/costs`), agent usage reporting endpoint |
| 8 | Local Model Management | Complete (2026-05-22) — **Keeper Settings** (`/settings/keeper`) for pulling/switching Ollama `gen`/`embed` models via Core proxy |
| 9 | Runtime Configuration | Complete (2026-05-24) — **General Settings** (`/settings/general`) exposing 12 operational knobs via DB-backed `SystemSetting` store with 30s cache |
| 10 | WhatsApp Access Modes | Complete (2026-05-29) — **Five access modes** (`opt_in`, `open`, `whitelist`, `closed`, `scheduled`) with per-JID rate limiting, time-window gating, and Board UI conditional configuration |
| 11 | Local Audio Service | Complete (2026-05-29) — **`isli-audio`** microservice with faster-whisper STT and piper-tts TTS; Telegram voice auto-transcription; agent-level `speech-to-text` and `text-to-speech` skills; managed from Board UI (`/settings/keeper`) alongside Ollama models |
| 12 | Board UI Voice Input | Complete (2026-05-29) — Mic button in Sessions/Conversations chat input; browser `MediaRecorder` → local Whisper STT → text inserted into input with auto-send toggle |
| 13 | Immersive Chat UI | Complete (2026-05-30) — Agent-driven inline React components (`table`, `card`, `button_group`, `comparison_table`, `form`, `json_viewer`, `status_timeline`, `metric_grid`) with per-message persistence; user interactions fire back as action messages; Telegram/WhatsApp `text_fallback`; Phase 2 editable Form + 3 display components delivered |
| 14 | Git Integration | Complete (2026-05-30) — **9 git skills** (`git-clone`, `git-status`, `git-commit`, `git-push`, `git-pull`, `git-branch-list`, `git-branch-create`, `git-checkout`, `git-log`) hosted in `isli-workspace` with GitPython; sandboxed via `resolve_path()`; URL validation blocks `file://`; typed SDK exceptions for graceful ReAct recovery |
| 15 | Secret Vault | Complete (2026-05-31) — **`get-secret` skill** with per-agent encrypted vault (AES-256-GCM in PostgreSQL); admin-only Board UI (`/agents/:id/secrets`) for create/delete; inline Core handler decrypts on demand; every read is audit-logged; cross-agent isolation via `(agent_id, name)` unique index; SDK `get_secret()` with typed `SecretNotFoundError` / `SecretAccessError` |
| 16 | Model Routing | Complete (2026-05-31) — **Hybrid A+B routing** (`TaskComplexityScorer` heuristic + Keeper LLM decision) for per-task/per-session dynamic model selection; session-lifetime lock; explicit three-tier fallback (routed → default → halt); Board UI toggle + JSON editor for `secondary_models` with `cost_tier` filtering |
| 17 | Streaming Modes | Complete (2026-05-31) — **Five live streaming modes** (`silent`, `text`, `tools`, `trace`, `debug`) with bidirectional WebSocket event flow; per-session override via `session_metadata`; Redis draft persistence for reconnect resilience; debug prompt isolation (Redis-only + admin REST); `StreamingMessageBubble`, `ToolCallBar`, `ProcessTracePane` components in Board UI |
| 18 | Prompt Management | Complete (2026-05-31) — **Board UI `/settings/prompts`** for editing `prompts.yaml` via structured cards and per-tab raw-YAML mode; `GET/PUT /v1/prompts` with file-mtime optimistic locking (409 conflict), merge-on-write preserving unknown keys, best-effort Keeper cache reload; agent-restart banner reminding that runners load prompts at startup |
| 19 | Unified Notifications | Complete (2026-06-01) — **Event-driven notification engine** with `Notification` + `NotificationPreference` DB models; unified Redis listener dispatch; in-app inbox (`/notifications`) with unread badge, filter tabs, mark-all-read, dismiss; digest batching (`/digests`) with `LRANGE`+`LTRIM` idempotency; quiet hours with `zoneinfo` timezone validation; Telegram escalation with Markdown formatting; per-agent-per-user rate limiting (20/hour); `notify_user` SDK tool with `NotificationRateLimitError`/`NotificationDeliveryError`; `POST /v1/notifications/send` agent-facing endpoint; **tool description neutralization + system prompt instruction** to prevent LLM over-refusal on benign user-facing tools; **session metadata injection** (`=== CURRENT SESSION ===` block) so agents always know the target `user_id` |
| 20 | Agent Peer Awareness | Complete (2026-06-01) — **Per-agent `known_agent_ids`** JSON column enabling directional delegation graphs; asymmetric peer relationships (A knows B ≠ B knows A); Board UI toggle pills in `AgentDetailPage` with dirty detection; `GET /v1/agents/{id}/peers` endpoint resolving IDs into full metadata for SDK consumption; config-changed event triggers runner refresh |
| 21 | Hardening & Monitoring | Complete (2026-06-02) — **Internal Priority Queue (P0-P3)** in Keeper ensuring critical path (context injection, heartbeats) bypasses background backlog; **Adaptive Throttling** (429) for background tasks (embed, journal) when depth > 50; **Per-priority timeouts** (45s for P0) to prevent silent HTTP hangs; **Latency SLO Monitoring** (p50/p95/p99) with automated health status (healthy/degraded/critical); **Queue Depth Observability** in Board UI /dashboard |
| 22 | Skill Metadata Updates | Complete (2026-06-03) — **`update-skill`** endpoint in `isli-skills` (`POST /update`) and SDK tool (`update_skill`) allowing agents to modify existing skill metadata (`description`, `category`, `workspace_path`, `endpoint`, `health_endpoint`, `agent_id`) without triggering review; preserves `usage_count` and `created_at`; wired through Core skill proxy with `SKILL_UPDATE_URL` env var |
| 6 | Compliance | Complete — SAR pipeline, audit hashes, AES-256-GCM, TIA |
| 7 | Scale-Out | Complete — Traefik, Terraform, ECS Fargate, blue/green, CI/CD |

## Research & Improvement Tracking

A comprehensive 12-agent parallel research review was conducted on 2026-05-11. It identified **142 findings** across architecture, security, scalability, observability, memory, coordination, resilience, deployment, cost, compliance, keeper reliability, and channels.

- **Full Report:** `Memory/ISLI-Research-Report.md` — executive summary, risk heat map, and prioritized recommendations
- **Phased Roadmap:** `Docs/10-roadmap.md` — 8-phase implementation plan (all phases now complete)

**Key themes addressed:**
1. ~~The "dev-only" single-machine assumption blocks production scaling~~ → Terraform + ECS Fargate + Traefik LB
2. ~~Documented mitigations (F1–F16) exist as architectural intent with zero implementation code~~ → All mitigations implemented
3. ~~The Keeper is an unmonitored single point of failure~~ → Honest 503 propagation + structured logging + dashboard telemetry (Keeper is local-only by design; resilience lives in Core/SDK circuit breakers)
4. ~~GDPR Article 17 directly conflicts with append-only Tier 4 archival memory~~ → Soft-delete + crypto-shredding + purge job
5. ~~Structural resilience patterns (circuit breakers, checkpointing, BICR governance) are absent~~ → All patterns implemented
