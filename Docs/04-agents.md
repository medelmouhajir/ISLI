# 04 — Agents

## Agent Philosophy

In ISLI, agents are **sovereign domain specialists**. There is no top-level orchestrator agent. Coordination happens through the Kanban board (task delegation), not through an agent hierarchy.

An agent is:
- A running Python process
- Connected to Core API via WebSocket
- Assigned one or more channels
- Using its own API key and model
- Given context by the Keeper before every task

---

## Agent Lifecycle

```
REGISTERED → ONLINE → IDLE → ACTIVE → IDLE
                  ↓               ↓
               PAUSED          BLOCKED (waiting for delegation)
                  ↓
              OFFLINE
```

State transitions are managed by Core API and broadcast to the Kanban board.

---

## Agent Definition File (`agent.yaml`)

Each agent is defined by a YAML config file:

```yaml
agent:
  id: agent_research
  name: "Research"
  description: "Deep research and knowledge retrieval specialist"
  version: "1.0.0"

  model:
    provider: anthropic          # anthropic | openai | google | mistral | custom
    model_id: claude-sonnet-4-6
    api_key_env: ANTHROPIC_API_KEY
    max_tokens: 4096
    temperature: 0.3

  persona: |
    You are a meticulous research specialist. You gather accurate information,
    cite sources, and present findings in structured formats. You always
    validate claims before presenting them.

  channels:
    - type: telegram
      bot_token_env: TELEGRAM_RESEARCH_BOT_TOKEN
      allowed_user_ids: []           # empty = all

  skills:
    - web-search
    - pdf-extract
    - file-read
    - file-write
    - file-list
    - file-delete

  memory:
    scope: agent:research
    episodic_top_k: 5
    memory_similarity_threshold: 0.4  # cosine distance threshold (< 0.4 is relevant)
    semantic_collections:
      - isli_domain_research
      - isli_preferences

  heartbeat:
    interval_seconds: 180

  task_types:
    - research
    - summarization
    - fact-check
    - web-scrape

```

---

## Agent Registration Flow

```
1. Agent process starts
2. POST /v1/agents/register  { agent_id, name, capabilities, channel_config }
3. Core API issues JWT token for this agent
4. Agent opens WebSocket connection to /ws/agents/{agent_id}
5. Core API sends: { type: "registered", keeper_endpoint, ... }
6. Agent begins heartbeat loop
7. Kanban board shows agent card as ONLINE
```

---

## Agent Turn Execution

When a task is assigned to an agent:

```python
# Simplified agent SDK prompt assembly
def _assemble_system_prompt(self, context_summary: str) -> str:
    identity_parts = [
        f"You are {self.config.name} (ID: {self.config.id}).",
    ]
    if self.config.description:
        identity_parts.append(f"Description: {self.config.description}")
    if self.config.persona:
        identity_parts.append(f"Persona: {self.config.persona}")

    identity_block = "=== IDENTITY ===\n" + "\n".join(identity_parts)
    
    prompt = f"{identity_block}\n\n{context_summary}"
    
    if self.config.config:
        prompt += f"\n\n=== ADDITIONAL CONFIG ===\n{json.dumps(self.config.config, indent=2)}"
        
    return prompt

async def execute_task(task: Task):
    # 1. Get Keeper context injection (includes identity, journal, and memories)
    context_summary = task.context_summary
    if not context_summary:
        context_summary = await keeper.get_context_injection(...)

    # 2. Build system prompt
    system_prompt = self._assemble_system_prompt(context_summary)

    # 3. Run agent loop (ReAct pattern)
    messages = [{"role": "user", "content": task.input}]
    ...
```

---

## The Keeper Role in Agent Turns

```
Before turn:  Keeper.context_inject()  → enriches agent prompt
During turn:  Agent runs independently  → Keeper uninvolved
After turn:   Keeper.store_episodic()   → writes to Tier 2 memory
On heartbeat: Keeper.validate()         → anomaly detection
```

---

## Agent Categories

ISLI does not pre-define agent names or personas. You define your own. But these archetypes cover most needs:

| Category | Example Role | Suggested Model |
|----------|-------------|----------------|
| Research | Web research, fact-check | Claude Sonnet / GPT-4o |
| Communication | Email drafting, messaging | Claude Haiku / GPT-4o-mini |
| Analysis | Data analysis, reports | Claude Sonnet / Gemini Pro |
| Code | Development, debugging | Claude Sonnet / GPT-4o |
| Domain Expert | Legal, finance, HR | Claude Opus / GPT-4o |
| Admin | Scheduling, reminders | GPT-4o-mini / Gemini Flash |

---

## Agent Permissions Model

Agents operate under a capability-scoped permission system enforced by Core API:

| Permission | Description |
|-----------|-------------|
| `tasks:read` | Read tasks from Kanban |
| `tasks:create` | Create new tasks (delegation) |
| `tasks:update:own` | Update own task status/output |
| `memory:read:own` | Read own agent memory |
| `memory:write:own` | Write to own agent memory |
| `skills:invoke` | Call skills via proxy |
| `channels:send` | Send messages via assigned channels |
| `agents:list` | See other registered agents |

