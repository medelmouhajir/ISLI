# 13 — Immersive Chat UI (Agent-Driven Components)

**Added:** 2026-05-29
**Updated:** 2026-05-30
**Status:** ✅ Complete (Phase 1 + Phase 2 — Read-only + Editable Form + 3 new display components)

---

## Overview

ISLI sessions now support **Agent-Driven UI State**. Agents can render typed React components (tables, cards, button groups, comparison tables) inline in the chat stream. User interactions with these components (clicking a table row, pressing a button) fire back as tool results into the same conversation context. The entire "app" lives inside one conversation — no frontend routing needed.

This transforms the chat from a passive text stream into a lightweight interactive application surface.

---

## Architecture

```
Agent turn
    ├── LLM decides to render a component
    │       └── calls ui_components(tool)
    │               └── Runner executes tool, stashes result in self._pending_components
    │                       └── Result injected as role:"tool" for LLM context
    ├── LLM produces final response (text + reference to component)
    │       └── Runner sends reply_to_session(text, components=self._pending_components)
    │               └── Core appends assistant message:
    │                       {"role": "assistant", "content": text, "timestamp": "...",
    │                        "components": [{component_type:"table", ...}]}
    │                       emits session:updated → WebSocket
    │                               ↓
    │                       Board reads msg.components per message, renders inline
    │                               ↓
    User clicks a row in the table
        └── Board POST /v1/sessions/{id}/action
                {action_id: "product_table_1",
                 action_type: "row_selected",
                 payload: {row_index: 2}}
                        ↓
                Core appends to messages:
                    {"role": "user", "type": "action", "action_id": "...",
                     "action_type": "row_selected", "payload": {...}, "timestamp": "..."}
                status = "pending_context"
                emits session:message → Agent WebSocket
                        ↓
                Agent receives action in next ReAct turn
                        ↓
                LLM reasons, calls ui_components again → DetailCard + ButtonGroup
```

---

## Core Changes

### Session Message Schema (Backward Compatible)

No Alembic migration required. The existing `messages` JSON column (list of dicts) is schemaless. Adding an optional `components` key to individual assistant message dicts preserves scrollback integrity:

```python
# Old assistant message (still works)
{"role": "assistant", "content": "Here are the products...", "timestamp": "..."}

# New assistant message with components
{"role": "assistant", "content": "Here are the products...", "timestamp": "...",
 "components": [
     {"component_type": "table", "props": {...}, "action_id": "products_001", "text_fallback": "..."}
 ]}
```

### Reply Endpoint (`POST /v1/sessions/{id}/reply`)

Accepts `text` + optional `components` list:

```python
class ComponentPayload(BaseModel):
    component_type: str           # "table", "card", "button_group", "comparison_table",
                                  # "form", "json_viewer", "status_timeline", "metric_grid"
    props: dict[str, Any]
    action_id: str | None = None
    text_fallback: str | None = None   # for Telegram/WhatsApp fallback
```

Components are stored **per-message**, not per-session. This means scrollback preserves every component — old assistant messages still show their tables when the user scrolls up.

### Action Endpoint (`POST /v1/sessions/{id}/action`)

User interactions from the Board create `role: "action"` messages:

```python
class SessionActionIn(BaseModel):
    action_id: str
    action_type: str          # "row_selected", "button_clicked"
    payload: dict[str, Any] = {}
```

Core appends to the session's `messages` list, sets `status = "pending_context"`, and emits `session:message` to the agent's WebSocket. An optional deduplication guard skips identical actions within a 1-second window.

### Channel Fallback

When forwarding replies to external channels (Telegram, WhatsApp), Core strips the `components` array and uses `text_fallback` if present. If no `text_fallback`, only the plain `text` is forwarded. External channel users never see raw JSON.

---

## Agent SDK

### Tool: `ui_components`

Registered in `SKILL_TOOL_REGISTRY` under the normalized key `ui_components` (skill name in Core: `ui-components`).

