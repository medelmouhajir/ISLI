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
    - file-write

  memory:
    scope: agent:research
    episodic_top_k: 5
    semantic_collections:
      - isli_domain_research
      - isli_preferences

  heartbeat:
    interval_seconds: 30

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
2. POST /api/agents/register  { agent_id, name, capabilities, channel_config }
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
# Simplified agent turn loop
async def execute_task(task: Task):
    # 1. Get Keeper context injection
    injection = await keeper.get_context_injection(
        agent_id=self.agent_id,
        session_id=task.session_id,
        task_description=task.description
    )

    # 2. Build system prompt
    system_prompt = f"""
    {self.persona}

    === CONTEXT FROM MEMORY ===
    {injection.context_summary}

    === RELEVANT PAST EVENTS ===
    {chr(10).join(injection.relevant_memories)}
    """

    # 3. Run agent loop (ReAct pattern)
    messages = [{"role": "user", "content": task.input}]
    while True:
        response = await self.model_client.complete(
            system=system_prompt,
            messages=messages,
            tools=self.available_tools
        )

        if response.stop_reason == "end_turn":
            break
        elif response.stop_reason == "tool_use":
            tool_result = await self.invoke_skill(response.tool_call)
            messages.append(response)
            messages.append({"role": "tool", "content": tool_result})

    # 4. Report result to Core API
    await core_api.complete_task(task.id, output=response.text)

    # 5. Keeper stores episodic memory (async, non-blocking)
    asyncio.create_task(keeper.store_episodic(task, response))
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

1. Create `my-agent/agent.yaml`
2. Create `my-agent/main.py` (using ISLI agent SDK)
3. Add API key to `.env`
4. Run: `python main.py` or `docker-compose up my-agent`
5. Agent auto-registers and appears on Kanban board

No code changes required in Core API. No orchestrator reconfiguration. Just run it.

---

## Agent System Gaps (2026-05-11 Research)

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
- **JWTs long-lived with no rotation** — issued once at registration with no expiry, refresh, or revocation.

### Medium
- **No Kanban queue depth limit per agent** — unlimited ASSIGNED tasks with no backpressure.
- **No guard against delegating to offline agents** — tasks sit in ASSIGNED indefinitely.
- **No priority inversion detection** — high-priority tasks can be blocked behind low-priority ones.
- **No conflict resolution for simultaneous assignments** — two tasks to the same agent may contradict each other.
- **No monitoring for exponential relay degradation** — chain length and semantic drift are not measured.
- **Agent turn loop ignores `token_budget`** — it is a soft hint, not a hard limit enforced by Core API.

> See `Memory/ISLI-Research-Report.md` for full details and recommendations.