# Plan: Bidirectional WebSocket Streaming for ISLI

## Executive Summary

Implement five streaming visibility modes (0–D) using **Approach 1: bidirectional WebSocket**.
The agent emits structured events over its existing authenticated WebSocket to Core. Core fans
them out to the Board UI via the shared `/ws/board` connection. No new ports, no new
auth model — we reuse the current Agent→Core→Board event pipeline.

**Key architectural decision:** For Mode A (live text) we implement **server-side chunked
text reveal**, not raw `stream=True` LLM streaming. True LLM streaming is incompatible with
ReAct (we only know a turn is "final" after it completes). The chunked reveal splits the
final answer into ~5-char chunks and emits them over WS with 20 ms delays. To the user it
is visually identical to token streaming, but it is 100× simpler and works with every
provider (Ollama, Gemini, OpenAI, etc.). True `stream=True` can be added later as a
Phase-2 optimization for single-turn sessions.

---

## 1. Protocol Design

### 1.1 Event Envelope (Agent → Core)

```json
{
  "type": "agent:stream_event",
  "payload": {
    "session_id": "sess-uuid",
    "event_type": "token_delta",
    "data": { "delta": "Hello " },
    "timestamp": "2026-05-31T12:00:00Z"
  }
}
```

Single envelope type (`agent:stream_event`) so Core validates auth once and routes.
The inner `event_type` controls visibility per mode.

### 1.2 Event Taxonomy

| `event_type` | Mode visibility | Description |
|--------------|-----------------|-------------|
| `phase_start` | C, D | `{phase: "context_inject|llm_call|tool_call|memory_op|checkpoint"}` |
| `phase_end` | C, D | `{phase, duration_ms}` |
| `turn_start` | C, D | `{turn_number, model, estimated_tokens}` |
| `turn_end` | C, D | `{turn_number, usage, duration_ms}` |
| `tool_call` | **A**, B, C, D | `{tool, args, status: "started|done", result_summary, duration_ms}` |
| `token_delta` | A, B, C, D | `{delta: "..."}` — chunked reveal of final text |
| `draft_complete` | A, B, C, D | `{}` — signals all deltas sent, final message follows |
| `cost_report` | C, D | `{input_tokens, output_tokens, reasoning_tokens, cost_usd}` |
| `debug_prompt` | D | Stored in Redis only; **not broadcast over WS** (see §4.4) |
| `debug_response` | D | Stored in Redis only; **not broadcast over WS** |
| `error` | A, B, C, D | `{error, recoverable}` |

**Rationale for `tool_call` in Mode A:** The dead wait before the final answer is the biggest UX problem. Even in "text" mode, emitting `tool_call` events costs nothing (no LLM streaming needed) and turns 8 seconds of silence into visible activity. The Board UI shows a compact skill indicator while the ReAct loop runs, then streams the final text. |

### 1.3 Configurable Chunk Parameters

The agent's `config` blob carries streaming tunables alongside `streaming_mode`:

```json
{
  "streaming_mode": "text",
  "stream_chunk_size": 5,
  "stream_delay_ms": 20
}
```

| Parameter | Default | Use case |
|-----------|---------|----------|
| `stream_chunk_size` | 5 | Short replies → 3; long reports → 20 |
| `stream_delay_ms` | 20 | Fast feel → 10; slower provider → 30 |

The runner reads these per-session from `self.config.config`. Invalid or missing values fall back to defaults. |

### 1.3 Core → Board Fan-out

Core transforms `agent:stream_event` into `session:stream_event`:

```json
{
  "type": "session:stream_event",
  "payload": {
    "session_id": "sess-uuid",
    "agent_id": "agent-id",
    "event_type": "token_delta",
    "data": { "delta": "Hello " },
    "timestamp": "2026-05-31T12:00:00Z"
  }
}
```

### 1.4 Draft Persistence

Core accumulates `token_delta` events in Redis:
- Key: `session:{session_id}:draft`
- Type: string (simple append)
- TTL: 300 seconds
- Deleted on `session:updated` (final reply persisted)