```python
def ui_components(
    component_type: str,        # "table", "card", "button_group", "comparison_table",
                               # "form", "json_viewer", "status_timeline", "metric_grid"
    props: dict[str, Any],
    action_id: str | None = None,
    text_fallback: str | None = None,
) -> dict[str, Any]:
    """Render a structured UI component inline in the chat stream."""
```

**8KB props cap** prevents token inflation. Large tables should paginate (max 50 rows recommended).

### Runner Integration

The runner intercepts `ui_components` at tool execution time (not by scanning final text). The result is stashed in `self._pending_components`. After the ReAct loop ends, the runner sends the stashed components alongside the final text reply via `reply_to_session(session_id, text, components=[...])`.

This is robust — no fragile string parsing of the LLM's final output.

### System Prompt Injection

When `"ui-components"` is in the agent's `config.skills`, the runner injects `UI_RENDERING_INSTRUCTIONS` into the system prompt. This tells the LLM:
- Which component types exist
- Their `props` schemas
- How interactions flow back as action messages
- Rules (always provide `action_id`, provide `text_fallback`, keep props under 8KB)

---

## Board UI

### Component Registry (`isli-board/src/components/ui/registry/`)

| Component | Key Props | Interaction |
|-----------|-----------|-------------|
| `DataTable` | `columns`, `rows` | `row_selected` on row click |
| `DetailCard` | `title`, `fields`, `buttons` | `button_clicked` on each button |
| `ButtonGroup` | `buttons` | `button_clicked` on each button |
| `ComparisonTable` | `headers`, `rows` | Read-only (no interaction) |
| `FormComponent` | `title`, `description`, `fields`, `submit_label` | `form_submitted` with `{values: {...}}` |
| `JsonViewer` | `title`, `data`, `collapsed` | Read-only (collapse/expand) |
| `StatusTimeline` | `steps` (label, status, detail) | Read-only (no interaction) |
| `MetricGrid` | `metrics` (label, value, trend, color) | Read-only (no interaction) |

Each interactive component receives:
- `payload` — the component dict from the message
- `sessionId` — for context
- `onAction(actionId, actionType, payload)` — callback that POSTs to `/v1/sessions/{id}/action`

### Action Indicator

When the user clicks a component, the Board appends an optimistic action indicator to the scrollback:

```
↳ row_selected on product_table_1
```

This gives immediate visual feedback while the agent thinks. The indicator is rendered as a `role: "action"` message with amber accent styling.

### Interaction Guard

Component interactions are disabled while `session.status !== 'ready'`. This prevents race conditions where the user clicks while the agent is already processing a prior turn.

### Audio Playback (Added 2026-06-01)

Assistant messages that include an `audio_url` (generated via TTS — see `Docs/07-channels.md`) render an inline `<audio controls preload="metadata">` player below the message bubble. This is independent of the component registry — any assistant message can carry both `components` and `audio_url` simultaneously.

- **Voice Mode:** When the user enables Voice Mode from the chat input toggle, every agent reply automatically includes a synthesized audio file.
- **Explicit voice messages:** Agents can proactively send voice via the `send_voice_message` SDK tool.
- **Source:** The player streams from `/api/v1/audio/{session_id}/{filename}` (Core proxies workspace download with session auth).

---

## Data Flow Example

### Turn 1: Agent renders a comparison table

**Agent calls:**
```python
ui_components(
    component_type="comparison_table",
    props={
        "headers": ["Feature", "Plan A", "Plan B"],
        "rows": [
            ["Price", "$10/mo", "$25/mo"],
            ["Storage", "10GB", "100GB"],
        ]
    },
    text_fallback="Plan A: $10/mo, 10GB. Plan B: $25/mo, 100GB.",
)
```

**Core stores:**
```json
{"role": "assistant", "content": "Here is the comparison:", "timestamp": "...",
 "components": [
   {"component_type": "comparison_table", "props": {"headers": [...], "rows": [...]}, "text_fallback": "..."}
 ]}
```

**Board renders:** A styled comparison table below the assistant message bubble.

### Turn 2: User clicks a button in a card

**Board sends:**
```json
POST /v1/sessions/{id}/action
{"action_id": "product_detail_1", "action_type": "schedule_demo", "payload": {"product_id": "widget_a"}}
```

