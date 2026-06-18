# ISLI AI — "The Council" Chat Paradigm

## Integration Plan

**Date:** 2026-06-17  
**Scope:** Add a Council Room experience to the existing ISLI stack (Core API, Agent SDK, React Board) while keeping all current Session/Kanban/Task flows intact.

---

## 1. Executive Summary

The Council is a new, additive conversation layer: a single room thread where the user can address one or more agents via `@mention` or the roster bar, and each addressed agent responds independently in parallel lanes. Agents share the visible thread as read-only context but never coordinate with each other. The user synthesises the outputs.

This plan proposes a **phased delivery** so the core paradigm can be shipped and validated before the more advanced Fork/Template/Pin-Board polish is added.

---

## 2. Recommended MVP Scope (Phase 1)

Ship first:

1. **Room model & CRUD** — create/list/open/close rooms, each seeded with at least one agent.
2. **Per-agent room sessions** — every `(Room, Agent)` pair gets its own `Session` row. Messages are mirrored into every session in the room so existing context-injection, journal, and memory workers keep working with minimal change.
3. **`@mention` parser + dynamic roster expansion** — mentioning `@donna` adds Donna to the room, creates her session, emits a join event, and dispatches the message to her.
4. **Sticky addressing state** — the UI remembers the last addressed agents; the user can clear it or toggle chips.
5. **Parallel dispatch** — one `context:requests` stream entry per addressed agent; each runs through the existing `ContextWorker` and `session:message` pipeline.
6. **Side-by-side response cards** — 1/2/3/4+ grid layouts with independent streaming.
7. **Roster bar + omni-input** — chips above the input, `@` live agent picker, addressing chips.
8. **Simple Pin Board** — pin any response, reorder, export to Markdown.
9. **Mobile responsive** — horizontal scroll with `◀ 2 of N ▶` indicator for 2+ cards.

**Deferred to Phase 2:** Fork sub-threads, room templates, `@all` broadcast polish, conflict indicators, multi-user sharing, room-level notifications, file attachments in council messages.

---

## 3. Architectural Decisions

| Decision | Rationale |
|---|---|
| **Add a new `Room` table; reuse `Session` rows for per-agent sessions** | Keeps the existing session-based context injection, journal, memory, and reply machinery intact. A direct 1:N room→sessions model matches the spec's "independent sessions per (Room, Agent)" rule. |
| **Mirror the canonical room thread into every session's `messages` JSON** | Existing `ContextWorker`, `JournalWorker`, `MemoryWorker`, and `reply_to_session` endpoint all operate on `Session.messages`. Mirroring avoids rewriting those workers. The `Room.messages` column remains the canonical source of truth for the UI. |
| **Web-only first** | The Council UI is a Board feature. Existing Telegram/WhatsApp flows keep using direct Sessions. |
| **Core is the source of truth for `@mention` expansion** | The UI sends `addressed_agent_ids` and the message text; Core validates, expands the roster, creates missing sessions, and dispatches. This prevents drift between UI state and persisted state. |
| **Clean-slate memory per room** | Because each room gets fresh per-agent sessions, agents do not inherit memories from other rooms by default. This satisfies the privacy-first default in the spec. |
| **Phased delivery** | The full spec is large. Shipping the core loop first lets us validate the UX before adding Fork, templates, etc. |

---

## 4. Data Model

### 4.1 New `Room` table

```text
id              String(36) PK   -- UUID
name            String(255)     -- editable by user
user_id         String(64)      -- owner
channel         String(32)      -- 'web' for now
status          String(32)      -- 'active' | 'closed'
messages        JSON            -- canonical thread (list of message dicts)
agent_ids       JSON            -- ordered roster list
pins            JSON            -- list of pinned message ids + preview
metadata        JSON            -- last_addressed_agent_ids, etc.
expires_at      DateTime TZ
last_activity_at DateTime TZ
created_at      DateTime TZ
deleted_at      DateTime TZ nullable
```