This allows a Board client that reconnects mid-stream to fetch the partial draft via REST.

---

## 2. Data Model Changes

### 2.1 Agent Config (No Migration)

`streaming_mode`, `stream_chunk_size`, and `stream_delay_ms` live inside the existing `agents.config` JSON blob:

```python
config = {
    "streaming_mode": "silent",      # "silent" | "text" | "tools" | "trace" | "debug"
    "stream_chunk_size": 5,
    "stream_delay_ms": 20,
}
```

Rationale: avoids migration, fits the existing `AgentConfigOut` / `AgentUpdate` schemas,
and the Board already edits `config` via a JSON field and per-field form bindings.

Validation in `AgentCreate` / `AgentUpdate`:
```python
_valid_streaming_modes = {"silent", "text", "tools", "trace", "debug"}
```
Coerce invalid values to `"silent"`; coerce negative/missing chunk/delay to defaults.

### 2.2 Session Metadata (Small Migration)

Add a nullable `metadata` JSON column to the `sessions` table for per-session overrides:

```python
class Session(Base):
    ...
    metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=dict)
```

Per-session override resolution order:
1. `session.metadata.get("streaming_mode")` — if set, wins
2. `agent.config.get("streaming_mode")` — fallback
3. `"silent"` — ultimate fallback

This allows debugging a single conversation without affecting the agent globally.
Alembic migration: one column addition, no data backfill needed.

---

## 3. Agent SDK Changes (`isli-agent-sdk`)

### 3.1 `runner.py`

#### New state
```python
self._websocket: websockets.WebSocketClientProtocol | None = None
self._outgoing_queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
```

#### `_ws_loop` modifications
- Store `self._websocket = websocket` on connect.
- Spawn `asyncio.create_task(self._drain_outgoing_queue())`.
- Clear `self._websocket = None` on disconnect.

#### `_drain_outgoing_queue`
```python
async def _drain_outgoing_queue(self):
    """Drain the outgoing queue to the active WebSocket.
    On reconnect, the queue may contain hundreds of backlogged events.
    We rate-limit the burst to avoid flooding Core."""
    while self._running:
        try:
            event = await asyncio.wait_for(self._outgoing_queue.get(), timeout=1.0)
            if self._websocket and self._websocket.open:
                await self._websocket.send(json.dumps(event))
                # Rate-limit reconnect bursts: small yield between sends
                await asyncio.sleep(0.001)
        except asyncio.TimeoutError:
            continue
```

**Reconnect semantics clarified:**
- The outgoing queue buffers events that were generated **while connected** but not yet sent (backpressure).
- If the WS drops, events in the queue are **lost**. This is acceptable — the Redis draft (`session:{id}:draft`) is the source of truth for text.
- On reconnect, Core already has the accumulated draft in Redis. The Board catches up via `GET /draft` or by receiving new deltas.
- **Process trace events are intentionally ephemeral.** They are not replayed. If the Board missed them, they are gone. This is correct — trace history is best-effort, not guaranteed delivery.
- The 1000-event cap prevents unbounded memory growth during long ReAct loops in trace/debug mode.

#### `_emit_stream_event` (with graceful degradation)

```python
async def _emit_stream_event(self, session_id: str, event_type: str, data: dict):
    """Emit a streaming event. NEVER raise — streaming is best-effort."""
    try:
        # Resolve streaming mode: session override > agent config > silent
        mode = "silent"
        if self._current_session_metadata and "streaming_mode" in self._current_session_metadata:
            mode = self._current_session_metadata["streaming_mode"]
        elif self.config.config:
            mode = self.config.config.get("streaming_mode", "silent")

        if mode == "silent":
            return
        if mode == "text" and event_type not in ("token_delta", "draft_complete", "tool_call", "error"):
            return
        if mode == "tools" and event_type not in ("token_delta", "draft_complete", "tool_call", "error"):
            return
        if mode == "trace" and event_type in ("debug_prompt", "debug_response"):
            return
        # debug mode allows everything

        event = {
            "type": "agent:stream_event",
            "payload": {
                "session_id": session_id,
                "event_type": event_type,
                "data": data,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        }
        try:
            self._outgoing_queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning("runner.stream_queue_full", session_id=session_id, event_type=event_type)
    except Exception as e:
        logger.warning("runner.emit_stream_event_failed", session_id=session_id, event_type=event_type, error=str(e))
```

