# ISLI — Intelligent System for Local Intelligence

Modular, production-grade multi-agent digital assistant system where **no single powerful model acts as orchestrator**. Instead, a lightweight local model (the *Keeper*) handles all background intelligence — embeddings, context summarization, heartbeats, and routing signals — while specialized agents use their own assigned models (API or local) for domain-specific work.

## Project Overview

*   **Architecture**: Event-driven, service-oriented multi-agent system.
*   **Central Nervous System**: A Shared Blackboard pattern implemented as a real-time **Kanban Board**.
*   **Memory Model**: 4-tier tiered memory (Session / Episodic / Semantic / Archival).
*   **Security**: Restricted execution sandboxes, internal service authentication (JWT), and hybrid PII scrubbing.
*   **Resilience**: Agent turn checkpointing, lease-based task ownership, hard retry E-stops, and Saga logs for atomic compensation.

## Project Structure

| Directory | Service | Tech Stack | Port | Description |
|-----------|---------|------------|------|-------------|
| `isli-core/` | **Core API** | FastAPI, Redis, PostgreSQL | 8000 | Agent lifecycle, task bus, skill proxy, cost control. |
| `isli-keeper/` | **Keeper** | Python, Ollama (7B) | 8001 | Background intelligence sidecar; local context & summarization. |
| `isli-board/` | **Kanban UI** | React, Vite, Tailwind | 5173 | Real-time task board via WebSocket event bus. |
| `isli-skills/` | **Skills Registry**| Python (Microservices) | 8100+ | Stateless utility services and self-evolving agent-written skills. |
| `isli-channels/` | **Gateway** | Python | 8200+ | Telegram, WhatsApp, Web, and Email adapters. |
| `isli-workspace/`| **Workspace** | Python | 8300 | Per-agent sandboxed filesystem for temporary data and skill code. |
| `infra/` | Infrastructure | Terraform, Traefik | — | Deployment definitions and cloud configuration. |
| `Docs/` | Documentation | Markdown | — | Canonical architectural designs and design principles. |
| `Memory/` | Project Memory | Markdown | — | Research reports, session logs, and development conventions. |

## Building and Running

### Quick Start (Docker)
The recommended way to run the full stack is via Docker Compose.
```powershell
# Copy environment template
copy .env.example .env

# Start all services
docker compose up --build
```

### Local Development (Native)
Use the provided script to start services natively (requires Python 3.12+ and Node.js).
```bash
./scripts/run-local.sh
```

### Testing
Each Python service uses `pytest`. `isli-core` is the most extensively tested component.
```bash
cd isli-core
pip install -e ".[dev]"
pytest
```

## Development Conventions

### 1. Canonical Context
- **Design Intent**: Read `Docs/` before making structural changes. These are the single source of truth for architectural requirements.
- **Evolutionary State**: Refer to `Memory/ISLI-Research-Report.md` and subsequent hardening plans for the current "Battle-Hardened" state of the logic.

### 2. Implementation Guardrails
- **Fail-Safe Security**: Always prioritize security over availability. If the PII scrubber or Logic Judge fails, the system must block or fail-safe to masked data.
- **Asynchronous by Design**: Task creation is instantaneous. Background workers (`ContextInjectorWorker`) handle heavy synthesis.
- **Durable State**: Every agent interaction must be persisted as a `Task` or `CheckPoint`. No transient state in multi-turn reasoning.
- **Lease-based Ownership**: Agents have a 5-minute lease on tasks. Stalled tasks are automatically recovered by the `CheckpointRecoveryWorker`.
- **Risk-based Gating**: The Local Logic Judge is only called for high-risk skills (`shell-exec`, `file-write`, etc.) to minimize latency.

### 3. Service Communication
- **Authentication**: All service-to-service calls MUST include an `X-Internal-Auth` JWT token.
- **Real-Time**: UI updates are broadcast via the FastAPI WebSocket bus backed by Redis Pub/Sub. No polling in the frontend.
- **Saga Pattern**: Record compensatory actions in the `saga_log` for any multi-step delegation that requires atomicity.

### 4. Code Style
- **Python**: Strict typing (`mypy`), `ruff` for linting, and `structlog` for structured JSON logging.
- **TypeScript**: React 18+, functional components with hooks, and `@tanstack/react-query` for data fetching where WebSockets are not applicable.
