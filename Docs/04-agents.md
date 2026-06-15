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
REGISTERED → STARTING → ONLINE → IDLE → ACTIVE → IDLE
                 ↓         ↓               ↓
              CRASHED    PAUSED          BLOCKED (waiting for delegation)
                 ↓         ↓
              STOPPED ← OFFLINE
                 ↑
              REBUILDING
```

State transitions are managed by Core API (and the internal **Agent Process Manager**) and broadcast to the Kanban board.

- **REGISTERED**: The agent configuration is saved in the database, but no process has been started.
- **STARTING**: Core API has spawned the agent container/process and is waiting for the first heartbeat.
- **ONLINE**: The agent has successfully connected via WebSocket and is sending heartbeats.
- **STOPPED**: The agent process has been manually terminated via the Core API/Board.
- **CRASHED**: The agent process exited with a non-zero return code.
- **OFFLINE**: The agent failed to send heartbeats for more than 180 seconds.
- **REBUILDING**: The agent-runner Docker image is being rebuilt in the background before a fresh container is spawned (triggered by **Rebuild & Restart** in the Board UI).

### Live SDK Reloading (Development)

To accelerate development of new skills and SDK features, ISLI supports **Live SDK Reloading**.

When `AGENT_SDK_HOST_PATH` is configured in ISLI Core (usually via `docker-compose.override.yml`), the **Agent Process Manager** mounts the host's `isli-agent-sdk/src` directory into every dynamically spawned agent container at `/app/src`.

The agent-runner image Dockerfile sets `PYTHONPATH=/app/src` and installs the package as editable (`pip install -e .`), so the live mount overlays the baked-in source without breaking the editable-install metadata.

**Benefits:**
- **Zero-Build Cycle:** Modify code in `isli-agent-sdk/src` and instantly see changes after clicking **Restart Agent** in the Board UI — no `docker build` needed.
- **Dynamic Skill Sync:** Use with the Board UI to add new tools to an agent's configuration and register them on-the-fly without rebuilding images.
- **Rebuild When Needed:** Click **Rebuild & Restart** to produce a fresh `isli-agent-runner:latest` image (e.g. after `requirements.txt` or `Dockerfile` changes).

---

## Agent Definition File (`agent.yaml`)

Each agent is defined by a YAML config file:

```yaml
agent:
  id: agent_research
  name: "Research"
  description: "Deep research and knowledge retrieval specialist"
  picture: null              # Optional: UUID of the uploaded avatar (blob)
  version: "1.0.0"

  model:
    provider: anthropic          # chosen from the provider registry (see Settings)
    model_id: claude-sonnet-4-6   # chosen from the provider's permitted-models list
    api_key: null                # optional per-agent override; null falls back to provider key
    max_tokens: 4096
    temperature: 0.3

  # Model Routing (added 2026-05-31)
  # See "Model Routing" section below for full details
  model_routing:
    enabled: false
    secondary_models:
      - provider: openai
        model_id: gpt-4o-mini
        label: "Cheap"
        description: "Fast and inexpensive for simple tasks"
        cost_tier: local          # local | standard | premium
      - provider: openai
        model_id: gpt-4o
        label: "Standard"
        description: "Good balance of quality and cost"
        cost_tier: standard
      - provider: anthropic
        model_id: claude-opus-4-8
        label: "Premium"
        description: "Best quality for complex reasoning"
        cost_tier: premium

  persona: |
    You are a meticulous research specialist. You gather accurate information,
    cite sources, and present findings in structured formats. You always
    validate claims before presenting them.

  channels:
    - type: telegram
      bot_token_env: TELEGRAM_RESEARCH_BOT_TOKEN
      allowed_user_ids: []           # empty = all

  # WhatsApp access mode (added 2026-05-29)
  # See Docs/07-channels.md for full details
  whatsapp:
    access_mode: opt_in              # opt_in | open | whitelist | closed | scheduled
    allowed_jids: []                 # for whitelist mode
    allowed_user_id: null            # for closed mode (single owner)
    open_rate_limit:                 # for open mode (optional)
      max_msgs: 20
      window_seconds: 3600
    schedule:                        # for scheduled mode
      timezone: "Africa/Casablanca"
      windows:
        - days: [1, 2, 3, 4, 5]
          from: "09:00"
          to: "18:00"
      off_hours_reply: "We're offline. Try again during business hours."

  skills:
    - web-search
    - pdf-extract
    - file-read
    - file-write
    - file-list
    - file-delete
    - speech-to-text      # transcribe audio via isli-audio
    - text-to-speech      # synthesize voice via isli-audio
    - interactive-debugger  # run code with breakpoints and variable inspection
    - ui-components       # render tables, cards, buttons, forms, JSON, timelines, metrics inline in chat (see Docs/13-immersive-chat-ui.md)
    - git-clone           # clone remote repositories into workspace
    - git-status          # show modified/staged/untracked files
    - git-commit          # stage and commit changes
    - git-push            # push branch to remote
    - git-pull            # pull changes from remote
    - git-branch-list     # list branches
    - git-branch-create   # create new branch
    - git-checkout        # switch branch
    - git-log             # view commit history
    - get-secret          # retrieve API keys, DB credentials, tokens from encrypted vault
    - notify-user         # send in-app + Telegram notifications to users (rate-limited, priority-aware)
    - web-browse-navigate # navigate a browser to a URL (persistent session per agent)
    - web-browse-snapshot # take accessibility-tree snapshot with @ref IDs
    - web-browse-click    # click an element by @ref ID
    - web-browse-type     # type text into an input by @ref ID
    - web-browse-press    # press a keyboard key (Enter, Tab, Escape)
    - web-browse-scroll   # scroll up/down on the current page
    - web-browse-back     # navigate back in browser history
    - web-browse-console  # retrieve browser console logs (delta since last call)
    - web-browse-vision   # take a screenshot of the current page
    - web-browse-images   # list all images with src/alt/dimensions

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
    - browser-automation

```

---

## API Key Fallback Chain

Each agent uses a **three-layer fallback** for its LLM API key:

1. **Agent override** — `Agent.api_key` (set per-agent via board or API)
2. **Provider global** — `LlmProvider.api_key` (set in Settings → Model API Keys)
3. **Environment variable** — `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, etc. (classic `.env` fallback)

The runner calls `self.client.register()`, which internally calls `GET /v1/agents/{id}/config` using admin or agent-scoped JWT to receive the **fully resolved key**. 

**Fixed 2026-05-22 (Credential Sync):** Previously, the SDK's `register()` method would sync the agent's configuration using the sanitized `AgentOut` model from the `/v1/agents` endpoint. This caused the `api_key` to be stripped (set to `None`) immediately after login. The SDK now explicitly calls the `/config` endpoint after registration to preserve the resolved API key.

### Secret Vault (`get-secret`) — Added 2026-05-31

Agents can access encrypted secrets at runtime via the `get_secret` tool. This keeps sensitive credentials (API keys, database passwords, tokens) **out of agent config and out of source code**.

**How it works:**
1. An admin creates a secret for an agent via the Board UI (`/agents/:id/secrets`) or `POST /v1/secrets`.
2. The secret is encrypted with AES-256-GCM and stored in PostgreSQL.
3. The agent calls `get_secret("secret_name")` during its ReAct loop.
4. Core decrypts the value on demand, returns it to the agent, and writes an audit log entry.

**Example agent usage:**
```python
# Inside an agent's ReAct turn
api_key = await get_secret("stripe_api_key")
# api_key now holds the decrypted string "sk_live_..."
```

**Benefits over `api_key` override:**
- `Agent.api_key` is a single LLM provider key stored in plaintext.
- The secret vault supports **multiple named secrets per agent** (e.g., `stripe_api_key`, `db_password`, `slack_webhook_url`).
- Values are **encrypted at rest** and **audit-logged on every read**.
- Secrets can be **rotated independently** without restarting the agent process.

**Prerequisite:** Add `get-secret` to the agent's `skills` list. The `AgentRunner` auto-registers the `get_secret` tool on startup.

### Proactive User Notifications (`notify_user`) — Added 2026-06-01

Agents can send notifications to users through the unified notification system via the `notify_user` tool. Unlike `send_message` (which delivers a chat message immediately), `notify_user` respects user preferences, quiet hours, and rate limits.