Agents cannot read each other's memory, read each other's task details, or impersonate other agents.

---

## Adding a New Agent

### Method 1: Docker Compose Profile (Recommended)

Agents are started via the `agent-runner` service with Docker Compose profiles:

```bash
# Start a specific agent
AGENT_ID=kimi-02 docker compose --profile agents up -d agent-runner

# Start another agent
AGENT_ID=my-new-agent docker compose --profile agents up -d agent-runner
```

The `agent-runner` service:
- Fetches agent config dynamically from Core API
- Recovers a fresh token on startup (handles 409 for existing agents)
- Connects via WebSocket and begins listening for events
- Does NOT auto-start with the core stack (`profiles: [agents]`)

### Method 2: Native Python

```bash
export CORE_API_URL=http://localhost:8000
export ADMIN_API_KEY=...
python isli-agent-sdk/examples/start_agent.py kimi-02
```

### Prerequisites

1. Agent record exists in Core API (created via board or API)
2. `AGENT_ID` matches the agent's `id` in the database
3. `ADMIN_API_KEY` is set in `.env`
4. Agent `model_provider` and `model_id` are configured

No code changes required in Core API. No orchestrator reconfiguration. Just run it.

### Tool Registration (Auto-Discovery from Skills)

The `AgentRunner` automatically registers tools based on the agent's synced `config.skills` list from Core. After calling `register()`, the runner populates its toolbox via `_auto_register_tools_from_skills()`:

```python
# AgentRunner.start() automatically does this:
reg_data = await self.client.register(self.config)
self.config = AgentConfig.model_validate(reg_data)   # sync skills from DB
self._auto_register_tools_from_skills()               # register matching tools
self.add_tool("get_current_datetime", get_current_datetime, DATETIME_DEF)
```

**Result:** An agent with `skills: ["file-read", "send-message", "memory-save"]` will have `file_read`, `send_message`, and `memory_save` callable at runtime with zero manual registration.

For backward compatibility, you can still register manually:

```python
from isli_agent import AgentRunner, AgentConfig
from isli_agent.tools.channels import send_message, SEND_MESSAGE_DEF
from isli_agent.tools.workspace import file_read, FILE_READ_DEF

runner = AgentRunner(config, core_url)
runner.add_workspace_tools()   # file_read, file_write, file_list, file_delete
runner.add_channel_tools()     # send_message
runner.add_tool("my_custom", my_func, MY_CUSTOM_DEF)
```

### Runtime Dependency Injection

Tools that need `agent_id` or `core_client` receive them automatically at invocation time — the LLM only sees user-facing parameters. For example, `send_message` has this signature:

```python
async def send_message(agent_id: str, channel: str, channel_user_id: str, text: str, core_client: CoreClient)
```

But the LLM tool definition only exposes `channel`, `channel_user_id`, and `text`. The `AgentRunner._execute_tool()` inspects the function signature and injects `agent_id` and `core_client` before calling the function. This keeps tool definitions clean while the runner handles the plumbing.

### Workspace File Tools

Agents can read and write files in their isolated workspace via the `isli-agent-sdk` built-in tools:

```python
from isli_agent import AgentRunner, AgentConfig

config = AgentConfig(
    id="my-agent",
    name="My Agent",
    skills=["file-read", "file-write", "file-list", "file-delete"],
    ...
)
runner = AgentRunner(config, core_url)
runner.add_workspace_tools()  # One-liner registration
```

These tools (`file_read`, `file_write`, `file_list`, `file_delete`) are automatically bound to the agent's ID and Core client via runtime injection. They raise typed exceptions (`WorkspaceNotFoundError`, `WorkspacePathError`, `WorkspaceQuotaError`) so the ReAct loop can recover gracefully.

### Token Recovery and Revocation

When an agent already exists, `POST /v1/agents` returns 409. The SDK automatically calls `POST /v1/agents/{id}/token` with admin auth to recover a fresh token. This endpoint sets `agent.token_issued_at`, which invalidates any previous tokens via `require_internal_auth`. Old tokens become unusable the moment a new one is issued.

**Security benefit:** If an admin key leaks, recovering a new token for an agent automatically revokes all previous tokens for that agent.

**Important implementation detail (fixed 2026-05-18):** The heartbeat endpoint must update `token_issued_at` **after** all side effects complete and the new token is guaranteed to be returned. If revocation is committed before the response is sent, a failure in `AuditWriter`, telemetry, or event emission leaves the agent with a revoked token and no replacement — causing a permanent 401 lockout.

**Task API auth note (fixed 2026-05-18):** Task mutation endpoints (`PUT /tasks/{id}`, `POST /tasks/{id}/move`, `POST /tasks/{id}/checkpoint`) require the admin API key, not the agent JWT. The agent SDK uses `use_admin=True` when calling these endpoints from `complete_task()`, `move_task()`, and `save_checkpoint()`.

---

## Agent Observability (Live Logs)

Agents implement real-time log forwarding to the Shared Blackboard for human-in-the-loop monitoring.