**Core appends:**
```json
{"role": "user", "type": "action", "action_id": "product_detail_1",
 "action_type": "schedule_demo", "payload": {"product_id": "widget_a"}, "timestamp": "..."}
```

**Agent receives:** The action message in its next ReAct turn. The LLM sees: "User clicked 'Schedule Demo' on product_detail_1 for product widget_a." It can then call `ui_components` again to render a confirmation card or trigger a CRM workflow via another tool.

---

## Files Modified

### `isli-core/`
- `src/isli_core/routers/sessions.py` — `SessionReplyIn` (add `components`), `SessionActionIn`, action endpoint
- `src/isli_core/routers/skills.py` — register `ui-components` in `SKILL_REGISTRY` and `SKILL_METADATA`

### `isli-agent-sdk/`
- `src/isli_agent/tools/ui_renderer.py` — new `ui_components` tool + `UI_RENDERING_INSTRUCTIONS`
- `src/isli_agent/tools/__init__.py` — register in `SKILL_TOOL_REGISTRY`
- `src/isli_agent/runner.py` — stash pattern, system prompt injection
- `src/isli_agent/client.py` — `reply_to_session` accepts `components` param

### `isli-board/`
- `src/types/index.ts` — `ComponentPayload`, expanded `Message`
- `src/components/ui/registry/` — `UiComponentRegistry`, `DataTable`, `DetailCard`, `ButtonGroup`, `ComparisonTable`
- `src/components/SessionsPage.tsx` — render components per message, action indicator
- `src/components/ConversationsPage.tsx` — same
- `src/hooks/useSessionAction.ts` — mutation hook for action POST

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| LLM emits invalid component JSON | Runner validates with pydantic before sending; fallback to plain text |
| Board crashes on unknown component type | `UiComponentRenderer` defaults to `<pre>` code block |
| Telegram/WhatsApp sees raw JSON | Core strips components; uses `text_fallback` or plain `text` |
| Action spam from rapid clicking | Board disables while `status !== 'ready'`; Core dedup within 1s |
| Old sessions missing `components` key | Per-message access safely handles absence (`msg.components?.map`) |
| Token inflation from large props | 8KB cap in SDK; paginate table rows (max 50) |
| Agent confused by action messages | System prompt describes action message format explicitly |
| Scrollback loses components | Components stored per-message, not per-session |
| **Phase 2: Form field overflow** | Agent controls schema size; instructions warn about field count. Forms typically <6 fields. |
| **Phase 2: Invalid `field.type`** | FormComponent renders unknown types as plain `Input` with a console warning. Never crashes. |
| **Phase 2: JSON viewer circular refs** | Props are JSON-serialized by SDK before sending; circular refs impossible at this layer. |

---

## Phase 2: Editable Form Component + New Display Components (2026-05-30)

Phase 2 expanded the component registry with an **interactive Form** (stateful user input) and three **display-only** components for richer data presentation.

### Form Component (`form`)

**Registry key:** `form`
**Interaction:** `form_submitted` → payload `{values: Record<string, unknown>}`

**Props schema:**
```json
{
  "title": "Update Profile",
  "description": "Please confirm your details.",
  "fields": [
    {"name": "full_name", "label": "Full Name", "type": "text", "required": true, "default": "Alice"},
    {"name": "age", "label": "Age", "type": "number", "required": false},
    {"name": "plan", "label": "Plan", "type": "select", "options": ["Free", "Pro", "Enterprise"], "required": true, "default": "Pro"},
    {"name": "newsletter", "label": "Subscribe to newsletter", "type": "toggle", "default": true},
    {"name": "notes", "label": "Notes", "type": "textarea", "required": false}
  ],
  "submit_label": "Save Changes"
}
```

**Supported field types:** `text`, `number`, `select`, `toggle`, `textarea`.

**Board behavior:**
- Renders as a themed card with industrial border styling.
- Uses existing UI primitives (`Input`, `Textarea`, `Select`, `Toggle`, `Label`, `Button`).
- Controlled local state via React `useState`.
- Submit fires `form_submitted` action with the complete `values` object.
- Shows "✓ Form submitted" confirmation after submit.
- Disabled while `session.status !== 'ready'`.