**How it works:**
1. The agent calls `notify_user(user_id, title, message, priority)` during its ReAct loop.
2. Core validates the agent's rate limit (`notif:agent_rate:{agent_id}:{user_id}` — max 20/hour).
3. Core checks the user's `NotificationPreference` (quiet hours, timezone, per-category toggles).
4. Core inserts a `Notification` row and emits `notification:new` to Board WebSockets.
5. If the user has Telegram enabled and the event is critical or outside quiet hours, Core escalates via `isli-channels`.

**Example agent usage:**
```python
# Inside an agent's ReAct turn — alert a user that their task is done
result = await notify_user(
    user_id="123456789",
    title="Task completed",
    message="Your research task on 'quantum computing' is finished.",
    priority="high",  # critical | high | normal | low
)
# Returns: {"ok": True, "notification_id": "..."}
```

**Typed exceptions for graceful ReAct recovery:**
- `NotificationRateLimitError` — Agent has sent too many notifications to this user this hour. The agent should back off or batch updates.
- `NotificationDeliveryError` — Core could not deliver the notification. The agent should log and retry later.

**Prerequisite:** Add `notify-user` to the agent's `skills` list. The `AgentRunner` auto-registers the tool on startup via `add_notification_tools()`.

**Comparison with `send_message`:**
| | `send_message` | `notify_user` |
|---|---|---|
| Channel | Telegram / WhatsApp only | in_app + Telegram |
| Respects quiet hours | ❌ No | ✅ Yes |
| Rate limited | ❌ No | ✅ Yes (20/hour per user per agent) |
| Priority levels | ❌ No | ✅ Yes (critical bypasses quiet hours) |
| Batched digests | ❌ No | ✅ Yes (low priority) |
| User preferences | ❌ No | ✅ Yes (per-category toggles) |

**Tool Description Neutralization (Fixed 2026-06-01):**
The original tool description used caution-triggering language ("unified notification system", "may escalate to Telegram", "proactive outreach"). This caused certain LLMs (e.g., Kimi K2.6) to apply a self-imposed safety protocol and refuse to execute the tool even when explicitly requested by the user.

- **Neutral description** now reads: *"Display a notification card in the user's web UI. Use this when the user asks you to send a notification, reminder, or alert."*
- **System prompt instruction** added: *"When the user asks you to send a notification, use notify_user immediately. The user's request is their approval — do not ask for additional confirmation."*

### Browser Automation (Added 2026-06-01)

Agents with browser skills can navigate websites, interact with forms, and extract structured data using Playwright-backed persistent browser sessions.

**Available Tools:**

| Tool | Purpose | Key Parameter |
|------|---------|---------------|
| `browser_navigate` | Load a URL | `url` |
| `browser_snapshot` | Get page as accessible text with `@ref` IDs | `full` (default false = interactive only) |
| `browser_click` | Click an element | `ref` (e.g., `"@e3"`) |
| `browser_type` | Type into an input | `ref`, `text`, `clear` |
| `browser_press` | Press a key | `key` (e.g., `"Enter"`) |
| `browser_scroll` | Scroll the page | `direction`, `amount` |
| `browser_back` | Go back in history | — |
| `browser_console` | Get JS console logs | `since_cursor` |
| `browser_vision` | Take a screenshot | `question` (optional) |
| `browser_get_images` | List all images | — |

**Example ReAct Turn:**
```
User: "Check the weather in Casablanca"

Agent:
  browser_navigate(url="https://weather.com")
  → {success: true, url: "https://weather.com", title: "The Weather Channel"}

  browser_snapshot()
  → {snapshot: "[1] input[text] 'Search City or Zip Code' @e1\n[2] button 'Search' @e2"}

  browser_type(ref="@e1", text="Casablanca, Morocco")
  → {success: true}

  browser_click(ref="@e2")
  → {success: true}

  browser_snapshot()
  → {snapshot: "[1] heading 'Casablanca, Morocco Weather'\n[2] div '72° F' @e3..."}

  browser_click(ref="@e3")
  → {success: true}

  browser_snapshot(full=true)
  → {snapshot: "...full page with forecast details..."}

Reply: "The weather in Casablanca is 72°F with partly cloudy skies..."
```

**Important Notes:**
- `@ref` IDs are **invalidated on every navigate/back**. Always re-snapshot after navigation.
- If a `click` or `type` returns `400 Ref not found — re-run snapshot`, the agent must call `browser_snapshot()` again.
- `browser_snapshot` default (`full=false`) returns only interactive elements. Set `full=true` for complete page content.
- `browser_vision` returns a base64 PNG — use it for CAPTCHAs or when the accessibility tree is insufficient.
- Browser sessions are **persistent per agent** (cookies, localStorage survive). Each agent gets its own browser profile.
- Max 5 concurrent browser sessions per `isli-skills` instance. If exceeded, the skill returns `503 Retry-After: 30`.

**Prerequisites:**
1. Add `web-browse-navigate` and `web-browse-snapshot` to the agent's `skills` list (minimum viable set)
2. Optionally add `web-browse-click`, `web-browse-type`, `web-browse-press` for interaction
3. Optionally add `web-browse-vision` for screenshot fallback
4. Rebuild and restart the agent-runner to compile the new SDK tools

### Session Metadata Injection (Added 2026-06-01)

The `AgentRunner` injects a `=== CURRENT SESSION ===` block into every system prompt for session-based conversations (web, Telegram, WhatsApp). This ensures the agent always knows who it is talking to and can call user-facing tools (`notify_user`, `send_message`) without asking for parameters.

```
=== CURRENT SESSION ===
User ID: 0446c690-44e4-4c3c-8975-c90145b9ecb8
Channel: web
Session ID: 0446c690-44e4-4c3c-8975-c90145b9ecb8
Use the User ID above when calling tools that require a user_id parameter.
```

**`effective_user_id` fallback:** Web channel sessions often have `user_id = NULL` in the database (the Board UI does not authenticate users with a persistent identity). In this case, the runner falls back to the `session_id` as the effective user identifier, ensuring `notify_user` always has a valid target.

### Gemini & Google Provider Hardening (Fixed 2026-05-22)

Gemini models (via LiteLLM) have specific schema requirements that differ from OpenAI/Anthropic. The `isli-agent-sdk` includes automatic hardening for Gemini:

- **Environment Fallback**: The runner explicitly sets `os.environ["GEMINI_API_KEY"]` before calling LiteLLM to ensure compatibility across all SDK versions.
- **Schema Sanitization**: Automatically strips `function_call: None` and empty `tool_calls: []` lists from message history, which previously caused 400 Bad Request errors from the Gemini API.
- **Robust Tool Arguments**: Handles cases where Gemini returns tool arguments as pre-parsed Python dictionaries instead of JSON strings, preventing `json.loads` type errors.

---

## Model Routing (Added 2026-05-31)

When `model_routing.enabled: true`, ISLI dynamically selects the best LLM for each task or session instead of hardcoding a single model per agent. This reduces costs on trivial tasks and reserves expensive models for complex reasoning.

### How It Works

1. **User configures secondary models** in the Board UI (`Agent Detail → Model Strategy`) or via `PUT /v1/agents/{id}`:
   ```json
   {
     "model_routing_enabled": true,
     "secondary_models": [
       {"provider": "openai", "model_id": "gpt-4o-mini", "cost_tier": "local"},
       {"provider": "openai", "model_id": "gpt-4o", "cost_tier": "standard"},
       {"provider": "anthropic", "model_id": "claude-opus-4-8", "cost_tier": "premium"}
     ]
   }
   ```

2. **Before each task or session**, Core runs a **hybrid A+B router** in parallel with context injection:
   - **A — Core Heuristic Scorer** (`TaskComplexityScorer.score_task_input()`): Fast, zero-cost analysis of the task description. Returns a `complexity_score` (0.0–1.0) and a `complexity_tier` (`local` | `standard` | `premium`).
   - **B — Keeper LLM Router** (`POST /model/route`): The Keeper local model reads the task description, complexity score, and the filtered model list, then returns a JSON decision: `{provider, model_id, reason}`.

