# 17 — Council Chat (Multi-Agent Rooms)

**Added:** 2026-06-17
**Updated:** 2026-06-17
**Status:** ✅ Complete (Phase 1 — Web-only, parallel agent lanes)

---

## Overview

**The Council** is a multi-agent chat paradigm in ISLI. A user enters a single room thread and can address one or more agents via `@mention` or the roster bar. Each addressed agent responds in its own parallel lane with an independent per-agent session. All agents share the canonical room thread as read-only context, but they do **not** coordinate with each other. This keeps ISLI's design principle intact: there is no orchestrator model.

Council rooms are useful when a user wants simultaneous input from multiple specialists — for example, a legal researcher, a marketing strategist, and a code reviewer answering the same brief in side-by-side cards.

### Key properties

- One canonical thread stored in the `Room` table.
- Every agent in the room has a deterministic `Session` row: `room:{room_id}:{agent_id}`.
- The canonical `Room.messages` list is mirrored into every room session, so existing context-injection, journal, and memory workers operate unchanged.
- Addressing is resolved by mentions (`@agent_id`, `@all`, `@everyone`) and sticky last-addressed state from the UI.
- Agents only respond to the user; other agents' replies are read-only context.
- Phase 1 is **web-only** and supports up to **6 agents per room**.

---

## Architecture

```
Board UI — Council page
    │
    ▼
POST /v1/rooms/{room_id}/message
    │
    ▼
RoomService
    ├── parse mentions (@agent_id, @all, @everyone)
    ├── ensure addressed agents are in room roster
    ├── append user message to Room.messages
    ├── mirror Room.messages into every room Session
    └── push context:requests to Redis Stream — one per addressed agent
              │
              ▼
    ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
    │ Agent A lane    │     │ Agent B lane    │     │ Agent C lane    │
    │ room:r:{id}:A   │     │ room:r:{id}:B   │     │ room:r:{id}:C   │
    │ (its own model, │     │ (its own model, │     │ (its own model, │
    │  own session)   │     │  own session)   │     │  own session)   │
    └────────┬────────┘     └────────┬────────┘     └────────┬────────┘
             │                        │                        │
             ▼                        ▼                        ▼
    reply_to_session(text)    reply_to_session(text)    reply_to_session(text)
             │                        │                        │
             └────────────┬───────────┴────────────────────────┘
                          ▼
              Core outbox — handle_session_persist
                    ├── append assistant reply to Room.messages
                    ├── tag parent_id to the user message for UI grouping
                    ├── mirror reply into every room Session
                    └── emit room:updated WebSocket event
                          │
                          ▼
              Board re-renders all lanes in real time
```

### Why mirror the thread into per-agent sessions?

ISLI's existing agent runtime, context-injection pipeline, journal worker, and memory worker are built around the `Session` model. Rather than reimplement those systems for rooms, a Council room is a thin layer on top:

- The `Room` owns the authoritative message list.
- Each agent's deterministic `Session` row is just a read/write projection of that list plus agent-specific metadata.
- When an agent replies, Core's existing `reply_to_session` path triggers `handle_session_persist`, which appends the reply to the room and mirrors it back into all room sessions.

This lets agents use their existing tools, skills, memory, and model routing without knowing they are in a room.

---

## Data Model

### `Room` table

| Column | Purpose |
|--------|---------|
| `id` | UUID primary key |
| `name` | Human-readable room name |
| `user_id` | Board user who owns the room |
| `channel` | Channel constant; Phase 1 is always `web` |
| `status` | `active` or `closed` |
| `messages` | Canonical JSON message list |
| `agent_ids` | Roster of agent IDs (max 6) |
| `pins` | Pinned message metadata |
| `room_metadata` | Operational metadata, including `last_addressed_agent_ids` |
| `expires_at` | Auto-cleanup date (30 days) |
| `last_activity_at` | For sorting and idle decisions |

### `Session.room_id`

The existing `sessions` table has a nullable foreign key `room_id` referencing `rooms.id`. Sessions where `room_id IS NOT NULL` are excluded from the session idle detector; their lifecycle is tied to the room.

### Deterministic session IDs

```
room:{room_id}:{agent_id}
```

This makes it trivial to route a context-injection request to the correct agent lane and to inspect a room's per-agent state from the database.

---

## Mention Resolution

The mention parser extracts `@token` from the user message and resolves them to agent IDs:

| Input | Resolves to |
|-------|-------------|
| `@researcher` | Agent whose `id` or first name matches `researcher` (case-insensitive) |
| `@all` | Every agent currently in the room roster |
| `@everyone` | Same as `@all` |

Resolution order:

1. If the UI sends an explicit `addressed_agent_ids` list, start there.
2. Otherwise fall back to the sticky `last_addressed_agent_ids` stored in `room_metadata`.
3. Expand any `@mentions` inside the message text.
4. If no agent is addressed after parsing, fall back to the entire room roster.

Agents referenced by mention but not yet in the room are added automatically (subject to the 6-agent cap).