### 4.2 `Session` table additions

Add a nullable `room_id` FK column. All existing direct sessions keep `room_id = null`.

Room sessions reuse the existing `Session` columns:
- `agent_id` = the agent in this room
- `user_id` = room owner
- `channel` = `'web'`
- `messages` = mirrored copy of the room thread
- `status` = normal session lifecycle
- `context_summary`, `journal`, `session_metadata` = per-agent, isolated

### 4.3 Message shape (stored in `Room.messages` and mirrored)

```json
{
  "id": "msg-uuid",
  "role": "user" | "assistant" | "system",
  "content": "...",
  "agent_id": "harvey",
  "agent_name": "Harvey",
  "timestamp": "2026-06-17T...",
  "parent_id": "user-msg-uuid",
  "mentions": ["donna"],
  "attachments": []
}
```

`agent_id`/`agent_name` are set on assistant messages. `parent_id` links agent replies to the user message they respond to.

---

## 5. Backend Changes (Phase 1)

### 5.1 Models & migration

- `isli-core/src/isli_core/models.py`
  - Add `Room` model.
  - Add `room_id` nullable FK to `Session`.
- Run `alembic revision --autogenerate -m "add council rooms"`.

### 5.2 New mention parser utility

- `isli-core/src/isli_core/rooms/mentions.py`
  - `parse_mentions(text: str, agents: list[Agent]) -> list[str]`
  - Case-insensitive `@token` matching anywhere in text.
  - `@all` / `@everyone` resolved to current roster.

### 5.3 New `rooms` router

- `isli-core/src/isli_core/routers/rooms.py`
  - `GET    /v1/rooms` — list active rooms for user.
  - `POST   /v1/rooms` — create room with `agent_ids` and optional `name`.
  - `GET    /v1/rooms/{room_id}` — room detail.
  - `GET    /v1/rooms/{room_id}/history` — canonical thread.
  - `POST   /v1/rooms/{room_id}/message` — user message ingress.
    - Parse mentions, expand roster.
    - Append user message to `Room.messages` and mirror into every session in the room.
    - For each addressed agent, push `context:requests` with `session_id` = that agent's room session.
    - Store `last_addressed_agent_ids` in `Room.metadata`.
    - Emit `room:updated`.
  - `POST   /v1/rooms/{room_id}/agents` — manually add an agent.
    - Create session, append `● {name} joined` system message, emit `room:agent_joined`.
  - `POST   /v1/rooms/{room_id}/close` — close room and its sessions.
  - `POST   /v1/rooms/{room_id}/pin` / `DELETE /v1/rooms/{room_id}/pin/{message_id}` — Pin Board.
  - `POST   /v1/rooms/{room_id}/export-pins` — return Markdown string.

- `isli-core/src/isli_core/main.py` — include `rooms.router` under `/v1`.

### 5.4 Context injection worker

- `isli-core/src/isli_core/jobs/context_worker.py`
  - `_call_keeper()`: when `session.room_id` is present, load `Room` and pass `Room.messages` (not just `Session.messages`) to Keeper. This gives every agent the full council thread.
  - `_on_success()`: emit `session:message` with `room_id` included so the agent runner knows it is in council mode.

### 5.5 Session reply path

- `isli-core/src/isli_core/routers/sessions.py` — `reply_to_session()`
  - If `sess.room_id` is set:
    - Append assistant message to `Room.messages` with `agent_id`/`agent_name`.
    - Mirror that assistant message into **every** room session's `messages` so all agents see it in subsequent turns.
    - Emit `room:updated` (broadcast to Board) in addition to `session:updated`.
  - Keep all existing direct-session logic unchanged.

### 5.6 WebSocket events

- `isli-core/src/isli_core/event_manager.py` / `schemas.py`
  - Add schemas/events:
    - `room:updated` — room_id, message (optional), last_activity.
    - `room:agent_joined` — room_id, agent_id, agent_name, color.