3. **The routed model is locked for the task/session lifetime.** Once chosen, it is stored in `tasks.routed_model_id` or `sessions.routed_model_id`. Subsequent messages in the same session reuse the same model without re-invoking the router (session-lifetime lock).

4. **The agent runner uses the routed model** via `_model_with_fallback()`:
   - Attempt 1: Routed model (if present and valid)
   - Attempt 2: Agent's **default** model (`model.provider` / `model.model_id`) — **never skipped**
   - If both fail, the runner raises `RuntimeError` and halts (never silently falls back to an unconfigured model)

### Cost-Tier Filtering

The heuristic scorer filters the secondary_models list before sending it to the Keeper. Models whose `cost_tier` is strictly more expensive than the computed tier are dropped. This ensures the Keeper only chooses from economically appropriate candidates.

| Task Complexity | Eligible Tiers | Example |
|-----------------|----------------|---------|
| `local` (score ≤ 0.33) | `local` only | "What time is it?" → `gpt-4o-mini` |
| `standard` (score 0.34–0.66) | `local`, `standard` | "Summarize this article" → `gpt-4o` |
| `premium` (score > 0.66) | `local`, `standard`, `premium` | "Design a distributed system" → `claude-opus-4-8` |

If filtering leaves zero models (e.g., no `local` model configured), the system **fail-opens** and returns the full unfiltered list, letting the Keeper decide.

### Session-Lifetime Lock

Sessions route **once** on the first message. The chosen model is written to `sessions.routed_model_id` and never changes for the life of that session. This prevents:
- Re-routing latency on every follow-up message
- Model switching mid-conversation, which breaks context continuity
- Inconsistent tone/capability jumps

Tasks (Kanban cards) route individually because each task has independent scope and complexity.

### Board UI Integration

The `AgentDetailPage.tsx` Model Strategy card now includes:
- **Toggle switch**: Enable/disable model routing per agent
- **JSON textarea**: Edit `secondary_models` array with live validation
- **Per-model fields**: `provider`, `model_id`, `label`, `description`, `cost_tier`

### Database Schema

Added to `agents`, `tasks`, and `sessions`:
- `model_routing_enabled` (boolean) on `agents`
- `secondary_models` (JSON) on `agents`
- `complexity_score`, `complexity_tier` on `tasks` and `sessions`
- `routed_model_provider`, `routed_model_id`, `routed_model_reason` on `tasks` and `sessions`

### Prompts

The Keeper uses the `keeper:model_router` prompt template from `prompts.yaml`. It receives:
- `{task_description}` — the raw user message or task input
- `{complexity_score}` and `{complexity_tier}` — from the heuristic scorer
- `{model_list}` — prose-formatted filtered secondary models (numbered lines)
- `{default_model}` — the agent's default model for fallback reference

The prompt instructs the Keeper to return a JSON block with `provider`, `model_id`, and `reason`. If the Keeper returns invalid JSON or an unknown model, the system falls back to the agent's default model.

---

## PII De-Identification Mesh (Added 2026-06-07)

Agents can optionally run with **PII Mesh** enabled. When ON, the agent runner anonymizes sensitive data before sending it to the cloud LLM, then re-hydrates the LLM response locally before delivery.

### How It Works

1. **Pre-turn anonymization** (`_prepare_llm_payload()`):
   - The agent receives `token_map` in the `session:message` or `task:updated` WebSocket event.
   - If `pii_mesh_enabled` is true, the runner calls `PIIKeeperClient.session_prep()` which:
     - Runs a fast regex pre-filter (`regex_hits()`) for emails, phones, SSNs, credit cards, DOBs, corp IDs.
     - If regex hits exist (or `pii_use_slm` is true), calls Keeper `POST /session-prep` for SLM-validated entity extraction.
   - The returned `scrubbed_context_summary` and `scrubbed_messages` replace the originals before the LLM call.

2. **Local re-hydration** (`_post_process_response()`):
   - After the LLM returns its response, the runner calls `PIIKeeperClient.rehydrate_local(text, session_id)`.
   - This is a pure in-memory `str.replace` loop over the cached token_map — zero network latency.
   - Tokens are sorted by length (descending) to avoid partial replacements.

3. **Defense-in-depth in Core** (`reply_to_session`):
   - Core runs a final regex scan on the outgoing text for stray `{{PII:...}}` tokens.
   - If any remain, it calls `POST /session-prep/rehydrate` on Keeper as a fallback.
   - If tokens still remain after fallback, it logs CRITICAL and delivers the text anyway (better to leak a token placeholder than silently drop the message).

### Agent Configuration

Two new fields in `Agent.config` JSONB:

```json
{
  "pii_mesh_enabled": true,
  "pii_use_slm": false
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `pii_mesh_enabled` | `boolean` | `false` | Master toggle for PII anonymization/re-hydration |
| `pii_use_slm` | `boolean` | `false` | When true, Keeper runs SLM inference for detection; when false, only regex pre-filter |

### Board UI Integration

The `AgentDetailPage.tsx` Model Strategy card now includes:
- **PII Mesh toggle switch**: Enable/disable per agent
- **Use Keeper SLM sub-toggle**: Appears only when PII Mesh is ON
- **Save/Discard bar**: Dirty detection follows the same per-section pattern as Model Routing

### Environment Variables

Added to `docker-compose.yml` for the `core` service:
- `PII_MESH_DEFAULT_ENABLED`
- `PII_USE_SLM_DEFAULT`
- `PII_REGEX_PRE_FILTER`
- `PII_TOKEN_TTL_HOURS`

Added to `agent-runner` service:
- `KEEPER_URL=http://keeper:8001`

### SDK Integration

```python
# AgentRunner.__init__
self._pii_client = PIIKeeperClient(keeper_url=os.getenv("KEEPER_URL"))
self._session_token_maps: dict[str, dict[str, str]] = {}

# On session:message event
if payload.get("token_map"):
    self._pii_client.cache_token_map(session_id, payload["token_map"])

# Before LLM call
system_prompt, messages = await self._prepare_llm_payload(system_prompt, messages, session_id)

# After LLM call
final_text = await self._post_process_response(final_text, session_id)
```

---

## Dynamic Skill & Configuration Sync (Added 2026-05-24)

Agents now support real-time configuration updates without requiring a process restart. This allows users to add/remove skills or modify personas via the Board UI and have those changes take effect immediately.

### How it Works
1. **Event Trigger**: When an agent's properties (skills, persona, model, etc.) are updated via `PUT /v1/agents/{id}`, the Core API emits an `agent:config_updated` event to Redis.
2. **WebSocket Routing**: The Core WebSocket gateway (`ws.py`) listens for these events and routes them to the specific agent's open WebSocket connection.
3. **SDK Sync**: The `AgentRunner` in the SDK receives the event and:
   - Re-authenticates and fetches the fresh configuration from the `/config` endpoint.
   - Clears its internal tool registry.
   - Re-registers tools based on the new skills list.
   - Re-assembles the system prompt template for the next interaction.

This ensures that the agent's "capabilities" are always in sync with the state defined on the Board.

---

## Tool Result Stashing (UI Components)

Agents that have the `ui-components` skill can render interactive React components inline in the chat stream. The runner uses a **tool result stashing pattern** for this:

1. During a ReAct turn, the LLM calls the `ui_components` tool with component props.
2. The runner executes the tool and **stashes the result dict** in `self._pending_components`.
3. A clean confirmation string is injected as the tool result so the LLM knows it succeeded.
4. After the final LLM response (no more tool calls), the runner sends all stashed components alongside the text reply via `reply_to_session(session_id, text, components=[...])`.

This avoids fragile text scanning — the runner never needs to parse JSON out of the LLM's prose output. See [`Docs/13-immersive-chat-ui.md`](./13-immersive-chat-ui.md) for full details.

---

## Tool Call Format Fallbacks (Added 2026-05-29)

Not all models output tool calls using the OpenAI-compatible `message.tool_calls` array. Local models via Ollama (especially Qwen 2.5) and some Anthropic-trained models embed tool calls inside the message `content` as raw text. The `AgentRunner` includes a **three-tier fallback parser** that activates when `message.tool_calls` is empty:

### Tier 1 — OpenAI Structured (`tool_calls` array)

**Primary path.** Used by OpenAI, Claude via Anthropic API, and Gemini via LiteLLM. The LLM returns a structured array of `ToolCall` objects with `id`, `function.name`, and `function.arguments`.

