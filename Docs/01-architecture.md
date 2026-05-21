# 01 — ISLI System Architecture

## Overview

ISLI is built as a **layered, event-driven multi-agent system**. The architecture inverts the common pattern: instead of a powerful orchestrator model dispatching to weak workers, ISLI uses a *silent local Keeper* for all background intelligence, and lets each agent be sovereign within its domain, communicating through a shared Kanban board.

---

## Architecture Layers

```
╔══════════════════════════════════════════════════════════════════╗
║  LAYER 5 — PRESENTATION                                         ║
║  React Kanban UI  ·  Workspace File Manager  ·  Agent Details   ║
╠══════════════════════════════════════════════════════════════════╣
║  LAYER 4 — CHANNEL GATEWAY                                      ║
║  Telegram Bot  ·  WhatsApp Business  ·  Web  ·  Email           ║
╠══════════════════════════════════════════════════════════════════╣
║  LAYER 3 — AGENT RUNTIME                                        ║
║  Agent A  ·  Agent B  ·  Agent N  ·  (each with own API key)    ║
╠══════════════════════════════════════════════════════════════════╣
║  LAYER 2 — CORE SERVICES                                        ║
║  FastAPI Core API  ·  Keeper  ·  Task Bus  ·  Skills Registry   ║
╠══════════════════════════════════════════════════════════════════╣
║  LAYER 1 — DATA                                                 ║
║  PostgreSQL  ·  Redis  ·  ChromaDB (vectors)  ·  SQLite (local) ║
╚══════════════════════════════════════════════════════════════════╝
```

---

## Component Map

### Core API (`isli-core`)
- **Runtime**: Python 3.12 + FastAPI + Uvicorn
- **Responsibilities**:
  - Agent registration and lifecycle management
  - Task creation and state transitions
  - WebSocket event bus (agent → UI)
  - Skill invocation proxy
  - Auth (JWT-based, per agent)

### The Keeper (`isli-keeper`)
- **Runtime**: Python process → Ollama (local)
- **Responsibilities**: See `02-keeper.md`
- Runs as a **sidecar** to the Core API
- Never exposed to users or external channels

### Agent Runtime (`isli-agent`)
- Each agent is a **standalone Python process** (or Docker container)
- Connects to Core API via REST + WebSocket
- Has a unique `agent_id`, `agent_name`, `model_config`, `channel_config`
- Gets pre-hydrated context from Keeper before each task execution

### Kanban Board (`isli-board`)
- **Frontend**: React + TypeScript + Vite + TailwindCSS
- **Backend**: Core API WebSocket endpoint
- Real-time task card streaming via SSE/WebSocket
- Columns: `Inbox → Assigned → In Progress → Blocked → Done → Archived`

### Skills Registry (`isli-skills`)
- HTTP microservices (no AI, no API keys)
- Registered via YAML manifests
- Discoverable by agents at runtime
- Examples: web-fetch, pdf-extract, file-write, db-query, send-email

### Channel Gateway (`isli-channels`)
- Each channel is a thin adapter that forwards messages to a specific agent
- Telegram adapter, WhatsApp adapter, etc.
- See `07-channels.md`

### Workspace Manager (`isli-workspace`)
- **Runtime**: Python 3.12 + FastAPI
- **Responsibilities**:
  - Sandboxed file management for agents
  - Quota enforcement per workspace (100MB default)
  - Secure file read/write/list/delete operations
- **Access**: Proxied via `isli-core` with path traversal validation.

---

## Data Flow: User Message → Agent Response

```
User sends message via Telegram
         │
         ▼
Telegram Channel Gateway
  → parses update
  → creates Task in Core API (status: inbox)
         │
         ▼
Core API
  → emits Kanban event (card appears on board)
  → notifies assigned agent via WebSocket
         │
         ▼
Keeper (pre-turn)
  → fetches pre-computed **Structured Session Journal** from Tier 1 memory
  → fetches last 3 raw messages for immediate context
  → fetches relevant episodic/semantic memories via vector search
  → assembles the **Fast-Path Context Block** (no LLM latency)
  → returns: { context_injection, relevant_memories }
         │
         ▼
Agent (e.g., Agent B)
  → receives task + Keeper context injection
  → calls its assigned model API (e.g., Claude, GPT-4o)
  → may invoke Skills (web search, file ops, etc.)
  → produces response
         │
         ▼
Core API
  → task status → Done
  → **JournalWorker** (background) triggers on task completion:
    → calls Keeper to update structured journal incrementally
    → truncates session messages to last 10 turns
  → Keeper stores result summary in episodic memory (Tier 2)
  → Kanban card updated (real-time)
         │
         ▼
Channel Gateway
  → sends response back to user via Telegram
```

---

## Inter-Agent Communication

ISLI **does not use direct agent-to-agent API calls**. All inter-agent communication goes through the Kanban board via **Task Delegation**:

```
Agent A needs Agent B to do something
  → Agent A creates a new Task card (type: delegation)
  → assigns to Agent B
  → waits for card status = Done (via polling or webhook)
  → reads result from task.output field
```

This design ensures:
- Full audit trail of every agent interaction
- No hidden message passing
- Human can inspect, pause, or redirect any delegation at any time

---

## Process Layout (Single Machine / Dev)

```
isli/
├── isli-core/          ← FastAPI core service (port 8000)
├── isli-keeper/        ← Keeper sidecar (port 8001, local only)
├── isli-workspace/     ← Workspace manager (port 8300, local only)
├── isli-board/         ← React frontend (port 5173)
├── isli-skills/        ← Skill microservices (ports 8100-8199)
├── isli-channels/      ← Channel adapters (port 8200+)
└── docker-compose.yml  ← Full stack orchestration
```

---

## Security Boundaries

| Boundary | Policy |
|----------|--------|
| Keeper → outside world | **Never exposed**. Localhost only. |
| Agent ↔ Core API | JWT per agent. Scoped permissions. |
| Skills | No auth internally. RBAC enforced by Core API proxy. |
| Channels | Webhook secret validation. Rate limited. |
| User ↔ Board | Session token. HTTPS only in production. |

---

## Architecture Gaps Identified (2026-05-11 Research)

The following gaps were identified during a parallel 12-agent research review. They represent the delta between documented architecture and production readiness:

### Critical
- **Hardcoded service discovery** — all services point to `localhost` and static ports with no registry or DNS-based discovery.
- **Keeper restart loses data** — `store_episodic()` is fire-and-forget with no retry or outbox pattern.
- **No event schema registry** — WebSocket and Redis payloads are unversioned and unenforced.
- **Task state race conditions** — concurrent PATCH updates from agents and humans lack optimistic locking.
- **Broken Docker networking** — `.env` template uses `localhost` which fails in Docker Compose.

### High
- **Missing backpressure/circuit breakers** on the Kanban event bus and WebSocket fan-out.
- **No API versioning contract** between Core API and agents.
- **Distributed tracing treated as optional** — OpenTelemetry is listed as "or Langfuse" rather than mandatory.
- **Unauthenticated internal skill network** — skills have no auth internally, creating lateral movement risk.

### Medium
- **No load balancer or service mesh** — explicit single-machine assumption limits scaling.
- **No graceful shutdown / connection draining** — in-flight tasks can lose state on restart.

> See `Memory/ISLI-Research-Report.md` for full details and recommendations.