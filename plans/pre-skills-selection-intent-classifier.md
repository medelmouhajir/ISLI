# Plan: Pre-Skills Selection via Keeper Intent Classifier

## Goal
Before each agent turn, run a lightweight intent classifier in Keeper so the agent only receives relevant skill metadata in its system prompt and `tools` array. Agents can dynamically discover all assigned skills via a new `discover_skills` tool.

## Motivation
- The SDK currently passes **all** registered tool definitions to LiteLLM on every ReAct turn.
- With 50+ skills, the JSON schemas alone consume **~2,500–6,000+ tokens** per turn (depending on parameter richness).
- Most user messages only need 3–7 tools (e.g., web-search + summarize + memory-save).
- This bloated `tools` array increases cost, latency, and context-window pressure.

## High-Level Flow

```
User message → Core (task/session created)
                  ↓
           ContextWorker calls Keeper
             ├─ /session-prep  (mesh path — SAME LLM call)
             └─ /intent/classify (legacy path — lightweight extra call)
                  ↓
           Keeper returns: context_summary + relevant_skills
                  ↓
           Core emits WebSocket event with relevant_skills
                  ↓
           Agent SDK receives event
             ├─ Filters self.tool_definitions for this turn
             ├─ Always includes universal tools + discover_skills
             └─ Falls back to full set if discover_skills is invoked
                  ↓
           LiteLLM call with slim tools array
```

---

## Detailed Implementation Steps

### Phase 1 — Keeper: Intent Classification

#### 1.1 Extend `SESSION_PREP_PROMPT` (same LLM call)
**File**: `isli-keeper/src/isli_keeper/pii_prompts.py`

Add a third job to the existing prompt:

```
3. SKILL INTENT: From the list of available skills below, select the most relevant ones for the user's message. Return them as a JSON array of skill names. If the intent is unclear or broad, return an empty array.
```

Update the JSON schema in `SESSION_PREP_PROMPT`:
```json
{
  "context_summary": "...",
  "entities": [...],
  "relevant_skills": ["skill-name-1", "skill-name-2"]
}
```

#### 1.2 Update `SessionPrepResponse` model
**File**: `isli-keeper/src/isli_keeper/pii_models.py`

Add:
```python
relevant_skills: list[str] = []
```

#### 1.3 Parse `relevant_skills` in `session_prep.py`
**File**: `isli-keeper/src/isli_keeper/session_prep.py`

In `_parse_dual_output`, extract `relevant_skills` from the SLM JSON and include it in the response dict.

#### 1.4 New Keeper endpoint: `POST /intent/classify`
**File**: `isli-keeper/src/isli_keeper/main.py`

For agents **not** on the PII mesh path (legacy `/context/inject`), Core needs a standalone lightweight endpoint.

**Request model**:
```python
class IntentClassifyRequest(BaseModel):
    user_message: str
    available_skills: list[dict[str, str]]  # [{"name": "...", "description": "...", "category": "..."}]
    agent_id: str | None = None
```

**Response model**:
```python
class IntentClassifyResponse(BaseModel):
    relevant_skills: list[str]
    reason: str = ""
    confidence: float = 0.0
```

**Implementation**:
- Build a lightweight prompt (~500 tokens) that lists skill names+descriptions and asks the SLM to return relevant ones as JSON.
- Use the priority queue (P0 or P1) since this is on the critical path.
- Fallback: if Ollama is unreachable or returns invalid JSON, return ALL skill names (safe degradation).
- Cache result in-memory keyed by `(user_message_hash, available_skills_hash)` with 60s TTL.

#### 1.5 Metrics and events
- Emit `keeper:inference` event for `/intent/classify` with latency and status.
- Log `keeper.intent_classified` with `agent_id`, `relevant_skills`, `confidence`.

---

### Phase 2 — Core: ContextWorker Integration

#### 2.1 Fetch assigned skills for the agent
**File**: `isli-core/src/isli_core/jobs/context_worker.py`

In `_call_keeper`, load the agent's `skills` list from `agent.config` or `agent.skills`.

#### 2.2 Call intent classification
**File**: `isli-core/src/isli_core/jobs/context_worker.py`

In `_process_one`, after getting context_summary:

```python
if agent_config.get("pii_mesh_enabled"):
    # relevant_skills comes back from /session-prep in the same response
    relevant_skills = prep_result.get("relevant_skills", [])
else:
    # Legacy path: extra call to /intent/classify
    relevant_skills = await KeeperClient.classify_intent(
        user_message=task_description or last_user_message,
        available_skills=[{"name": s, **SKILL_METADATA[s]} for s in agent_skills if s in SKILL_METADATA],
    )
```

> **Note on "same LLM call"**: For mesh agents, the classification is literally part of the `/session-prep` SLM call. For legacy agents, we accept a separate lightweight call because `/context/inject` is intentionally retrieval-only and fast. The overhead is ~200–500ms (same Ollama model, tiny prompt).

#### 2.3 Include `relevant_skills` in WebSocket events
**File**: `isli-core/src/isli_core/jobs/context_worker.py` (`_on_success`)

For both `task:updated` and `session:message` events, add:
```python
"relevant_skills": relevant_skills,
```

This ensures the agent SDK receives the filtered list inline.

#### 2.4 `KeeperClient` new method
**File**: `isli-core/src/isli_core/memory/keeper_client.py`

Add:
```python
@staticmethod
async def classify_intent(user_message: str, available_skills: list[dict]) -> list[str]: ...
```

---

### Phase 3 — Agent SDK: Per-Turn Tool Filtering