### Tier 2 — Anthropic-Style XML (`<function_calls>`)

**Fallback for Qwen and other Anthropic-trained models.** When `tool_calls` is empty, the runner scans `message.content` for `<function_calls>` blocks:

```xml
<function_calls>
  <invoke name="ui_components">
    <arg name="component_type">card</arg>
    <arg name="props">{"title":"Demo"}</arg>
    <arg name="action_id">demo_001</arg>
  </invoke>
</function_calls>
```

The runner uses `xml.etree.ElementTree` to parse each `<invoke>`, JSON-decode argument values, and convert them into synthetic `_ParsedToolCall` objects that mimic the OpenAI interface. The XML block is stripped from the final response text before delivery.

### Tier 3 — JSON-in-Text Blob (`{"name":..., "arguments":...}`)

**Fallback for models that output raw JSON objects inline.** When neither structured `tool_calls` nor XML is found, the runner performs brace-matching on `message.content` to find top-level JSON objects:

```json
{"name":"ui_components","arguments":{"component_type":"card","action_id":"demo_001"}}
```

A JSON blob is accepted as a tool call only if it:
1. Is a valid JSON object (`dict`)
2. Has both `"name"` and `"arguments"` keys
3. `"arguments"` is itself a `dict`
4. `"name"` matches a **registered tool** in `self.tools`

This prevents ordinary JSON prose (e.g., a code example or data payload) from being misinterpreted as a tool call.

### Tier 4 — Legacy `<tool_call>` Markup (`<tool_call><function=...>`)

**Fallback for Ollama models (e.g., Kimi K2.6) that hallucinate their own tool-calling syntax.** When none of the above formats are found, the runner scans `message.content` for `<tool_call>` blocks:

```xml
<tool_call>
<function=ui_components>
<parameter=component_type>card</parameter>
<parameter=action_id>demo_001</parameter>
</function>
</tool_call>
```

Two variants are supported:
- **Attribute style:** `<function name="ui_components">` / `<parameter name="component_type">`
- **Inline style:** `<function=ui_components>` / `<parameter=component_type>`

Parameter values may span multiple lines. JSON values inside parameters are auto-parsed. The parser uses regex (not `xml.etree.ElementTree`) because the markup is not valid XML (`=` in tag names).

Only tools registered in `self.tools` are extracted. Unrecognized tool names are silently skipped.

### Stripping & History Cleanup

When any fallback (XML, JSON, or Legacy) is triggered, the runner:
- Removes the markup from `message.content` before sending the final reply to the user
- Injects synthetic `tool_calls` into the conversation history `msg_dict` so LiteLLM replay remains valid
- Logs the extraction at `debug` level for observability

### Supported Patterns

| Model Family | Format Detected | Fallback Used |
|--------------|----------------|---------------|
| GPT-4, Claude API, Gemini | `message.tool_calls[]` | Tier 1 (native) |
| Qwen 2.5 via Ollama | `<function_calls>` XML | Tier 2 |
| Qwen 2.5 via Ollama (variant) | Raw JSON blob in text | Tier 3 |
| Kimi K2.6 via Ollama | `<tool_call>` markup | Tier 4 |
| Llama 3.1 via Ollama | `message.tool_calls[]` | Tier 1 (native) |

> **Note:** The XML fallback requires `xml.etree.ElementTree` (stdlib). The JSON and Legacy fallbacks require no extra dependencies. All are backward-compatible — agents using Tier 1 models are unaffected.

---

## Agent Process Manager

In order to simplify deployment and management, `isli-core` includes an embedded **Agent Process Manager**. This service is responsible for spawning, monitoring, and terminating agent containers (Docker mode) or Python processes (native mode).

### Capabilities
- **Auto-Start**: New agents are automatically spawned upon creation (if `auto_start=true`).
- **Lifecycle Control**: Start, Stop, **Restart**, and **Rebuild & Restart** agents via the Board UI or API.
- **Health Monitoring**: Detects container/process crashes and tracks crash counts.
- **Log Aggregation**: Captures agent stdout/stderr and routes it to `isli-core` logs and Redis for live streaming.
- **Image Rebuild**: Rebuilds the `isli-agent-runner:latest` image from the host build context (`AGENT_RUNNER_BUILD_CONTEXT`) in the background when **Rebuild & Restart** is triggered.

### Configuration
| Variable | Purpose |
|----------|---------|
| `AGENT_RUNNER_IMAGE` | Docker image tag used for spawned agent containers (default: `isli-agent-runner:latest`) |
| `AGENT_SDK_HOST_PATH` | Absolute host path to `isli-agent-sdk/src` for live volume mount in dev mode |
| `AGENT_RUNNER_BUILD_CONTEXT` | Absolute host path to `isli-agent-sdk` root for Docker image rebuilds |
| `AGENT_NETWORK` | Docker network name for agent containers (default: `isli_isli-mesh`). **Must be a network that Core itself is attached to** — otherwise spawned agents cannot resolve `core:8000`. |

### Docker Network Requirements (Fixed 2026-06-03)

When running under Docker Compose, the spawned agent containers must share a network with `isli-core` or they will fail with `[Errno -2] Name or service not known` on every heartbeat and WebSocket reconnect.

**Compose default networks:**
- `isli-public` — Traefik + Board only (no Core)
- `isli-mesh` — Core, Keeper, Skills, Channels, Workspace, Audio, Agents, Board
- `isli-data` — Internal only (no external access); Postgres, Redis, Ollama

**Correct configuration:**
1. Core must be on `isli-mesh` (so agents can resolve `core:8000`).
2. Board must also be on `isli-mesh` (so its nginx `proxy_pass` to `core:8000` works).
3. `AGENT_NETWORK` must be set to the same network Core is on (`isli_isli-mesh` by default).

**Verification:**
```bash
# From inside the board container
docker compose exec board getent hosts core
# Expected: 172.20.0.x  core

# From inside a spawned agent container
docker exec isli-agent-<id> getent hosts core
# Expected: 172.20.0.x  core
```