**Critical rule:** `_emit_stream_event` is wrapped in a broad `try/except`. A streaming failure must **never** propagate and kill the agent response. Mode 0 (silent) is the implicit fallback.

#### `_stream_text`
```python
async def _stream_text(self, session_id: str, text: str):
    """Emit token_delta events by splitting text into configurable chunks.
    Chunk size and delay are read from agent config per session."""
    cfg = self.config.config or {}
    chunk_size = cfg.get("stream_chunk_size", 5)
    delay_ms = cfg.get("stream_delay_ms", 20)
    if chunk_size < 1:
        chunk_size = 5
    if delay_ms < 0:
        delay_ms = 20

    for i in range(0, len(text), chunk_size):
        chunk = text[i:i + chunk_size]
        await self._emit_stream_event(session_id, "token_delta", {"delta": chunk})
        await asyncio.sleep(delay_ms / 1000)
    await self._emit_stream_event(session_id, "draft_complete", {})
```

#### `_execute_session_message` modifications

Insert emission hooks:

1. **After context injection:**
   ```python
   await self._emit_stream_event(session_id, "phase_start", {"phase": "context_inject"})
   # ... existing context code ...
   await self._emit_stream_event(session_id, "phase_end", {"phase": "context_inject", "duration_ms": ...})
   ```

2. **At turn start:**
   ```python
   await self._emit_stream_event(session_id, "turn_start", {"turn_number": turn_number, "model": ...})
   ```

3. **At tool execution:**
   ```python
   await self._emit_stream_event(session_id, "tool_call", {"tool": tool_name, "args": tool_args, "status": "started"})
   result = await self._execute_tool(tool_name, tool_args)
   await self._emit_stream_event(session_id, "tool_call", {"tool": tool_name, "status": "done", "result_summary": result[:200], "duration_ms": ...})
   ```

4. **At final answer (Mode A+):**
   ```python
   if not tool_calls:
       clean_content = self._strip_tool_calls(message.content or "")
       # Stream the final text
       await self._stream_text(session_id, clean_content)
       # Then send the formal reply
       await self.client.reply_to_session(session_id, clean_content, components=components)
       break
   ```

5. **At turn end:**
   ```python
   await self._emit_stream_event(session_id, "turn_end", {"turn_number": turn_number, "usage": ...})
   ```

6. **At checkpoint (Mode C+):**
   ```python
   await self._emit_stream_event(session_id, "phase_start", {"phase": "checkpoint"})
   await self.client.save_checkpoint(...)
   await self._emit_stream_event(session_id, "phase_end", {"phase": "checkpoint", "duration_ms": ...})
   ```

7. **At cost report (Mode C+):**
   After `report_usage`, emit `cost_report` event.

8. **At debug (Mode D):**
   Before LLM call, emit `debug_prompt` with truncated prompt.
   After LLM call, emit `debug_response` with truncated response.

### 3.2 `client.py`

No new REST endpoints needed for streaming — events go over WS.
Add `send_typing_indicator` helper? No, keep channels untouched for Phase 1.

---

## 4. Core Changes (`isli-core`)

### 4.1 `ws.py` — Bidirectional Agent WebSocket

Modify `agent_ws()` to parse incoming messages:

```python
@router.websocket("/agents/{agent_id}")
async def agent_ws(...):
    ...
    try:
        while True:
            data = await websocket.receive_text()
            try:
                event = json.loads(data)
                if event.get("type") == "agent:stream_event":
                    payload = event.get("payload", {})
                    session_id = payload.get("session_id")
                    event_type = payload.get("event_type")
                    event_data = payload.get("data", {})

                    # Append token_delta to Redis draft
                    if event_type == "token_delta" and session_id:
                        delta = event_data.get("delta", "")
                        if delta:
                            redis = await get_redis()
                            await redis.append(f"session:{session_id}:draft", delta)
                            await redis.expire(f"session:{session_id}:draft", 300)

                    # Store debug events in Redis (never broadcast over WS)
                    if event_type in ("debug_prompt", "debug_response") and session_id:
                        redis = await get_redis()
                        trace_key = f"session:{session_id}:debug_trace"
                        await redis.lpush(trace_key, json.dumps({
                            "event_type": event_type,
                            "data": event_data,
                            "timestamp": payload.get("timestamp"),
                        }))
                        await redis.ltrim(trace_key, 0, 99)
                        await redis.expire(trace_key, 300)
                        continue  # skip broadcast

                    # Fan out to board
                    await manager.broadcast_to_board(json.dumps({
                        "type": "session:stream_event",
                        "payload": {
                            "session_id": session_id,
                            "agent_id": agent_id,
                            "event_type": event_type,
                            "data": event_data,
                            "timestamp": payload.get("timestamp"),
                        }
                    }))
            except Exception as exc:
                logger.warning("ws.agent_message_parse_failed", agent_id=agent_id, error=str(exc))
    except WebSocketDisconnect:
        ...
```

### 4.2 `sessions.py` — Draft and Debug Trace Endpoints

Add draft retrieval:

```python
@router.get("/{session_id}/draft")
async def get_session_draft(session_id: str):
    redis = await get_redis()
    draft = await redis.get(f"session:{session_id}:draft")
    return {"session_id": session_id, "draft": draft or ""}
```

Add protected debug trace retrieval (admin only):

```python
@router.get("/{session_id}/debug-trace")
async def get_session_debug_trace(
    session_id: str,
    _admin: str = Depends(require_admin_auth),
):
    redis = await get_redis()
    trace_key = f"session:{session_id}:debug_trace"
    raw = await redis.lrange(trace_key, 0, -1)
    events = [json.loads(r) for r in raw]
    return {"session_id": session_id, "events": list(reversed(events))}
```

Also clear both `draft` and `debug_trace` keys in `reply_to_session` after emitting `session:updated`.

### 4.3 `routers/agents.py` — Validation

In `AgentCreate` and `AgentUpdate`, add field-level normalization:

```python
@field_validator("config")
@classmethod
def _normalize_streaming_mode(cls, v: dict | None) -> dict:
    if v is None:
        return {"streaming_mode": "silent"}
    valid = {"silent", "text", "tools", "trace", "debug"}
    mode = v.get("streaming_mode", "silent")
    if mode not in valid:
        v["streaming_mode"] = "silent"
    return v
```

Add `streaming_mode` to `AgentOut` for convenience (computed from config):

```python
class AgentOut(BaseModel):
    ...
    streaming_mode: str = "silent"

    @classmethod
    def from_agent(cls, agent: Agent) -> "AgentOut":
        base = cls.model_validate(agent)
        base.config = _safe_json(agent.config, {})
        base.streaming_mode = base.config.get("streaming_mode", "silent")
        return base
```

---

## 5. Board UI Changes (`isli-board`)

### 5.1 `types/index.ts`

Add `StreamingEvent` type and extend `BoardMessage`:

```typescript
export interface StreamingEvent {
  event_type: string
  data: Record<string, unknown>
  timestamp: string
}

export type BoardMessage =
  | ...existing...
  | { type: 'session:stream_event'; payload: { session_id: string; agent_id: string; event_type: string; data: Record<string, unknown>; timestamp: string } }
```

### 5.2 `contexts/BoardSocketContext.tsx`

Add `session:stream_event` to the union.

### 5.3 `App.tsx`

In the `lastMessage` effect, add:

```typescript
case 'session:stream_event': {
  // Handled by page-level hooks; we just ensure the session list
  // shows the latest activity timestamp without refetching.
  const { session_id } = lastMessage.payload
  queryClient.setQueryData(['chat-sessions'], (old: Session[] | undefined) =>
    old?.map((s) =>
      s.id === session_id
        ? { ...s, last_activity_at: new Date().toISOString() }
        : s
    ) ?? old
  )
  break
}
```

### 5.4 `ConversationsPage.tsx`

#### State additions
```typescript
const [drafts, setDrafts] = useState<Record<string, string>>({})
const [toolCalls, setToolCalls] = useState<Record<string, ToolCallEvent[]>>({})
const [processTraces, setProcessTraces] = useState<Record<string, ProcessTraceEvent[]>>({})
```

#### New hook: `useSessionStream`
```typescript
// In a new file hooks/useSessionStream.ts
export function useSessionStream() {
  const { lastMessage } = useBoardSocket()
  // Returns the latest stream event for consumption by pages
}
```

#### Render streaming message
When `drafts[activeSessionId]` exists, render a **special assistant bubble** after the last persisted message:

```tsx
{drafts[activeSessionId] && (
  <StreamingMessageBubble text={drafts[activeSessionId]} />
)}
```

#### Replace static spinner
The current spinner shows "THINKING..." for any non-ready status. Instead:
- When a draft exists → show the streaming bubble (no spinner).
- When no draft but status is not ready → show spinner with more specific text based on latest event:
  - If last event was `tool_call` with `status: "started"` → `USING_SKILL: file_read...`
  - If last event was `phase_start: context_inject` → `INJECTING_CONTEXT...`
  - Otherwise → `THINKING...`

#### Tool cards (Mode B+)
Render a collapsible "Skills" bar above the streaming bubble when `toolCalls[sessionId]` has active items.

### 5.5 New Components

#### `StreamingMessageBubble.tsx`
```typescript
export function StreamingMessageBubble({ text }: { text: string }) {
  return (
    <div className="flex gap-4 max-w-[80%]">
      <div className="w-8 h-8 ..."><Bot className="w-4 h-4" /></div>
      <div className="bg-bg-elevated border border-border-dim p-4 ...">
        <span className="text-sm leading-relaxed font-mono whitespace-pre-wrap">
          {text}
          <span className="inline-block w-2 h-4 bg-accent-cyan animate-pulse ml-0.5" />
        </span>
      </div>
    </div>
  )
}
```

#### `ToolCallCard.tsx`
```typescript
export interface ToolCallEvent {
  tool: string
  status: 'started' | 'done'
  result_summary?: string
  duration_ms?: number
}

export function ToolCallCard({ event }: { event: ToolCallEvent }) {
  // Compact monospace card with spinner → checkmark transition
}
```

#### `ProcessTracePane.tsx`
```typescript
export function ProcessTracePane({ events }: { events: ProcessTraceEvent[] }) {
  // Collapsible bottom/drawer with timeline of phase_start, phase_end, turn_start, turn_end, debug_prompt, debug_response
}
```

### 5.6 `AgentDetailPage.tsx`

Add a "Streaming Mode" `<Select>` in the Model section (or Advanced section):

```tsx
<Select
  value={form.streaming_mode || 'silent'}
  onChange={(e) => setField('streaming_mode', e.target.value)}
>
  <option value="silent">Silent (batch) — current behavior</option>
  <option value="text">Live text — token reveal</option>
  <option value="tools">Live + tools — skill cards</option>
  <option value="trace">Process trace — full lifecycle</option>
  <option value="debug">Debug — raw prompt inspector</option>
</Select>
```

Update `buildForm`, dirty detection, and save handler for `streaming_mode`.

---

## 6. Channel Adapter Changes (Phase 2)

### 6.1 Telegram
- Add `send_typing_action(user_id, agent_id)` method calling `sendChatAction` with `"typing"`.
- Core calls Channels when a session transitions to a "processing" state.