- `isli-core/src/isli_core/routers/ws.py`
  - `room:*` events are broadcast to the Board only (already broadcast to all board connections).
  - `session:message` for a room session still routes to the agent's WebSocket via `target_agent_id`.

### 5.7 Session lifecycle

- `isli-core/src/isli_core/session_lifecycle.py`
  - `detect_idle()` and `expire_sessions()` should skip sessions whose `room_id` points to a room whose `last_activity_at` is still fresh, OR close room sessions together with the room.
  - Recommended: set `Room.expires_at` far in the future (e.g. 30 days) and propagate that to room sessions at creation. Then the existing `expires_at` logic naturally keeps them alive.

### 5.8 Journal / memory

No changes required in Phase 1 because each room session has its own mirrored `messages`, `journal`, and `last_memory_extracted_at`. Each agent extracts its own episodic memory independently.

---

## 6. Agent SDK Changes (Phase 1)

### 6.1 Council mode prompt block

- `isli-agent-sdk/prompts.yaml`
  - Add a `council_mode_block` instructing the agent:
    - "You are in a Council Room. You see messages from the user and from other specialists."
    - "Treat other agents' messages as read-only context."
    - "Respond only to the user's current request."
    - "Do not address, agree with, or reference other agents unless the user explicitly asks for comparison."

- `isli-agent-sdk/src/isli_agent/runner.py` — `_assemble_system_prompt()`
  - When `session_info` contains `room_id`, append the `council_mode_block` after the existing identity/context sections.
  - No other runner changes: it already receives `messages`, runs ReAct, and calls `reply_to_session()`.

### 6.2 Streaming

No SDK streaming changes required. The runner emits `session:stream_event` keyed by its room session id; the Board maps that id to the correct room/agent.

---

## 7. Board UI Changes (Phase 1)

### 7.1 Types & API hooks

- `isli-board/src/types/index.ts`
  - Add `Room`, `RoomMessage`, `RoomHistory`, `PinItem` interfaces.
- `isli-board/src/hooks/useRooms.ts` (new)
  - `useRooms()`, `useRoom(roomId)`, `useCreateRoom()`, `useSendRoomMessage()`, `useAddRoomAgent()`, `usePinMessage()`.

### 7.2 New components

- `isli-board/src/components/CouncilPage.tsx` — top-level route component.
- `isli-board/src/components/CouncilRoomList.tsx` — left sidebar room list.
- `isli-board/src/components/CouncilRoom.tsx` — main room container (header, roster, thread, input, pin board).
- `isli-board/src/components/CouncilRosterBar.tsx` — agent chips with status dots and `+ Add Agent`.
- `isli-board/src/components/CouncilThread.tsx` — render user message + grouped response cards.
- `isli-board/src/components/CouncilResponseCard.tsx` — agent card with streaming, Reply/Pin/Fork actions.
- `isli-board/src/components/CouncilInput.tsx` — omni-input with `@` mention dropdown and addressing chips.
- `isli-board/src/components/CouncilPinBoard.tsx` — right panel with pins + export.

### 7.3 Routing & navigation

- `isli-board/src/App.tsx`
  - Add `<Route path="/council" element={<CouncilPage />} />`.
  - Add WebSocket event handlers for `room:updated` and `room:agent_joined` to invalidate React Query caches (`['rooms']`, `['room', room_id]`).
  - Extend existing `session:stream_event` handling to support room streaming (the payload already contains `session_id` and `agent_id`).
- `isli-board/src/components/Sidebar.tsx`
  - Add "Council" nav item (e.g. between Sessions and Chats).

### 7.4 Reuse where possible

- Reuse `ChatInput.tsx` as the base for `CouncilInput.tsx`, adding `@mention` dropdown and addressing chip row.
- Reuse `StreamingMessageBubble.tsx` inside response cards.
- Reuse existing `useAgents()` to populate agent chips and picker.