---

## Agent Behavior in Council Mode

When the agent SDK receives a `session:message` event whose payload contains `room_id`, it:

1. Injects the `agent.council_mode_block` prompt block from `prompts.yaml` into the system prompt.
2. The block instructs the agent:
   - This is a Council room; the user may have addressed multiple agents.
   - Messages from other agents are read-only context.
   - Respond only to the user, not to other agents.
   - Do not attempt to delegate or coordinate with other agents.

Each agent's response is therefore independent and addressed to the user, while still benefiting from seeing peer responses in the shared thread.

---

## Core API Endpoints

All endpoints are under `/v1/rooms` and scoped by `user_id` from the Board session token.

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/v1/rooms?user_id={uid}` | List active rooms |
| `POST` | `/v1/rooms` | Create a room with an initial roster |
| `GET` | `/v1/rooms/{id}` | Fetch room state |
| `GET` | `/v1/rooms/{id}/history` | Fetch full message history |
| `POST` | `/v1/rooms/{id}/message` | Post a user message; triggers parallel agent turns |
| `POST` | `/v1/rooms/{id}/agents` | Add an agent to the room |
| `POST` | `/v1/rooms/{id}/close` | Close the room and all room sessions |
| `POST` | `/v1/rooms/{id}/pin` | Pin a message |
| `DELETE` | `/v1/rooms/{id}/pin/{message_id}` | Unpin a message |
| `POST` | `/v1/rooms/{id}/export-pins` | Export pinned messages as Markdown |

WebSocket events emitted:

- `room:updated` — the room thread changed; Board re-fetches room history.
- `room:agent_joined` — a new agent was added to the room.

---

## Board UI

The Council page is reachable from the sidebar (`/council`). It consists of:

- **Room list** — active rooms with last activity.
- **Roster bar** — click an agent pill to address it explicitly; `@all` addresses everyone.
- **Thread** — canonical user messages and system events.
- **Response cards** — side-by-side lanes, one per agent, showing each agent's reply grouped by the parent user message.
- **Pin board** — user can pin any message; pins are persisted in `Room.pins`.
- **Export** — `Export Pins` downloads pinned messages as Markdown.

---

## Limits & Phase 1 Scope

| Limit | Value | Notes |
|-------|-------|-------|
| Max agents per room | 6 | Hard cap to control cost and context size |
| Channels | web only | Telegram/WhatsApp/Email are planned for Phase 2 |
| Memory | clean slate per room | Room sessions do not reuse normal session memory; each room has its own context |
| Lifecycle | 30 days | `expires_at` default; closing a room closes all room sessions |

### What's planned but not in Phase 1

- Cross-room memory or agent recollection of past rooms.
- Agent-to-agent replies (agents currently respond only to the user).
- Non-web channels.
- Automated room creation from slash commands.

---

## Files Modified

### `isli-core/`
- `src/isli_core/models.py` — `Room` model; `Session.room_id` foreign key.
- `alembic/versions/20260617_a1b2c3d4e5f6_add_council_rooms.py` — idempotent migration.
- `src/isli_core/rooms/mentions.py` — mention parser.
- `src/isli_core/rooms/service.py` — `RoomService`, `mirror_room_reply`.
- `src/isli_core/routers/rooms.py` — `/v1/rooms` endpoints.
- `src/isli_core/main.py` — register rooms router.
- `src/isli_core/startup/outbox.py` — mirror room replies to room and sessions.
- `src/isli_core/jobs/context_worker.py` — forward `room_id` in `session:message` event.
- `src/isli_core/session_lifecycle.py` — exclude room sessions from idle detection.
- `src/isli_core/schemas.py` — `room:updated`, `room:agent_joined` schemas.
- `src/isli_core/routers/sessions.py` — `room_id` in `SessionOut`.
- `tests/test_council_rooms.py` — 18 new tests.

### `isli-agent-sdk/`
- `prompts.yaml` — `agent.council_mode_block`.
- `src/isli_agent/runner/prompt_assembler.py` — inject council block when `room_id` is present; pass `room_id` into `session_info`.

### `isli-board/`
- `src/types/index.ts` — `Room`, `RoomMessage`, `PinItem`, `RoomHistory`.
- `src/hooks/useRooms.ts` — TanStack Query hooks.
- `src/contexts/BoardSocketContext.tsx` — `room:updated` / `room:agent_joined` union cases.
- `src/App.tsx` — `/council` route and WebSocket invalidation.
- `src/components/Sidebar.tsx` — Council nav item.
- `src/components/CouncilPage.tsx` and related components — full UI.

---

## See Also

- [`04-agents.md`](./04-agents.md) — Agent lifecycle and prompt injection.
- [`07-channels.md`](./07-channels.md) — Channel gateway flow.
- [`13-immersive-chat-ui.md`](./13-immersive-chat-ui.md) — Inline agent-driven components.
- [`10-roadmap.md`](./10-roadmap.md) — Council Chat Phase 1 milestone.