### 6.2 WhatsApp
- WhatsApp Business API has no typing indicator. Skip.
- For Mode B, prepend a one-line italic prefix to the final message: `🔧 Used: file_read, summarize_text`.

---

## 7. Backward Compatibility & Rollout

### 7.1 Default Behavior
- All existing agents default to `streaming_mode: "silent"` (Mode 0).
- Board UI ignores unknown `session:stream_event` types gracefully.
- Agent SDK without the new code continues to work exactly as before.

### 7.2 Agent/SDK Version Coordination
- The `AgentRunner` checks `self.config.config.get("streaming_mode", "silent")`. If the config key is missing, it falls back to silent.
- No breaking changes to `reply_to_session` or `complete_task`.

### 7.3 Redis Memory Safety
- Draft keys expire in 300s.
- `XTRIM`-like behavior is unnecessary because we use simple string keys.
- If an agent crashes mid-stream, the draft remains in Redis for 5 min, then auto-expires.

---

## 8. File Inventory

### Agent SDK (`isli-agent-sdk`)
| File | Change |
|------|--------|
| `src/isli_agent/runner.py` | Add `_websocket`, `_outgoing_queue`, `_emit_stream_event`, `_stream_text`, `_drain_outgoing_queue`, instrument `_execute_session_message` and `_execute_task` |
| `src/isli_agent/models.py` | Add `streaming_mode` validator to `AgentConfig` (optional, since config is `dict`) |

### Core (`isli-core`)
| File | Change |
|------|--------|
| `src/isli_core/routers/ws.py` | Parse `agent:stream_event` in `agent_ws()`, append to Redis draft, store debug events in Redis (no WS broadcast), fan out to board |
| `src/isli_core/routers/sessions.py` | Add `GET /{session_id}/draft`, `GET /{session_id}/debug-trace` (admin), clear draft/debug_trace in `reply_to_session` |
| `src/isli_core/routers/agents.py` | Add `streaming_mode` to schemas, validation, `AgentOut.from_agent` |
| `src/isli_core/models.py` | Add `metadata` JSON column to `Session` |
| `alembic/versions/..._add_session_metadata.py` | **New** — add `metadata` column to `sessions` |

### Board (`isli-board`)
| File | Change |
|------|--------|
| `src/types/index.ts` | Add `StreamingEvent`, extend `BoardMessage` |
| `src/contexts/BoardSocketContext.tsx` | Extend union type |
| `src/App.tsx` | Handle `session:stream_event` |
| `src/components/ConversationsPage.tsx` | Add draft/toolCall/processTrace state, render streaming bubble, dynamic status text |
| `src/components/StreamingMessageBubble.tsx` | **New** |
| `src/components/ToolCallCard.tsx` | **New** |
| `src/components/ProcessTracePane.tsx` | **New** |
| `src/components/AgentDetailPage.tsx` | Add streaming mode select, dirty detection, save |
| `src/hooks/useSessionStream.ts` | **New** — thin hook over `useBoardSocket` |

### Channels (`isli-channels`)
| File | Change |
|------|--------|
| `src/isli_channels/adapters/telegram.py` | Phase 2: `send_typing_action` |

---

## 9. Phased Implementation Roadmap

### Phase 1: Foundation + Mode A (Live Text)
**Goal:** Text appears word-by-word in Board UI.

1. Agent SDK: add WS queue, `_emit_stream_event`, `_stream_text`.
2. Core: parse agent WS messages, fan out, draft endpoint.
3. Board: `StreamingMessageBubble`, draft state in `ConversationsPage`.
4. Board: `AgentDetailPage` streaming mode dropdown.
5. Test: set mode to `"text"`, send a message, verify chunked reveal.

### Phase 2: Mode B (Live + Tools)
**Goal:** Users see skill cards before the answer.

1. Agent SDK: emit `tool_call` events around `_execute_tool`.
2. Board: `ToolCallCard` component, render above streaming bubble.
3. Board: collapse cards 5s after completion (pin on click).

### Phase 3: Mode C (Process Trace)
**Goal:** Full ReAct lifecycle visible in collapsible pane.

