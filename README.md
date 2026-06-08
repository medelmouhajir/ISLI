# ISLI

Intelligent System for Local Intelligence — a modular multi-agent digital assistant.

## Project Structure

| Directory | Service | Port | Description |
|-----------|---------|------|-------------|
| `isli-core/` | Core API | 8000 | FastAPI — agent lifecycle & process management, task bus, skill proxy, cost control |
| `isli-keeper/` | Keeper | 8001 | Local Ollama sidecar (qwen3:1.7b) for memory & context |
| `isli-board/` | Kanban UI | 5173 | React + Vite real-time task board |
| `isli-skills/` | Skills Registry | 8100+ | Stateless HTTP skill microservices (incl. browser automation) |
| `isli-channels/` | Channel Gateway | 8200+ | Telegram, WhatsApp, Web, Email adapters |
| `infra/` | Infrastructure | — | Terraform, Traefik, Redis Sentinel, nginx |
| `scripts/` | Operations | — | Backup, chaos, load test, blue/green deploy |
| `Docs/` | Architecture docs | — | 12 markdown design documents |
| `Memory/` | Project memory | — | Research reports, conventions |

## Quick Start (Recommended)

The fastest way to install ISLI on a VPS or local machine is using the one-tap installer:

```bash
# Download and run the bootstrap script
curl -sSL https://raw.githubusercontent.com/medelmouhajir/ISLI/main/install.sh | bash
```

This will clone the repo, set up a management CLI, and guide you through an interactive setup wizard (secret generation, Ollama detection, and domain config).

### Manual Installation (Docker)

If you prefer to manage the stack manually:

```bash
git clone https://github.com/medelmouhajir/ISLI.git
cd ISLI
cp .env.example .env
# Edit .env with your secrets
docker compose up -d
```

## Management CLI

ISLI includes a unified `isli` CLI for operational tasks. It is installed automatically during the Quick Start.

```bash
# Check system health
./isli status

# Safely update to the latest version (with auto-backup)
./isli update

# Backup your database and workspaces
./isli backup
```

See [Docs/14 — Management CLI](./Docs/14-management-cli.md) for the full command reference.

### Prompt Configuration

All LLM prompts are centralized in `prompts.yaml` at the repo root. Edit prompts there and restart containers to apply changes — no rebuild required.

```bash
# Edit prompts.yaml, then restart affected services
docker compose restart keeper core agent-runner
```

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
- Phase 8 — Advanced Local Research (SearXNG Web Search)
- Phase 9 — Browser Automation (Beta) — Hermes-style accessibility-tree snapshots with `@ref` IDs, persistent Playwright sessions, form filling, and screenshot capture
- Phase 10 — Recurring Tasks & Full Scheduler — Standard 5-field cron support with transactional cloning, execution history, and "Upcoming" Kanban view
- Phase 11 — Skill Metadata Updates — `update-skill` endpoint and SDK tool for modifying existing skill metadata without review gate
- Phase 12 — Agent Identity Enhancements — Native support for agent avatars with specific upload endpoint, Redis blob storage (DB 10), and multi-view rendering (Grid, Panel, Detail)
