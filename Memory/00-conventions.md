# Project Logging & Memory Conventions

## Memory Folder
All session logs, memory snapshots, agent outputs, and intermediate work products must be saved as `.md` files inside this folder (`X:\Projects\ISLI_AI\Memory`).

Preferred sub-folders:
- `InProgress/` — Active tasks, ongoing work, partial outputs.
- `Completed/` — Finished work, final summaries, closed tasks.
- `Idle/` — Back-burner ideas, parked items, deferred work.

## Docs Folder
The `X:\Projects\ISLI_AI\Docs` directory contains the canonical project description files:

| File | Purpose |
|------|---------|
| `README.md` | Project overview and entry point |
| `01-architecture.md` | System architecture documentation |
| `02-keeper.md` | Keeper role / responsibilities |
| `03-memory.md` | Memory system design |
| `04-agents.md` | Agent definitions and behaviors |
| `05-kanban.md` | Kanban workflow rules |
| `06-skills.md` | Available skills catalog |
| `07-channels.md` | Communication channels |
| `08-failure-modes.md` | Failure mode analysis |
| `09-tech-stack.md` | Technology stack |

These files are the authoritative source of project intent and must be consulted before making structural changes.