1. Agent SDK: emit `phase_start/end`, `turn_start/end`, `cost_report`.
2. Board: `ProcessTracePane` as a bottom drawer or right sidebar.
3. Board: toggle button in chat header to show/hide trace.

### Phase 4: Mode D (Debug)
**Goal:** Raw prompt/response inspector.

1. Agent SDK: emit `debug_prompt` and `debug_response` with truncated previews.
2. Board: extend `ProcessTracePane` with expandable raw JSON.
3. Board: only visible when `streaming_mode === "debug"`.

### Phase 5: Channel Typing Indicators
**Goal:** Telegram users see "typing..." while the agent works.

1. Core: new `POST /v1/channels/{channel}/typing` endpoint.
2. Channels: Telegram `sendChatAction`, WhatsApp placeholder message.
3. Trigger on `phase_start: llm_call`.

---

## 10. Risk & Mitigation

| Risk | Mitigation |
|------|------------|
| Agent WS disconnects mid-stream | Outgoing queue buffers up to 1000 events; reconnect drains at 1ms/send. Process trace events are ephemeral and not replayed. |
| Board WS disconnects | Draft persisted in Redis; `GET /draft` restores state on reconnect |
| High-frequency token spam | Chunk size 5 chars + 20ms delay limits to ~250 events/sec per session. Configurable per agent. |
| Redis draft memory leak | 300s TTL on all draft and debug_trace keys |
| Agent crashes mid-stream | Draft auto-expires; final `reply_to_session` still works normally |
| Backward compat with old SDK | New code is additive; old agents without `_emit_stream_event` continue silently |
| Telegram rate limits on typing | Phase 5 debounces typing indicator to 1 per 3 seconds |
| Debug prompt data exposure | `debug_prompt`/`debug_response` **never** broadcast over WS. Stored in Redis only, served via `GET /debug-trace` with `require_admin_auth`. |
| Streaming failure kills agent | Every `_emit_stream_event` call is wrapped in `try/except`. Streaming failure is logged and swallowed. Mode 0 is the implicit fallback. |
| Per-session override resolution | Board UI passes `metadata: { streaming_mode: "debug" }` in `POST /sessions/{id}/message`. Core stores it; agent reads it on `session:message` event. |

---

## 11. Testing Strategy

1. **Unit (Agent SDK):** Mock websocket, verify `_emit_stream_event` filters by mode correctly.
2. **Integration (Core):** Open agent WS, send `agent:stream_event`, verify board WS receives `session:stream_event` and Redis draft accumulates.
3. **E2E (Board):** Cypress/Playwright: select agent, set mode to "text", send message, assert streaming bubble appears and text grows.
4. **Regression:** Verify Mode 0 (silent) produces identical behavior to pre-change.
5. **Graceful degradation:**
   - Kill agent WS mid-stream → verify final reply still arrives via REST
   - Kill board WS mid-stream → reconnect and verify `GET /draft` restores state
   - Raise exception inside `_emit_stream_event` → verify agent continues and reply is still sent
   - Set invalid `streaming_mode` → verify falls back to silent
   - Set `stream_chunk_size: -1` → verify defaults to 5
   - Send `debug_prompt` event → verify it does NOT appear in board WS, only in Redis
   - Call `GET /debug-trace` without admin auth → verify 403
6. **Per-session override:** Create session with `metadata: { streaming_mode: "debug" }`, verify agent emits debug events even though agent config is "silent".

---

## 12. Summary

This plan implements all five streaming modes using **only** the existing bidirectional
WebSocket infrastructure. The agent emits events over its WS; Core fans them out to the
Board; the Board renders draft text, tool cards, and process traces. Channels stay
unchanged in Phase 1. The default mode is `silent`, ensuring zero breaking changes.

**Estimated effort:**
- Phase 1: ~2–3 hours
- Phase 2: ~1 hour
- Phase 3: ~1.5 hours
- Phase 4: ~1 hour
- Phase 5: ~1.5 hours