### Architecture
1. **Producer**: The `isli-agent-sdk` uses a custom `structlog` processor to publish every log entry as JSON to Redis.
2. **Transport**: Redis Pub/Sub channel `agent:{agent_id}:logs`.
3. **Gateway**: `isli-core` provides a WebSocket endpoint at `WS /v1/agents/{agent_id}/logs/stream`.
4. **Consumer**: `isli-board` connects to the WebSocket and displays a live terminal view.

### Configuration
In `docker-compose.yml`, the agent must have `REDIS_URL` configured to enable log forwarding:
```yaml
agent-runner:
  environment:
    - REDIS_URL=redis://redis:6379/0
    - AGENT_ID=${AGENT_ID}
```

### UI Access
Users can view live logs by navigating to the **Agent Detail** page and clicking the **"Live Logs"** button. This opens a dedicated terminal view with support for real-time streaming, text filtering, and log downloading.

---

## Agent Runner Error Handling

When a session message fails (e.g., LLM provider overloaded, network timeout), the agent runner sends an error reply to the user via the channel adapter.

**Before 2026-05-18:** A broad `except Exception` sent the static string:
> "Sorry, I encountered an error processing your message. Please try again."

This was opaque — users couldn't distinguish model overload from a local bug.

**After 2026-05-18:** The runner classifies the exception string:
- `"overloaded"` / `"temporarily"` → "The AI model is temporarily overloaded. Please try again in a moment."
- `"APIConnectionError"` / `"timeout"` → "Connection to the AI model timed out. Please try again shortly."
- Other exceptions → Original generic fallback

The `acompletion` call also has `timeout=120` to fail fast instead of hanging indefinitely. An optional `LITELLM_DEBUG=true` env var enables LiteLLM verbose logging for future diagnosis.

### Session Messaging Loop

Agents can also participate in long-lived chat sessions. When a `session:message` event is received:

1. **Context Recovery**: The SDK receives the session history and Keeper-injected context directly in the event payload.
2. **LLM Completion**: The agent generates a reply using the same ReAct loop as tasks.
3. **Reply Submission**: The agent sends the response via `POST /v1/sessions/{id}/reply`.
4. **UI Update**: Core API broadcasts `session:updated` to trigger frontend refreshes.

**Implementation** (`runner.py`):

```python
# In _ws_loop() — non-blocking task spawn, same pattern as task events
elif event["type"] == "session:message":
    payload = event["payload"]
    logger.info("runner.session_message_detected", session_id=payload.get("session_id"))
    asyncio.create_task(self._execute_session_message(payload))
```

`_execute_session_message()` reuses `_assemble_system_prompt()`, `_execute_tool()`, and the LiteLLM ReAct loop from `_execute_task()`. The final response is sent via `reply_to_session()` wrapped in `try/except` with explicit logging to prevent silent failures. Session messages are never blocked inline — slow LLM responses run in background tasks so heartbeats and other WebSocket events continue normally.

---

## Agent System Gaps
 (2026-05-11 Research)

The following gaps were identified during a parallel 12-agent research review:

### Critical
- **Token budget enforcement (F15) entirely unimplemented** — the "optional daily cap" exists only in docs; no enforcement code.
- **No delegation cycle detection** — `can_delegate_to` enforces edges but not acyclicity; A→B→C→A loops forever.
- **Unbounded delegation chain length** — no `max_depth` enforced; 2026 research shows >3-agent chains degrade to ~22.5% accuracy.

### High
- **No global timeout for delegation chains** — individual tasks expire after 5 min, but cumulative chain timeout is absent.
- **No fallback agents when primary fails** — `OFFLINE` state exists but no auto-reassignment or hot-standby.
- **No model fallback strategy** — agents have one statically assigned model with no downgrade path.
- **Insufficient defense against consensus inertia** — F6 mitigations are passive isolation only; no active BICR "Challenge" step.
- **No deadlock detection** — BLOCKED agents waiting for child tasks can circularly wait with no breaker.
- ~~**JWTs long-lived with no rotation**~~ — **Fixed 2026-05-18**. `token_issued_at` column enables revocation. `POST /v1/agents/{id}/token` issues fresh tokens and invalidates old ones. Heartbeat renewals also update `token_issued_at`.
- ~~**Heartbeat validator flags agents on single flaky LLM response**~~ — **Fixed 2026-05-18**. Redis counter requires 3 consecutive anomalies before `flagged`; valid heartbeats auto-unflag.
- ~~**WebSocket auth bypasses token revocation**~~ — **Fixed 2026-05-18**. WebSocket endpoint now calls `_check_token_revocation` after `verify_internal_token`.

### Medium
- **No Kanban queue depth limit per agent** — unlimited ASSIGNED tasks with no backpressure.
- **No guard against delegating to offline agents** — tasks sit in ASSIGNED indefinitely.
- **No priority inversion detection** — high-priority tasks can be blocked behind low-priority ones.
- **No conflict resolution for simultaneous assignments** — two tasks to the same agent may contradict each other.
- **No monitoring for exponential relay degradation** — chain length and semantic drift are not measured.
- **Agent turn loop ignores `token_budget`** — it is a soft hint, not a hard limit enforced by Core API.

> See `Memory/ISLI-Research-Report.md` for full details and recommendations.