#### 3.1 `_assemble_system_prompt` accepts `relevant_skills`
**File**: `isli-agent-sdk/src/isli_agent/runner.py`

Change signature:
```python
def _assemble_system_prompt(self, context_summary: str, session_info: dict | None = None, relevant_skills: list[str] | None = None) -> str:
```

Use `relevant_skills` to build `tools_list` from the filtered subset. Fall back to all registered tools if `relevant_skills` is `None`.

#### 3.2 Per-turn `tool_definitions` filtering
**File**: `isli-agent-sdk/src/isli_agent/runner.py`

Store:
- `self._all_tool_definitions` — full set (populated at startup).
- `self._active_tool_definitions` — filtered set for current turn.

At the start of `_execute_task` and `_execute_session_message`:
```python
self._active_tool_definitions = self._filter_tools_by_relevance(
    self._all_tool_definitions,
    payload.get("relevant_skills"),
)
```

**Filtering rules**:
1. If `relevant_skills` is empty/missing → use ALL tools (safe default).
2. Map `relevant_skills` names to tool definitions using `SKILL_NAME_ALIASES`.
3. Always include `get_current_datetime`.
4. Always include `discover_skills` (see 3.4).

#### 3.3 Pass `_active_tool_definitions` to LiteLLM
Replace `self.tool_definitions` with `self._active_tool_definitions` in the `completion_kwargs`:
```python
"tools": self._active_tool_definitions if self._active_tool_definitions else None,
```

#### 3.4 New SDK tool: `discover_skills`
**File**: `isli-agent-sdk/src/isli_agent/tools/discover_skills.py`

This tool fetches the agent's full assigned skills list from Core and returns them as formatted text.

```python
async def discover_skills(core_client: CoreClient) -> str:
    skills = await core_client.get_skills()
    return "\n".join(f"- {s['name']}: {s['description']}" for s in skills)
```

Register it universally (like `get_current_datetime`) in `AgentRunner.__init__`.

#### 3.5 Dynamic expansion fallback
In the ReAct loop, after tool executions, detect if `discover_skills` was among the tools called. If so:
```python
if any(tc.function.name == "discover_skills" for tc in tool_calls):
    logger.info("runner.expanding_tools_after_discovery")
    self._active_tool_definitions = self._all_tool_definitions
```

This means: the NEXT LLM turn within the same task/session will have access to ALL tools. The LLM already read the `discover_skills` result, so it knows what's available and can now invoke it.

---

### Phase 4 — System Prompt & Prompts YAML

#### 4.1 Update system prompt template
**File**: `prompts.yaml` (repo root)

Add a hint to the `=== AVAILABLE TOOLS ===` section:
```yaml
=== AVAILABLE TOOLS ===
You have access to the following tools. Call them when appropriate.
{tools_list}

If you need a tool that is not listed above, call discover_skills to see all available capabilities.
```

#### 4.2 Register `discover_skills` in `tool_descriptions`
Add an entry in `prompts.yaml` under `agent.tool_descriptions`:
```yaml
discover_skills: List all skills assigned to this agent. Use this when you need a capability that is not currently visible in your tool list.
```

---

### Phase 5 — Caching & Performance

#### 5.1 ContextCache key inclusion
**File**: `isli-core/src/isli_core/memory/context_cache.py`

The cache key already uses `turn_hash = SHA256(session_id, task_description, last_message_ids)`. Since `relevant_skills` is derived from `task_description` and `last_message_ids`, it will naturally invalidate when the message changes. No changes needed.

#### 5.2 Agent-side cache
The agent runner does not cache `relevant_skills` across different tasks/sessions; it receives it per-event. No changes needed.

---

## Files to Modify

| File | Change |
|------|--------|
| `isli-keeper/src/isli_keeper/pii_prompts.py` | Extend `SESSION_PREP_PROMPT` with skill-intent job |
| `isli-keeper/src/isli_keeper/pii_models.py` | Add `relevant_skills` to `SessionPrepResponse` |
| `isli-keeper/src/isli_keeper/session_prep.py` | Parse and forward `relevant_skills` |
| `isli-keeper/src/isli_keeper/main.py` | Add `POST /intent/classify` endpoint |
| `isli-core/src/isli_core/memory/keeper_client.py` | Add `classify_intent()` client method |
| `isli-core/src/isli_core/jobs/context_worker.py` | Integrate intent classification into `_process_one` / `_on_success` |
| `isli-agent-sdk/src/isli_agent/runner.py` | Filter `tool_definitions` per turn; add `discover_skills` handling |
| `isli-agent-sdk/src/isli_agent/tools/discover_skills.py` | **New file** — tool implementation |
| `isli-agent-sdk/src/isli_agent/tools/__init__.py` | Export `discover_skills` and its definition |
| `prompts.yaml` | Update system prompt template and `tool_descriptions` |

## Rollback Strategy
- If the intent classifier is inaccurate, Core can bypass it by setting `relevant_skills: None` (falls back to all tools).
- Add a feature flag `intent_filter_enabled` in agent `config` (default `false` for gradual rollout).

## Testing Plan
1. **Unit test** `discover_skills` tool wrapper.
2. **Unit test** `AgentRunner._filter_tools_by_relevance` with various `relevant_skills` inputs.
3. **Integration test** Keeper `/intent/classify` with a sample user message and 10 skills.
4. **Integration test** Mesh path: verify `/session-prep` returns `relevant_skills` in the JSON.
5. **End-to-end** Send a session message → verify WebSocket event includes `relevant_skills` → verify agent prompt only contains relevant tools.
6. **Fallback test** Trigger `discover_skills` mid-task → verify next ReAct turn receives full tool set.