**Common mistake:** If `AGENT_NETWORK` points to `isli_isli` (Compose's implicit default network) but Core is not attached to it, agents will be orphaned. They will boot, register, then enter an infinite retry loop because `core:8000` is unresolvable from their container.

---

## WebSocket Library Compatibility (Fixed 2026-06-03)

The `isli-agent-sdk` uses `websockets` to connect to Core's WebSocket gateway. In `websockets` 14+, the parameter name for extra headers changed from `extra_headers` to `additional_headers`.

**Error signature (websockets ≥14 with old code):**
```
BaseEventLoop.create_connection() got an unexpected keyword argument 'extra_headers'
```

**Fix:** In `isli-agent-sdk/src/isli_agent/runner.py`, change:
```python
# BEFORE (websockets <14)
async with websockets.connect(
    ws_url,
    extra_headers={"Authorization": f"Bearer {token}"},
) as websocket:

# AFTER (websockets ≥14)
async with websockets.connect(
    ws_url,
    additional_headers={"Authorization": f"Bearer {token}"},
) as websocket:
```

After changing the source, rebuild the agent-runner image:
```bash
docker compose build agent-runner
```

Then restart every agent via the Board UI or API so they pick up the new image.

---

## Agent Registration Flow

```
1. User creates agent via Board UI (POST /v1/agents)
2. Core API saves agent record (status: "registered")
3. Core API (Process Manager) spawns container: isli-agent-{agent_id}
4. Agent status becomes "starting"
5. Agent process initializes, fetches config, and opens WebSocket
6. First heartbeat arrives → status becomes "online"
7. Kanban board shows agent card as ONLINE
```

### Restart Flow
```
1. User clicks "Restart Agent" in Board UI
2. POST /v1/agents/{id}/restart (rebuild=false)
3. Core API stops existing container, removes it
4. Core API spawns a new container from the existing image
5. Status → "starting" → "online"
```

### Rebuild & Restart Flow
```
1. User clicks "Rebuild & Restart" in Board UI
2. POST /v1/agents/{id}/restart?rebuild=true
3. Core API stops existing container, sets status → "rebuilding"
4. Background task rebuilds agent-runner image from AGENT_RUNNER_BUILD_CONTEXT
5. On success: spawns new container; status → "starting" → "online"
6. On failure: status → "stopped" with reason logged
```

---

## Agent Turn Execution

When a task is assigned to an agent:

### Task Path (Zero HTTP)

The `task:updated` WebSocket event carries `context_summary` inline in the payload. The agent SDK reads it directly — no HTTP round-trips to Core.

```python
async def _execute_task(self, task_data: dict):
    task_id = task_data["id"]
    # context_summary delivered inline via WebSocket — no get_context() HTTP call
    context_summary = task_data.get("context_summary") or ""
    system_prompt = self._assemble_system_prompt(context_summary)
    messages = [{"role": "user", "content": task_data.get("input", "")}]
    # ... ReAct loop continues
```

> **Deprecated:** `client.get_context()` is deprecated and should not be called from new code.

### Session Path

The `session:message` WebSocket event carries `context_summary` inline, same as tasks.

```python
async def _execute_session_message(self, payload: dict):
    context_summary = payload.get("context_summary") or ""
    system_prompt = self._assemble_system_prompt(context_summary, session_info=payload)
    # ... ReAct loop continues
```

### Prompt Assembly

```python
# Simplified agent SDK prompt assembly
def _assemble_system_prompt(self, context_summary: str, session_info: dict | None = None) -> str:
    from isli_agent.prompts_loader import get_prompts
    template = get_prompts()["agent"]["system_prompt_template"]

    persona_line = f"Persona: {self.config.persona}\n" if self.config.persona else ""
    tools_list = "\n".join(
        f"- {d.get('function', {}).get('name', 'unknown')}: "
        f"{d.get('function', {}).get('description', 'No description.')}""
        for d in self.tool_definitions
    )

    return template.format(
        name=self.config.name,
        description=self.config.description or "No description provided.",
        persona_line=persona_line,
        tools_list=tools_list,
        context_summary=context_summary,
        context_timestamp=datetime.now(timezone.utc).isoformat()
    )
```

### Protocol Constraints & Decision Logic (Tiered Prompting)

To enforce the Shared Blackboard architecture, all agents are injected with mandatory **Protocol Constraints** and **Decision Logic** in their system prompt.

#### 1. Protocol Constraints
Agents are strictly forbidden from direct communication.
- **Shared Blackboard**: All coordination must happen via the Kanban.
- **Halt on Approval**: If a task is flagged `needs_human_approval: true`, the agent MUST halt, surface its state, and wait for human review in the **Review** column.

#### 2. Decision Logic
Before acting, agents run a 4-branch internal check:
1. **Full capability** → Proceed autonomously.
2. **Partial capability** → Execute known portion, create Kanban task for the remainder.
3. **No capability / High-risk** → Do NOT attempt; create a Kanban task immediately.
4. **Approval Gate** → HALT and surface state.

#### 3. Context Freshness
The `{context_timestamp}` is injected every turn to allow agents to detect stale memory or infrastructure-level latency, closing the gap between the last Keeper summary and the current system time.

---

### Task-Mode Execution Block (Added 2026-06-14)

When an agent is executing a Kanban task (the `_execute_task` path), the SDK injects an additional `agent.task_execution_block` from `prompts.yaml` into the system prompt. Session/chat messages do **not** receive this block.

**Purpose:** Prevent agents from returning greeting/status cards or marking tasks done without performing the requested work. The block instructs the model to:

1. Treat the task title and description as a work order.
2. Call the relevant skills/tools to execute the work.
3. Write file deliverables via `file-write`, `shared_file_write`, `shared_promote_file_workspace`, or `promote_output` before completing.
4. Use the final non-tool text as the task result.
5. Never use `ui_components`, `send_message`, or `notify_user` as a substitute for doing the work.

**SDK implementation:**

```python
def _assemble_system_prompt(
    self,
    context_summary: str,
    session_info: dict | None = None,
    relevant_skills: list[str] | None = None,
    task_mode: bool = False,
) -> str:
    # ... base template rendered as before ...
    if task_mode:
        block = prompts.get("agent", {}).get("task_execution_block")
        if block:
            system_prompt += "\n\n" + block
```

- `_execute_task()` calls `_assemble_system_prompt(..., task_mode=True)`.
- `_execute_session_message()` uses the default `task_mode=False`.

> **Note:** The `task_execution_block` is mounted via `prompts.yaml`, but the SDK code that applies it is baked into the `isli-agent-runner` image. After editing the block, restart the agent-runner and recreate agent containers; after changing the injection logic, rebuild the agent-runner image.

### Prompt Configuration (`prompts.yaml`)

The agent system prompt template and all 15 tool descriptions are loaded from `prompts.yaml` at runtime. The file is mounted as a volume on the `agent-runner` container, so you can tune prompts without rebuilding (the SDK must still be restarted/reloaded to clear its `lru_cache`).

**Agent keys you can override:**

| Key | Description |
|-----|-------------|
| `agent.system_prompt_template` | Full system prompt with `{name}`, `{description}`, `{persona_line}`, `{tools_list}`, `{context_summary}` |
| `agent.tool_descriptions.*` | LiteLLM function `description` for each tool (e.g., `file_read`, `web_search`, `memory_save`) |
| `agent.task_execution_block` | Extra rules injected only during Kanban task execution (see above) |

---

## The Keeper Role in Agent Turns

```
Before turn:  Keeper.context_inject()  → enriches agent prompt
During turn:  Agent runs independently  → Keeper uninvolved
After turn:   Journal/MemoryWorker     → asynchronous Tier 2 memory extraction (cursor-backed polling)
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

## Agent Peer Awareness (Added 2026-06-01)

Agents do not automatically know about every other agent in the system. Instead, each agent has an explicit **delegation target list** (`known_agent_ids`) that the operator configures via the Board UI.

### Why Asymmetric?

If Agent A knows Agent B, it does **not** mean B knows A. This is intentional:
- **Directional delegation** — A can assign tasks to B, but B has no reason to delegate back to A unless the operator explicitly enables it.
- **Least privilege** — Agents only see peers they might actually need to collaborate with.
- **Prevents surprise loops** — An agent cannot be pulled into a delegation chain by a peer it doesn't know about.

### Data Model

```python
class Agent:
    id: str
    name: str
    description: str | None
    persona: str | None
    picture: str | None         # UUID of the blob in Redis (DB 10)
    known_agent_ids: list[str]   # JSON column; default []
```

- Stored as a JSON array of agent IDs on the `agents` table (same pattern as `channels` and `skills`).
- Updated via `PUT /v1/agents/{id}` with `{"known_agent_ids": ["agent-b", "agent-c"]}`.
- Emits `agent:config_updated` when changed so the runner can refresh context.

### Board UI

The `AgentDetailPage` includes a card titled **"Agents this agent can delegate to"**:
- Toggle pills for every other agent (self excluded).
- Each pill shows: status dot (green/yellow/grey) + agent name + model.
- Dirty detection, Save/Discard bar — follows the same per-section pattern as Model Strategy and Channels.

### Runtime Discovery

Agents query their peers at runtime via the SDK or directly against Core:

```
GET /v1/agents/{agent_id}/peers
→ Returns list[AgentOut] with full metadata for each known agent
```

This endpoint resolves `known_agent_ids` into name, description, skills, status, and model — everything an agent needs to decide "who should I delegate this to?"

### Integration with Keeper Context Injection (Future)

A planned enhancement will pre-inject a compact peer summary into the agent's system prompt when `known_agent_ids` is non-empty:

```
--- Available Peers ---
• agent-research (Research Assistant) — web research, summarization
• agent-code (Code Reviewer) — git diff analysis, linting
```

This eliminates an extra tool-call roundtrip for the common delegation case.

---

## Agent Permissions Model

Agents operate under a capability-scoped permission system enforced by Core API:

| Permission | Description |
|-----------|-------------|
| `tasks:read` | Read tasks from Kanban |
| `tasks:create` | Create new tasks (delegation via `create-kanban-task`) |
| `tasks:update:own` | Update own task status/output |
| `memory:read:own` | Read own agent memory |
| `memory:write:own` | Write to own agent memory |
| `skills:invoke` | Call skills via proxy |
| `channels:send` | Send messages via assigned channels |
| `agents:list` | See other registered agents |
| `agents:read:peers` | Resolve own `known_agent_ids` into full metadata |

Agents cannot read each other's memory, read each other's task details, or impersonate other agents.

### Software Engineering Workflows (Added 2026-05-24)

Agents can now leverage specialized Software Engineering skills to improve implementation reliability:
- **`create-engineering-plan`**: Agents are encouraged to call this skill before starting complex tasks to generate a `PLAN.md` in their workspace. This mimics the "plan-first" philosophy of high-end frameworks.

---

## Adding a New Agent

### Method 1: Board UI / API (Recommended)

Create the agent via the Board UI or `POST /v1/agents`, then start it with **Start Agent**. The Core API's Process Manager dynamically spawns a dedicated Docker container (`isli-agent-{agent_id}`) from the `isli-agent-runner:latest` image.

In development, the live SDK mount makes `isli-agent-sdk/src` code changes immediate — use **Restart Agent** to pick them up. Use **Rebuild & Restart** after changing `requirements.txt`, `Dockerfile`, or when you need a completely clean image.

### Method 2: Docker Compose Profile (Legacy)

The `agent-runner` service exists in `docker-compose.yml` as a **build target** (`replicas: 0`, `command: ["true"]`). It is not a long-running service; Core spawns containers from this image at runtime.

```bash
# Ensure the image is up to date
docker compose build agent-runner

# The image is referenced by Core when spawning agents dynamically
```

The `agent-runner` service:
- Serves as the Docker build target for the agent-runner image
- Does NOT auto-start with the core stack (`deploy.replicas: 0`)
- Core's Process Manager uses `AGENT_RUNNER_IMAGE` to spawn individual agent containers

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
from isli_agent.tools.audio import speech_to_text, SPEECH_TO_TEXT_DEF

runner = AgentRunner(config, core_url)
runner.add_workspace_tools()   # file_read, file_write, file_list, file_delete
runner.add_channel_tools()     # send_message
runner.add_audio_tools()     # speech_to_text, text_to_speech
runner.add_tool("my_custom", my_func, MY_CUSTOM_DEF)
```

### Runtime Dependency Injection

Tools that need `agent_id` or `core_client` receive them automatically at invocation time — the LLM only sees user-facing parameters. For example, `send_message` has this signature:

```python
async def send_message(agent_id: str, channel: str, channel_user_id: str, text: str, core_client: CoreClient)
```

But the LLM tool definition only exposes `channel`, `channel_user_id`, and `text`. The `AgentRunner._execute_tool()` inspects the function signature and injects `agent_id` and `core_client` before calling the function. This keeps tool definitions clean while the runner handles the plumbing.

### Per-Turn Tool Filtering (Added 2026-06-11)

To reduce token waste, the agent runner does **not** send the full tool definitions to the LLM on every turn. Instead, it filters the toolbox dynamically based on the Keeper's intent classification.

**How it works:**
1. Before each turn, Core asks the Keeper which skills are relevant to the user's message.
2. The `AgentRunner` receives `relevant_skills` via WebSocket event payload.
3. At the start of `_execute_task` / `_execute_session_message`, the runner resets `_active_tool_definitions` to the relevant subset.
4. Only tools matching `relevant_skills` + tools marked `x_isli_always_active: true` are sent to the LLM.

**Dynamic expansion:**
If the agent calls `discover_skills`, the runner expands `_active_tool_definitions` to the **full** set for the **next** turn only. After that turn, filtering resets automatically. This gives agents on-demand access to their complete toolbox without permanently bloating the context window.

**`x_isli_always_active` flag:**
Tool definitions can include `"x_isli_always_active": true` to remain visible regardless of intent classification. Currently used for:
- `get_current_datetime` — agents often need timestamps
- `discover_skills` — agents must always be able to discover their toolbox

**Always-visible tools are configurable** — any tool definition can opt in by setting the flag.

### Tool Injection Strategy (Added 2026-06-13)

Agents can override the default per-turn filtering behavior via a new `tool_injection_strategy` field in `Agent.config`:

```json
{
  "tool_injection_strategy": "auto"
}
```

| Strategy | Behavior |
|----------|----------|
| `auto` (default) | Filter by `relevant_skills`; fall back to the full set when Keeper returns empty/none. |
| `all` | Skip Keeper filtering entirely; always send the full registered tool set. |
| `strict` | Only send tools matching `relevant_skills`. If Keeper returns empty, only `x_isli_always_active` tools survive. |

**Why three modes?**
- **Coding agents** with many workspace/browser tools often need their full toolkit visible to plan multi-step operations.
- **Chat-only agents** with 20+ skills benefit from strict filtering to reduce token waste and prevent the LLM from hallucinating irrelevant tool calls.
- **Auto** preserves the existing behavior: filtered most of the time, with a safety fallback when classification fails.

**Configuration:**
- Set per-agent via Board UI (`Agent Detail → Model Strategy → Tool Injection Strategy` dropdown).
- Validated by Core's `AgentUpdate` Pydantic model; invalid values default to `"auto"`.
- Hot-reloads automatically: changing the setting triggers `agent:config_updated`, the runner re-syncs config, and the next turn uses the new strategy.

**SDK Implementation:**
The `AgentRunner._filter_tools_by_relevance()` method reads `self.config.config.get("tool_injection_strategy", "auto")` and branches:

```python
strategy = self.config.config.get("tool_injection_strategy", "auto")
all_defs = getattr(self, "_all_tool_definitions", None) or self.tool_definitions

if strategy == "all":
    return all_defs
if strategy == "auto" and not relevant_skills:
    return all_defs
# strict or auto with skills → apply filtering
```

- `structlog` emits `runner.tools_filtered` with `strategy`, `active_count`, and `total_count` for observability.
- No database migration required — the setting lives in the existing `config` JSONB blob.

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

### Shared Workspace Tools

Agents that are members of a shared workspace can access it via additional SDK tools. Most use `scope="shared"` and `scope_id={workspace_id}` under the hood:

| Tool | Description | Required Skill |
|------|-------------|----------------|
| `shared_file_read` | Read a file from a shared workspace | `shared-file-read` |
| `shared_file_write` | Write a file to a shared workspace | `shared-file-write` |
| `shared_file_list` | List files in a shared workspace | `shared-file-list` |
| `shared_file_delete` | Delete a file from a shared workspace | `shared-file-delete` |
| `shared_file_move` | Move/rename a file within or between shared workspaces | `shared-file-move` |
| `shared_workspace_info` | Return workspace metadata (name, members, quota, root path) | `shared-workspace-info` |
| `shared_workspace_search` | Search file names and/or contents across a shared workspace | `shared-workspace-search` |
| `shared_promote_file_workspace` | Copy a file from the agent's own workspace into a shared workspace | `shared-promote-file-workspace` |
| `promote_output` | Copy/move a file from a task attachment into a shared workspace | `promote-output` |

**Registration:**

```python
runner.add_shared_workspace_tools()  # all eight shared workspace tools
```

**Typed exceptions:**
- `WorkspaceNotFoundError` — workspace does not exist or agent is not a member.
- `WorkspacePathError` — path traversal attempt, invalid path, or access denied.
- `WorkspaceQuotaError` — write would exceed the workspace's `quota_bytes`.

**Promote paths:**
- **Agent workspace → shared workspace:** call `shared_promote_file_workspace(agent_id, workspace_id, source_path, target_path)`.
- **Task attachment → shared workspace:** call `promote_output(agent_id, task_id, file_path, workspace_id)`. This is useful when a delegated Kanban task produces a deliverable that should become a permanent project asset.

In both cases Core verifies the agent is a workspace member before proxying to the workspace service.

### Token Recovery and Revocation

When an agent already exists, `POST /v1/agents` returns 409. The SDK automatically calls `POST /v1/agents/{id}/token` with admin auth to recover a fresh token. This endpoint sets `agent.token_issued_at`, which invalidates any previous tokens via `require_internal_auth`. Old tokens become unusable the moment a new one is issued.

**Security benefit:** If an admin key leaks, recovering a new token for an agent automatically revokes all previous tokens for that agent.

**Important implementation detail (fixed 2026-05-18):** The heartbeat endpoint must update `token_issued_at` **after** all side effects complete and the new token is guaranteed to be returned. If revocation is committed before the response is sent, a failure in `AuditWriter`, telemetry, or event emission leaves the agent with a revoked token and no replacement — causing a permanent 401 lockout.

**Task API auth note (fixed 2026-05-18):** Task mutation endpoints (`PUT /tasks/{id}`, `POST /tasks/{id}/move`, `POST /tasks/{id}/checkpoint`) require the admin API key, not the agent JWT. The agent SDK uses `use_admin=True` when calling these endpoints from `complete_task()`, `move_task()`, and `save_checkpoint()`.

---

## Streaming Modes (Added 2026-05-31)

Agents now support **live response streaming** across all channels (Web, Telegram, WhatsApp). Instead of silent batch processing (send → context injection → nothing → full response), the agent emits structured events during its turn. These events flow agent → Core → Board via the existing bidirectional WebSocket, or agent → Core → channel adapter for external channels.

### Mode Taxonomy

| Mode | Key | Events Emitted | UX |
|------|-----|----------------|-----|
| **Silent** | `silent` | None | Final text delivered at once (legacy behavior) |
| **Live Text** | `text` | `turn_start`, `token_delta`, `draft_complete`, `turn_end`, `cost_report` | Text appears word-by-word with a blinking cursor |
| **Live + Tools** | `tools` | `text` events + `tool_call` + `phase_start`, `phase_end` (llm_inference) | Skill cards appear above the text stream; "THINKING..." pulses per turn |
| **Process Trace** | `trace` | All `tools` events + `phase_start`, `phase_end` for context_inject/checkpoint/llm_inference | Collapsible timeline pane shows full execution trace |
| **Debug** | `debug` | All Mode C events + `debug_prompt`, `debug_response` | Same as trace + raw prompt/response previews (admin-only) |

**Default:** `silent` — existing agents behave exactly as before until explicitly reconfigured.

### Agent Configuration

Three new fields in `Agent.config` JSONB:

```json
{
  "streaming_mode": "text",
  "stream_chunk_size": 5,
  "stream_delay_ms": 20
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `streaming_mode` | `string` | `"silent"` | One of `silent`, `text`, `tools`, `trace`, `debug` |
| `stream_chunk_size` | `int` | `5` | Characters per chunk when revealing text |
| `stream_delay_ms` | `int` | `20` | Milliseconds between chunks |

Validation (Pydantic in `agents.py`):
- `streaming_mode` must be in the allowed set
- `stream_chunk_size` clamped to `1–100`
- `stream_delay_ms` clamped to `0–5000`

### Per-Session Override

A session can override the agent's default streaming mode for one-off debugging:

```json
POST /v1/sessions/{id}/message
{
  "text": "...",
  "metadata": { "streaming_mode": "debug" }
}
```

The override is stored in the session's `session_metadata` JSONB column and takes precedence over the agent config for that session only.

### Event Types

The `AgentRunner` instruments both `_execute_session_message()` and `_execute_task()` with these hooks:

| Event | When | Payload |
|-------|------|---------|
| `phase_start` | Before context injection, checkpoint recovery, **or LLM inference** | `{phase: "context_inject"}` / `{phase: "llm_inference", label: "THINKING...", turn: 1}` |
| `phase_end` | After context injection/checkpoint/**LLM inference** completes | `{phase: "context_inject", duration_ms: 1200}` / `{phase: "llm_inference", turn: 1}` |
| `turn_start` | Before each LLM turn | `{turn_number: 1, model: "...", estimated_tokens: 512}` |
| `tool_call` | Before/after each tool execution | `{tool: "file_read", status: "started"}` / `{status: "done", duration_ms: 45}` |
| `token_delta` | After each streamed text chunk | `{delta: " chunk"}` |
| `draft_complete` | After full response assembled | `{}` |
| `turn_end` | After a ReAct turn completes | `{turn_number: 1}` |
| `cost_report` | After LiteLLM usage extracted | `{input_tokens: 124, output_tokens: 89, model: "claude-sonnet-4-6"}` |
| `debug_prompt` | Before LLM call (debug mode only) | `{prompt_preview: "...", token_count: 512}` |
| `debug_response` | After LLM response (debug mode only) | `{response_preview: "...", token_count: 256}` |

**Important:** `debug_prompt` and `debug_response` are **never broadcast over WebSocket**. They are stored in a Redis list (`session:{id}:debug_trace`) and exposed via an admin-only REST endpoint `GET /v1/sessions/{id}/debug-trace`. This prevents prompt injection data exposure through the public event bus.

### Graceful Degradation

Every `_emit_stream_event()` call is wrapped in a broad `try/except` that logs a warning and swallows the exception. Streaming failures never crash the agent or delay the final response. The draft text is also persisted to Redis (`session:{id}:draft`) so Board clients reconnecting mid-stream can recover the partial response.

### Architecture

```
Agent ReAct loop (per turn)
  ├─ _emit_stream_event("phase_start", {phase: "context_inject"})
  ├─ Keeper context injection
  ├─ _emit_stream_event("phase_end", {phase: "context_inject", duration_ms: ...})
  ├─ _emit_stream_event("turn_start", {turn_number: N, ...})
  ├─ _emit_stream_event("phase_start", {phase: "llm_inference", label: "THINKING...", turn: N})
  ├─ LLM call (blocking acompletion)
  ├─ _emit_stream_event("phase_end", {phase: "llm_inference", turn: N})
  │   ├─ _emit_stream_event("tool_call", {tool: "...", status: "started"})
  │   ├─ Skill execution
  │   └─ _emit_stream_event("tool_call", {tool: "...", status: "done", duration_ms: ...})
  ├─ _stream_text() → chunks text per config, emits "token_delta" + "draft_complete"
  ├─ _emit_stream_event("cost_report", {...})
  ├─ _emit_stream_event("turn_end", {turn_number: N})
  └─ reply_to_session(text, ...)
     └─ finally: _notify_core_session_ready() → POST /v1/sessions/{id}/status → "ready"

Agent WS loop
  ├─ outgoing_queue accumulates events
  └─ _drain_outgoing_queue() sends "agent:stream_event" frames to Core

Core WS gateway
  ├─ Receives "agent:stream_event"
  ├─ Appends token_delta to Redis draft
  ├─ Stores debug_prompt/debug_response in Redis trace list
  └─ Fans out everything else as "session:stream_event" to Board WebSockets

Board UI
  ├─ StreamingMessageBubble.tsx — monospace text + blinking cursor
  ├─ ToolCallBar.tsx / ToolCallCard.tsx — spinner→checkmark transition
  └─ ProcessTracePane.tsx — collapsible timeline
```

### Session Status Lifecycle (2026-06-12)

The session status field drives the Board UI's loading indicators and streaming state. The lifecycle is:

```
User sends message
    ↓
sess.status = "pending_context"           → UI: INJECTING_CONTEXT...
    ↓
ContextWorker finishes injection
    ↓
sess.status = "agent_processing"        → UI: PROCESSING...
    ↓
session:message event → Agent ReAct loop starts
    ↓
phase_start {phase: "llm_inference"}      → UI: THINKING...
    ↓
Agent finishes → reply_to_session()
    ↓
Core reply endpoint sets status = "ready" → UI clears streaming state
```

**`agent_processing`** (added 2026-06-12) is an intermediate status set by `ContextWorker` immediately after context injection succeeds. It prevents the "blank gap" between "INJECTING_CONTEXT..." and the agent's first `phase_start` heartbeat (which can be 2–5 seconds on cold Ollama starts). The Board UI maps `agent_processing` → `PROCESSING...`, then quickly overrides it to `THINKING...` when the `llm_inference` heartbeat arrives.

**Explicit `ready` reset:** The `AgentRunner` wraps the entire session execution path in a `try/finally` that calls `_notify_core_session_ready(session_id)`. This POSTs to Core's new `POST /v1/sessions/{id}/status` endpoint to flip the status back to `ready` **even if the agent crashes, times out, or hits max turns**. Without this, sessions could get stuck in `agent_processing` forever.

**DB safety:** `Session.status` is a plain `String(32)` column — no PostgreSQL enum or CHECK constraint. Adding `agent_processing` requires zero migrations.

### Board UI Integration

The `AgentDetailPage.tsx` Model Strategy card includes a **Streaming Mode** `<Select>` dropdown with the 5 options. Changes are saved into `Agent.config` via `PUT /v1/agents/{id}` and take effect on the next session message.

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
Users can view live logs by navigating to the **Agent Detail** page and clicking the **"Live Logs"** button. Additionally, the centralized **Observability Hub** (`/logs`) provides a high-level overview of all execution streams across the entire swarm.

---

## Agent Runner Error Handling

When a model call fails (e.g., LLM provider overloaded, network timeout, invalid API key), the agent runner classifies the error, applies retry/backoff where appropriate, and sends a user-friendly message instead of raw exception text.

### Error Classification (Implemented 2026-06-01)

The runner imports LiteLLM exception types and maps them to categories:

| Category | LiteLLM Exception | User Message |
|---|---|---|
| `auth` | `AuthenticationError`, `BadRequestError` with "api key" | "The AI model's API key is invalid or has expired. Please contact the administrator." |
| `rate_limit` | `RateLimitError` | "The AI model is currently rate-limited. Please try again in a moment." |
| `timeout` | `Timeout`, connection errors | "Connection to the AI model timed out. Please try again shortly." |
| `overloaded` | `ServiceUnavailableError` | "The AI model is temporarily overloaded. Please try again in a moment." |
| `bad_request` | `BadRequestError` | "The request could not be processed by the AI model. It may be too long or contain unsupported content." |
| `unknown` | Catch-all | "An unexpected error occurred while talking to the AI model. The administrator has been notified." |

Classification uses `isinstance` checks as the primary path; string inspection is a fallback for provider-specific errors LiteLLM doesn't wrap.

### Retry with Jitter

Transient errors (`rate_limit`, `timeout`, `overloaded`) are retried up to 3 times with exponential backoff and ±50% jitter:

```
delay = min(1.0 * 2^attempt, 30.0)
delay = delay * (0.5 + random() * 0.5)   # ±50% jitter
```

Auth errors and bad requests are **not retried** — they will fail identically on every attempt.

### Model Fallback

`_model_with_fallback()` attempts the routed model first, then the agent's default model. If both fail, the turn halts with `RuntimeError`. Auth errors **short-circuit fallback** — the same dead API key would fail on every model, so the runner raises immediately without wasting tokens.

### Configurable Timeout

The `acompletion` call includes `timeout=self.config.config.get("litellm_timeout", 120)` (seconds). Heavy-reasoning agents can override this per-agent via their `config` field.

### Circuit Breaker for Sustained Auth Failures

After 3 consecutive authentication errors, the runner opens a **circuit breaker**:
- All new tasks/sessions fail fast for 5 minutes (`CIRCUIT_HALF_OPEN_AFTER = 300`)
- After 5 minutes, one **half-open probe** is allowed through
  - If the key was fixed → probe succeeds → circuit closes
  - If still broken → trips again → another 5 minute cooldown
- On runner restart, if Core shows `status="flagged"` with `auth_error`, the circuit restores immediately with the half-open window already elapsed — so an operator who fixed the key and restarted gets instant recovery
- Core is notified via `POST /v1/agents/{id}/model_error` so the Board UI shows the agent as flagged

### Ops Signaling

Two new Core endpoints enable durable ops visibility:
- `POST /v1/agents/{id}/model_error` — Core sets `Agent.status = "flagged"`, `status_reason = "auth_error(...)"`
- `POST /v1/agents/{id}/model_recovery` — Core sets `Agent.status = "online"` when the runner reports recovery

The recovery endpoint logs a noop message (`agents.model_recovery_noop`) if the agent was already manually set to `online`, preventing silent confusion during debugging.

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

### Budget Enforcement

Agents are subject to several budget constraints defined in `isli_core/budget.py` and enforced in the SDK:

1.  **Lifetime Token Budget (`token_budget`)**: The total tokens an agent can consume before being automatically paused.
2.  **Per-Turn Token Cap (`turn_token_cap`)**: A hard limit on the tokens sent to the LLM in a single turn (input + estimated output). 
    - **Mechanism**: If the turn exceeds the cap, the SDK identifies `tool` role messages and truncates them proportionally until the turn fits within the limit.
    - **Defaults**: 4,000 for local models (to ensure system prompts and context fit), 12,000 for cloud models.
    - **Estimation**: Uses a stable heuristic of `len(text) // 3.5` with a 5% safety margin.
3.  **Reasoning Budget**: Specific caps on tokens consumed during reasoning/Chain-of-Thought phases.

---

## Agent System Gaps
 (2026-05-11 Research)

The following gaps were identified during a parallel 12-agent research review:

### Critical
- ~~**Token budget enforcement (F15) entirely unimplemented**~~ — **Implemented 2026-05-21**. `POST /v1/agents/{id}/usage` endpoint records CostLedger, enforces agent/task/user/org budgets, and pauses agents on exceed. Agent SDK extracts `response.usage` from LiteLLM and reports back after every turn.
- ~~**No delegation cycle detection**~~ — **Implemented 2026-05-30**. `isli_core/delegation.py` enforces `MAX_DEPTH = 3` and raises `CycleDetectedError` on agent-id recurrence in ancestor chains.
- ~~**Unbounded delegation chain length**~~ — **Implemented 2026-05-30**. `MAX_DEPTH = 3` enforced in `validate_delegation()`; human approval required at depth ≥ 2.

### High
- **No global timeout for delegation chains** — individual tasks expire after 5 min, but cumulative chain timeout is absent.
- ~~**No fallback agents when primary fails**~~ — **Implemented 2026-05-30**. `Agent.fallback_agent_id` column + `isli_core/fallback.py` `FallbackManager`; `CheckpointRecoveryWorker` triggers fallback on max-retries exceeded.
- ~~**No model fallback strategy**~~ — **Implemented 2026-05-21**. `isli_core/cost/tiering.py` `ModelTiering.attempt_with_fallback()` implements three-tier fallback (premium → standard → local → pause) based on rate card and remaining budget.
- **Insufficient defense against consensus inertia** — F6 mitigations are passive isolation only; no active BICR "Challenge" step.
- **No deadlock detection** — BLOCKED agents waiting for child tasks can circularly wait with no breaker.
- ~~**JWTs long-lived with no rotation**~~ — **Fixed 2026-05-18**. `token_issued_at` column enables revocation. `POST /v1/agents/{id}/token` issues fresh tokens and invalidates old ones. Heartbeat renewals also update `token_issued_at`.
- ~~**Heartbeat validator flags agents on single flaky LLM response**~~ — **Fixed 2026-05-18**. Redis counter requires 3 consecutive anomalies before `flagged`; valid heartbeats auto-unflag.
- ~~**Heartbeat validator false-positives from stale episodic memories**~~ — **Fixed 2026-05-28**. Activity log entries now prefixed with timestamps; prompt instructs LLM to disregard entries older than 24h unless they show a persistent pattern.
- ~~**WebSocket auth bypasses token revocation**~~ — **Fixed 2026-05-18**. WebSocket endpoint now calls `_check_token_revocation` after `verify_internal_token`.

### Medium
- **No Kanban queue depth limit per agent** — unlimited ASSIGNED tasks with no backpressure.
- **No guard against delegating to offline agents** — tasks sit in ASSIGNED indefinitely.
- **No priority inversion detection** — high-priority tasks can be blocked behind low-priority ones.
- **No conflict resolution for simultaneous assignments** — two tasks to the same agent may contradict each other.
- **No monitoring for exponential relay degradation** — chain length and semantic drift are not measured.
L1201: - ~~**Agent turn loop ignores `token_budget`**~~ — **Implemented 2026-05-21**. `isli_core/budget.py` enforces hard caps via `BudgetExceededError`; agent status set to `paused` on exceed. SDK reports LiteLLM `usage` after every turn.
- ~~**Single oversized turn can deplete agent budget**~~ — **Implemented 2026-06-07**. `Agent.turn_token_cap` enforced in `isli-agent-sdk`. The SDK proportionally truncates `tool` role results if `estimated_input + max_tokens` exceeds the cap, ensuring the budget is preserved. Defaults: 4,000 (local) / 12,000 (cloud).


> See `Memory/ISLI-Research-Report.md` for full details and recommendations.