---

## 8. Phase 2+ Roadmap

1. **Fork mechanic** — open a sub-thread scoped to one agent, indented UI, collapsible.
2. **Room templates** — Legal Review, Research Sprint, Full Council; configurable by workspace admin.
3. **`@all` broadcast** — UI expands to full roster, server enforces max agents cap (suggest 6 for readability).
4. **Conflict indicator** — optional LLM/lightweight heuristic to flag contradictory assistant replies.
5. **File attachments / voice in council messages** — port existing session attachment logic to room ingress.
6. **Multi-user rooms** — share a room read-only or collaboratively.
7. **Agent memory across rooms** — opt-in per agent/room to share episodic memory.

---

## 9. Testing & Verification

### Backend
- Unit tests for `parse_mentions()` (case-insensitive, unknown tokens as plain text, `@all`).
- API tests for room CRUD, message dispatch, roster expansion, and reply mirroring.
- Verify that direct `Session` endpoints still pass existing tests unchanged.
- Run `ruff`, `mypy`, `pytest` in `isli-core`.

### Frontend
- `npm run typecheck` and `npm run build` in `isli-board`.
- Manual E2E flow:
  1. Create room with Harvey.
  2. Send message → Harvey replies.
  3. Type "@donna can you review?" → Donna joins and replies in parallel.
  4. Pin Harvey's response; export pins.

### Docker
- Rebuild `isli-core`, `isli-board`, and `agent-runner` images from source.
- Run `docker compose up --build` and `alembic upgrade head` in the core container.
- Confirm existing sessions/chats still work.

---

## 10. Open Questions / Assumptions

1. **MVP scope** — Plan assumes Phase 1 is the core loop (rooms, roster, parallel dispatch, cards, pin board). Confirm if this is the right first slice, or if Fork/Templates are required in the first pass.
2. **Max agents per room** — Recommend a UI cap of **6** agents for legibility. Confirm or override.
3. **Mobile layout** — Recommend horizontal scroll with counter for 2+ cards; single-card full width on desktop for 1 agent.
4. **Channel scope** — Council is web-only in Phase 1. Confirm whether Telegram/WhatsApp should also support room threads in Phase 1 (not recommended due to UI constraints).
5. **Memory default** — Clean slate per room. Confirm this matches the product intent.
6. **Conflict detection** — Deferred to Phase 2; UI leaves synthesis entirely to the user in Phase 1.

---

## 11. Files Likely to Change (Phase 1)

```text
isli-core/
  src/isli_core/models.py
  src/isli_core/main.py
  src/isli_core/schemas.py
  src/isli_core/event_manager.py
  src/isli_core/session_lifecycle.py
  src/isli_core/routers/sessions.py
  src/isli_core/routers/ws.py
  src/isli_core/jobs/context_worker.py
  src/isli_core/rooms/
    __init__.py
    mentions.py
    service.py
  src/isli_core/routers/rooms.py
  alembic/versions/...
  tests/...

isli-agent-sdk/
  prompts.yaml
  src/isli_agent/runner.py

isli-board/
  src/types/index.ts
  src/lib/api.ts (minor)
  src/hooks/useRooms.ts (new)
  src/components/
    Sidebar.tsx
    App.tsx
    CouncilPage.tsx (new)
    CouncilRoomList.tsx (new)
    CouncilRoom.tsx (new)
    CouncilRosterBar.tsx (new)
    CouncilThread.tsx (new)
    CouncilResponseCard.tsx (new)
    CouncilInput.tsx (new)
    CouncilPinBoard.tsx (new)
```

---

## 12. Deployment Notes

- Rebuild Docker images from source; do **not** use `docker cp` (per project memory).
- Apply Alembic migration before starting Core.
- No new environment variables are needed for Phase 1.
- The Board `dist/` is baked into its Docker image; rebuild with `--no-cache` after UI changes (per project memory).
