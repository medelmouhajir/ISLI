# ISLI — Intelligent System for Local Intelligence

ISLI is a modular, production-grade multi-agent system designed to avoid central orchestration bottlenecks. It utilizes a lightweight local model (the **Keeper**) for background intelligence (summarization, context injection, routing) while specialized agents handle domain-specific tasks via their own assigned models (local or API-based). All agent interactions are coordinated through a real-time **Shared Blackboard** (Kanban Board).

## Project Overview

*   **Core Philosophy**: Invert the "central orchestrator" pattern. Use a silent local sidecar (Keeper) for system-level reasoning and a Kanban board for explicit, human-inspectable task delegation.
*   **Central Component**: `isli-core` (FastAPI) acts as the task bus and agent lifecycle manager.
*   **Real-time UI**: `isli-board` (React) provides a live view of all agent activities and allows human intervention.
*   **Keeper Model**: `qwen2.5-coder:1.5b` (Local via Ollama). Optimized for CPU-only environments with permanent memory loading (`keep_alive=-1`) and 8-thread core pinning.
*   **Memory Model**: 4-tier tiered memory:
    1.  **Session**: High-velocity transient state (Redis).
    2.  **Episodic**: Summarized interaction history (ChromaDB/PostgreSQL).
    3.  **Semantic**: Long-term RAG knowledge (ChromaDB).
    4.  **Archival**: Immutable audit logs (PostgreSQL).

## Project Structure

| Directory | Service | Tech Stack | Port | Description |
| :--- | :--- | :--- | :--- | :--- |
| `isli-core/` | **Core API** | Python 3.12, FastAPI, asyncpg, Redis | 8000 | The "brain" of the system. Manages tasks, agents, and event broadcasting. |
| `isli-board/` | **Kanban UI** | React 18, Vite, Tailwind, TanStack Query | 5173 | Real-time dashboard for task management and agent monitoring. |
| `isli-keeper/` | **Keeper** | Python, Ollama | 8001 | Sidecar for background intelligence; handles context summarization. |
| `isli-skills/` | **Skills Registry**| Python | 8100+ | Microservices providing tools (web-fetch, web-search, db-query, etc.) to agents. |
| `isli-channels/` | **Gateway** | Python | 8200+ | Adapters for Telegram, WhatsApp, Web, and Email. |
| `isli-workspace/`| **Workspace** | Python | 8300 | Sandboxed file manager for agents. |
| `isli-agent-sdk/`| **Agent SDK** | Python | — | Standard library for building and running ISLI-compatible agents. |
| `infra/` | **Infrastructure** | Terraform, Traefik, Nginx | — | Deployment configurations and infrastructure-as-code. |
| `Docs/` | **Documentation** | Markdown | — | Architectural designs and design principles. |
| `Memory/` | **Project Memory** | Markdown | — | Research reports, session logs, and development conventions. |

## Building and Running

### Full Stack (Docker - Recommended)
The fastest way to spin up the entire environment:
```bash
# Enter project directory
cd /home/projects/ISLI_AI/ISLI

# Setup environment
cp .env.example .env

# Start all services
docker compose up --build
```

### Native Development

#### Backend (isli-core)
```bash
cd isli-core
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn isli_core.main:app --reload --port 8000
```

#### Frontend (isli-board)
```bash
cd isli-board
npm install
npm run dev
```

### Testing
Each service uses `pytest`. Run core tests with:
```bash
cd isli-core
pytest
```

## Development Conventions

### 1. Architectural Integrity
*   **Shared Blackboard**: Agents MUST NOT communicate directly. All delegation MUST happen via creating a Task on the Kanban board.
*   **Keeper First**: Use the Keeper for summarization and context injection to minimize latency and token costs on primary agent models.
*   **Rich Agent Identity**: All agents possess a unique name, description, and persona. This identity is stored in `isli-core` and automatically injected into the agent's context by the Keeper during every turn.
*   **Resilience Modules**: Leverage built-in `isli_core` modules for `circuit_breaker`, `bulkhead`, `retry`, and `checkpoint` to ensure system stability.

### 2. Implementation Guardrails
*   **Asynchronous Patterns**: Use `async`/`await` for all I/O bound operations. Core services rely on `asyncpg` and `aioredis`.
*   **External Channel Guarding**: `isli-core` MUST NOT forward replies to `isli-channels` for web-based sessions. Direct communication for web sessions is handled via WebSockets; forwarding unnecessary web replies to the gateway causes schema validation errors (422).
*   **Structured Logging**: Use `structlog` for all Python services to ensure logs are JSON-parseable and contain relevant context (e.g., `trace_id`).
*   **Distributed Tracing**: All requests should propagate a `trace_id` using OpenTelemetry.
*   **Real-time Observability**: Agent-specific logs are streamed in real-time via Redis Pub/Sub (channel: `agent:{agent_id}:logs`) and exposed via WebSockets in `isli-core` for the Board UI.

### 3. Security & Compliance
*   **PII Scrubbing**: All agent inputs/outputs should pass through the PII scrubber (documented in `Docs/08-failure-modes.md`).
*   **SSRF Protection**: Use the `ssrf.py` module in `isli_core` when implementing new skills that fetch external URLs.
*   **GDPR Compliance**: Refer to `gdpr.py` for erasure and storage limitation implementations.

### 4. Code Style
*   **Python**: Strict typing (`mypy`), `ruff` for linting.
*   **TypeScript**: Functional components with hooks, strict typing for all API payloads and WebSocket events.

## Useful Commands
*   `./scripts/run-local.sh`: Start services natively in separate panes (if available).
*   `./scripts/verify-enhancements.py`: Run a suite of integration tests for resilience features.
*   `docker compose -f docker-compose.scale-out.yml up`: Start in high-availability mode with Redis Sentinel.