### JsonViewer (`json_viewer`)

**Registry key:** `json_viewer`
**Interaction:** Read-only (collapse/expand)

**Props schema:**
```json
{
  "title": "API Response",
  "data": {"status": "ok", "items": [...]},
  "collapsed": false
}
```

- Recursive collapsible JSON tree renderer.
- Syntax-colored values: strings (`cyan`), numbers (`amber`), booleans (`green`), null (`red`).
- Monospace font with 2-space indent guides.
- Max-height scroll container for large payloads.

### StatusTimeline (`status_timeline`)

**Registry key:** `status_timeline`
**Interaction:** Read-only

**Props schema:**
```json
{
  "steps": [
    {"label": "Data ingestion", "status": "completed", "detail": "12,400 rows processed"},
    {"label": "Embedding", "status": "in_progress", "detail": "Batch 3/5"},
    {"label": "Index build", "status": "pending", "detail": "Waiting..."}
  ]
}
```

- Vertical timeline with step dots connected by a line.
- Status values: `completed` (green + check), `in_progress` (amber pulse + spinner), `pending` (grey + clock), `failed` (red + X).
- Mono uppercase labels with detail subtext.

### MetricGrid (`metric_grid`)

**Registry key:** `metric_grid`
**Interaction:** Read-only

**Props schema:**
```json
{
  "metrics": [
    {"label": "CPU", "value": "42%", "trend": "up", "color": "amber"},
    {"label": "Memory", "value": "1.2 GB", "trend": "down", "color": "cyan"},
    {"label": "Errors", "value": "0", "trend": "flat", "color": "green"}
  ]
}
```

- Responsive CSS grid (`2/3/4` columns).
- Metric mini-cards with label, value, and optional trend arrow.
- Color mapping to accent tokens: `cyan`, `amber`, `green`, `red`, `violet`.

### Phase 2 Files Modified

| File | Change |
|---|---|
| `isli-board/src/types/index.ts` | Expanded `ComponentPayload.component_type` union |
| `isli-board/src/components/ui/registry/UiComponentRegistry.tsx` | Registered 4 new components |
| `isli-board/src/components/ui/registry/FormComponent.tsx` | **New** — editable form with submit action |
| `isli-board/src/components/ui/registry/JsonViewer.tsx` | **New** — collapsible JSON tree |
| `isli-board/src/components/ui/registry/StatusTimeline.tsx` | **New** — step timeline |
| `isli-board/src/components/ui/registry/MetricGrid.tsx` | **New** — metric cards grid |
| `isli-agent-sdk/src/isli_agent/tools/ui_renderer.py` | Added to `COMPONENT_TYPES`; expanded `UI_RENDERING_INSTRUCTIONS` |

---

## Streaming Modes (Added 2026-05-31)

The immersive chat UI works alongside the new **streaming modes** system. When an agent is configured with `streaming_mode: "tools"`, `"trace"`, or `"debug"`, the Board receives `session:stream_event` WebSocket messages alongside the final `components` array:

| Streaming Mode | Complementary UI |
|----------------|-----------------|
| `text` | `StreamingMessageBubble` renders `token_delta` chunks with a blinking cursor |
| `tools` | `ToolCallBar` shows skill invocations above the text stream |
| `trace` | `ProcessTracePane` shows a collapsible timeline of the agent's turn |
| `debug` | Admin fetches prompt/response trace via REST; never broadcast over WS |

Components and streaming are **orthogonal** — an agent can emit both live `token_delta` events and a final `components` array in the same reply. The Board renders streaming events in real-time, then appends the structured components when the `session:updated` event arrives.

---

## See Also

- [`04-agents.md`](./04-agents.md) — Agent lifecycle, tool registration, and streaming modes
- [`06-skills.md`](./06-skills.md) — Skills system and registry
- [`07-channels.md`](./07-channels.md) — Session message flow
- [`10-roadmap.md`](./10-roadmap.md) — Implementation roadmap
