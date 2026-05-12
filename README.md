# ISLI

Intelligent System for Local Intelligence — a modular multi-agent digital assistant.

## Project Structure

| Directory | Service | Port | Description |
|-----------|---------|------|-------------|
| `isli-core/` | Core API | 8000 | FastAPI — agent lifecycle, task bus, skill proxy, cost control |
| `isli-keeper/` | Keeper | 8001 | Local Ollama sidecar for memory & context; cloud fallback |
| `isli-board/` | Kanban UI | 5173 | React + Vite real-time task board |
| `isli-skills/` | Skills Registry | 8100+ | Stateless HTTP skill microservices |
| `isli-channels/` | Channel Gateway | 8200+ | Telegram, WhatsApp, Web, Email adapters |
| `infra/` | Infrastructure | — | Terraform, Traefik, Redis Sentinel, nginx |
| `scripts/` | Operations | — | Backup, chaos, load test, blue/green deploy |
| `Docs/` | Architecture docs | — | 12 markdown design documents |
| `Memory/` | Project memory | — | Research reports, conventions |

## Quick Start (Docker)

```bash
# Clone and enter
cd /x/Projects/ISLI_AI

# Set environment
cp .env.docker .env

# Start the full stack
docker compose up --build

# Or scale-out mode
docker compose -f docker-compose.scale-out.yml up --build
```

Services will be available at:
- Core API: http://localhost:8000
- Keeper: http://localhost:8001
- Board: http://localhost:5173
- Jaeger (tracing): http://localhost:16686

## Run Tests

```bash
cd isli-core
pip install -e ".[dev]"
pytest
```

## Documentation

See `Docs/README.md` for the full architecture documentation.

## Implementation Status

All 7 implementation phases are complete:
- Phase 0 — Foundation
- Phase 1 — Safety & Governance
- Phase 2 — Resilience & Recovery
- Phase 3 — Channels & Delivery Guarantees
- Phase 4 — Memory & Data Integrity
- Phase 5 — Cost Optimization & Model Tiering
- Phase 6 — Compliance & Audit Hardening
- Phase 7 — Scale-Out & Production Topology
