# 08 — Failure Modes & Mitigations

## Source: MAST Taxonomy (NeurIPS 2025)

The **MAST (Multi-Agent System Failure Taxonomy)** from UC Berkeley (NeurIPS 2025) identifies 14 failure modes across 3 categories validated against 1,600+ execution traces. ISLI's architecture explicitly counters each one.

> "Multi-agent systems fail not because the models are bad, but because the system design is bad."

---

## Category 1 — System Design Issues

### F1: Role and Task Ambiguity
**What it is**: Agents don't know clearly what they are supposed to do. A subordinate agent makes executive decisions. A coordinator agent does execution work.

**ISLI mitigation**:
- Agent `task_types` field in `agent.yaml` — explicit list of accepted task types
- Core API rejects task assignments that don't match an agent's declared `task_types`
- Agent persona is tightly scoped, not general-purpose
- Tasks have typed schemas, not free-text instructions

---

### F2: Specification Drift (Requirement Drift)
**What it is**: The original task goal shifts silently over a long execution chain. What the orchestrator asked for is no longer what the final agent delivers.

**ISLI mitigation**:
- Task `input` field is **immutable** after creation — agents cannot edit it
- Task `description` is always visible on the Kanban card
- Delegation chains: each child task stores `parent_task_id` and the parent's full `input`
- Keeper re-validates child task outputs against parent task intent (semantic similarity check)

---

### F3: Missing Verification / Validation Gap
**What it is**: No agent checks that the output is actually correct before it's delivered.

**ISLI mitigation**:
- Optional "Judge" role: any agent can be marked `is_judge: true` and assigned to verify outputs
- Skill `json-parse` with schema validation prevents malformed outputs from propagating
- Keeper's post-turn episodic write includes a `quality_flag` if the output has anomalies
- Human always sees the card and output — Kanban makes verification explicit

---

## Category 2 — Inter-Agent Misalignment

### F4: Context Drift (Factual Drift)
**What it is**: In long sessions, the agent forgets what was decided hours ago because it was pushed out of the context window.

**ISLI mitigation**:
- **Structured Session Journal**: Keeper maintains a persistent, lightly structured state (`[Context]`, `[Decisions]`, `[Last State]`) that is updated after every task.
- **Fast-Path Injection**: The journal is always injected into the agent's prompt, regardless of session length.
- 4-tier memory ensures critical decisions persist in the Journal and Episodic memory (Tier 2), never lost to window compression.
- Keeper's `context_inject` also retrieves top-5 relevant episodic memories to bridge gaps between sessions.

---

### F5: Alignment Drift (Goal Drift)
**What it is**: Agent "forgets why" — the original intent of a task. Separate from factual drift.

**ISLI mitigation**:
- Task `input` is immutable and always re-included in every Keeper context injection
- Keeper injects a "current task goal" reminder at the top of every context block
- Session memory stores user's original intent as a pinned first message

---

### F6: Echo Chamber / Conformity Bias
**What it is**: When one agent makes a confident wrong claim, other agents accept it rather than challenge it. False consensus locks in.

**ISLI mitigation**:
- Agents **never see each other's outputs directly** — only through Kanban task cards
- Different agents use different models by design (different blind spots)
- Judge agents have isolated system prompts (they never see the producing agent's reasoning — only the output)
- Keeper uses a local model for heartbeat/anomaly detection — independent from cloud models

---

### F7: Step Repetition (Infinite Loops)
**What it is**: Agent gets stuck repeating the same action. ReAct loop never terminates.

**ISLI mitigation**:
- Keeper **loop detection**: flags if same `task_id` remains `in_progress` beyond `stuck_threshold_seconds`
- Agent runtime: hard max iteration limit per task (default: 20 tool calls)
- Core API: task auto-expires after `task_timeout_seconds` (default: 5 minutes)
- Stuck tasks appear on Kanban board with ⚠️ warning and notify user

---

### F8: Loss of History / Conversation Reset
**What it is**: Agent loses all context mid-session — as if the conversation never happened.

**ISLI mitigation**:
- **Structured Session Journal** survives restarts: The pre-computed journal is stored in the PostgreSQL `sessions` table.
- **Incremental Updates**: The journal is updated after every successful task completion.
- On agent restart, the Keeper re-injects the last journal state and the most recent raw messages.
- 4-tier memory ensures nothing critical is stored only in RAM.
- **Fixed 2026-05-18**: Session soft-delete no longer wipes `messages`; revival no longer wipes `journal`; `session:message` event now includes `journal`; agent prepends it to the system prompt.

---

## Category 3 — Verification Gaps

### F9: Hallucination Propagation
**What it is**: One agent hallucinates. Downstream agents treat the hallucination as fact. Error cascades silently.

**ISLI mitigation**:
- Skills force evidence: `web-search` and `pdf-extract` return cited sources, not generated text
- Keeper's RAG gate: before injecting episodic memory, semantic similarity score is shown to agent ("this memory has 0.73 confidence")
- Task outputs are stored verbatim in Tier 4 — traceable to the producing agent
- Judge agent pattern: for high-stakes tasks, a second agent verifies output before delivery

---

### F10: Silent Failures (Execution & Correctness)
**What it is**: Agent produces output that looks correct but isn't, or a tool call fails silently/malforms arguments without raising a visible error.

**ISLI mitigation**:
- **Tool Execution Audits**: Every tool call is granularly logged: `Tool Call Initiated` → `Arguments (JSON)` → `Latency` → `Raw Output (capped)`.
- **Strict Pydantic Rejections**: Agent SDK uses Pydantic `validate_call(strict=True)` for all tools. Schema mismatches (e.g., missing fields, wrong types) are surfaced as prominent warning logs.
- **Structured LLM Feedback**: Validation errors are returned to the LLM as structured JSON reports, enabling models to self-correct their tool arguments on retry.
- **Circuit Breaker Visibility**: System-level circuit breakers log all state transitions (`OPEN`, `HALF_OPEN`, `CLOSED`) to the agent log stream, preventing silent skill outages.
- **Log Durability & Hydration**: The last 1000 agent logs are persisted in Redis history. The UI implements a robust hydration pattern (buffering live events during history fetch) and **end-relative pagination** (negative indexing) to allow seamless "Load More" navigation without race conditions.
- **Centralized Observability Hub (`/logs`)**: Provides a unified industrial dashboard for monitoring execution logs, audit trails, and memory journals across the entire swarm.

---

### F11: Cascading Errors (Compounding Mistakes)
**What it is**: Small error in step 1 becomes catastrophic by step 5.

**ISLI mitigation**:
- Kanban delegation chains are visible — human can inspect at any point
- Each child task's output is stored independently (Task archive, Tier 4)
- Keeper stores parent→child result trail in episodic memory
- Human can cancel mid-chain from Kanban board

---

### F12: Monoculture Blind Spots
**What it is**: Using the same model for both producing and verifying means the verifier has the same blind spots.

**ISLI mitigation**:
- Keeper uses a **different model family** (local Qwen/Llama) from cloud agent models (Claude/GPT)
- Judge agents are encouraged to use a different provider than the producing agent
- Agent `model.provider` can be mixed freely (Claude + Gemini + local)

---

### F13: Prompt Injection via Untrusted Input
**What it is**: Malicious content in a web-fetched page or user message hijacks agent behavior.

**ISLI mitigation**:
- All skill outputs go through Keeper's summarization before agent context injection
- Keeper is a small local model — less susceptible to sophisticated injection
- Skill `web-fetch` strips HTML and returns plain text only
- Memory stores with `read_only` flag for reference material (future feature)
- User input is sanitized and labeled `[USER INPUT]` in agent prompts

---

### F14: Credential/Permission Escalation
**What it is**: Agent gains access to resources beyond its intended scope.

**ISLI mitigation**:
- Per-agent JWT tokens with scoped permissions
- Skills proxy enforces `permissions_required` per skill per agent
- Agents cannot read each other's memory scopes
- All skill calls logged in Tier 4 archive — full audit trail
- Memory stores: agents can only write to their own `agent:{id}` scope

---

## Additional Failure Points (Beyond MAST)

### F15: Token Runaway Cost
**What it is**: An agent loop burns thousands of tokens unexpectedly, generating large API bills.

**ISLI mitigation**:
- Per-agent token budget enforcement: Core API tracks cumulative tokens per session
- Keeper's context injection is capped at `max_injection_tokens` (500 by default)
- Skill large-output summarization prevents skill results from bloating context
- Kanban card shows token usage in real-time
- Optional: per-agent daily token cap with automatic pause

---

### F16: Flat Organization Failure
**What it is**: Every agent can talk to every other agent without structure, creating coordination chaos.

**ISLI mitigation**:
- `can_delegate_to` / `can_receive_from` lists in `agent.yaml` — explicit delegation graph
- Kanban board enforces task routing — no off-board communication
- Core API rejects delegation attempts from agents not in the allowed graph

### F17: Notification Delivery Failures
**What it is**: Alerts are lost, delayed, or duplicated due to race conditions in the unified notification pipeline. Users miss critical agent crashes because the event never reached their phone, or they receive the same digest twice after a container restart.

**ISLI mitigation**:
- **DB-as-authority**: PostgreSQL `notifications` table is the single source of truth for unread count. Redis is a best-effort cache with 5-min TTL and anti-drift `EXISTS` checks.
- **Durable Outbox**: All deliveries go through the `Outbox` table with retry logic and `dead_letter` status. In-app and external handlers are registered in Core's lifespan, not ad-hoc.
- **Digest idempotency**: `DigestWorker` uses `LRANGE` + `LTRIM` atomically — items are removed from Redis *before* processing, preventing double-delivery on crash.
- **Rate limiting**: `notif:agent_rate:{agent_id}:{user_id}` sliding window (max 20/hour) prevents runaway agent spam that could overwhelm downstream channels.
- **Preference fallback**: If Redis cache or preference row is missing, `DEFAULT_CATEGORIES` ensures users still receive critical events (`agent:crash`, `task:failed`).
- **Quiet hours safety**: Critical events (`priority: critical`) always bypass quiet hours. Only non-critical events are suppressed or batched.

### F18: Provider-Specific Schema Quirks
**What it is**: Different LLM providers (Gemini, Claude, GPT) have slightly different expectations for tool call formatting and message history. A "standard" ReAct loop that works for one provider may crash another due to strict schema validation or unexpected argument types. Local models via Ollama (Qwen, Llama) may output tool calls as XML or raw JSON blobs inside `message.content` rather than using the structured `tool_calls` array.

**ISLI mitigation**:
- `AgentRunner` includes a provider-specific normalization layer.
- **Gemini hardening**: Strips empty `tool_calls` and `function_call: None` from history.
- **Robust parsing**: Tool argument parser handles both JSON strings and native Python dicts (returned by some Gemini/Vertex models).
- **Env Fallback**: Automatically injects provider keys into environment variables (e.g., `GEMINI_API_KEY`) to satisfy SDK-specific lookup patterns.
- **Tool Call Format Fallbacks (Added 2026-05-29)**: When `message.tool_calls` is empty, the runner attempts two fallback parsers before treating the response as final text:
  1. **Anthropic-style XML** (`<function_calls>...</invoke>`) — parsed with `xml.etree.ElementTree`
  2. **JSON-in-text blob** (`{"name":"...","arguments":{...}}`) — matched via brace-counting, validated against registered tool names
  Both fallbacks produce synthetic `_ParsedToolCall` objects compatible with the existing execution loop, strip the markup from the final response, and inject clean `tool_calls` into conversation history for LiteLLM replay.

### F19: WhatsApp Silent Message Loss (Consent & Error Cascades)
**What it is**: Three cascading failures in the WhatsApp pipeline cause inbound messages to be silently dropped with zero user feedback:
1. **Consent gate**: Core requires `UserConsent` for every message. New users who haven't sent `/start` receive HTTP 403.
2. **Error swallowing**: The WhatsApp adapter propagates the 403 as an unhandled exception, which FastAPI converts to HTTP 500.
3. **No retry on 4xx**: The sidecar's `axiosRetry` retries on 5xx but not on 4xx. A 500 from channels is retried 3 times, then the message is permanently lost.

**ISLI mitigation** (Fixed 2026-05-29):
- **Graceful 403 handling**: `WhatsAppAdapter._handle_inbound_message()` wraps `_forward_to_core()` in `try/except httpx.HTTPStatusError`. On 403, it sends an auto-reply: *"Welcome! Please send /start to begin chatting with this agent."*
- **Webhook error surfacing**: `whatsapp_sidecar_webhook` in `isli_core/routers/channels.py` catches adapter exceptions and returns appropriate status codes (200 for handled 403, 500 only for true transient errors).
- **Context failure notification**: `SessionContextInjectorWorker` sends a proactive message to the user when a session reaches `context_failed` after max retries: *"Sorry, I'm having trouble processing your message right now. Please try again later."*

### F20: WhatsApp Adapter State Loss on Restart
**What it is**: `connection_states`, `qr_codes`, and `qr_sequences` are stored in plain Python dicts inside `WhatsAppAdapter`. When the `isli-channels` container restarts, all state is lost. Agents that were connected appear "disconnected" even though the sidecar still has an active Baileys session.

**ISLI mitigation** (Fixed 2026-05-29):
- **Direct sidecar queries**: `get_status()` and `get_qr()` query the sidecar's REST API (`GET /session/{agentId}/status` and `/qr`) instead of reading in-memory dicts. Status survives adapter restarts.
- **Idempotent create**: `create_session()` queries the sidecar first to check if already connected, returning `already_connected` instead of trying to start a duplicate session.

---

### F21: WhatsApp Sidecar → Channels HMAC Auth Format Mismatch
**What it is**: The WhatsApp sidecar sends the raw `SIDECAR_WEBHOOK_SECRET` string as the `X-Sidecar-Secret` header, but Channels expects an **HMAC-SHA256 hex digest** of the request body. Every inbound webhook is rejected with `401 Unauthorized`, causing all WhatsApp messages to be silently dropped.

**ISLI mitigation** (Fixed 2026-05-29):
- **HMAC computation in sidecar**: `forwardEvent()` now computes `crypto.createHmac('sha256', SIDECAR_WEBHOOK_SECRET).update(body).digest('hex')` before sending.
- **Pre-stringified body**: Passes the exact JSON string to axios (not an object) so the HMAC matches the bytes on the wire.

### F22: Channels → Core Webhook Secret Mismatch
**What it is**: The Channels adapter signs forwarded payloads with `WEBHOOK_SECRET` (env value: `"telegram-secret"`), but Core's `config.py` hardcodes `webhook_secrets["whatsapp"] = "whatsapp-secret"`. All WhatsApp messages forwarded from Channels to Core are rejected with `401 Unauthorized`.

**ISLI mitigation** (Fixed 2026-05-29):
- **Unified secret**: Core now reads `WEBHOOK_SECRET` from the environment and uses it for all channels (`telegram` and `whatsapp`).
- **Compose wiring**: `docker-compose.yml` explicitly passes `WEBHOOK_SECRET: ${WEBHOOK_SECRET}` to the `core` service so the env var is available inside the container.

### F23: WhatsApp JID Format Mismatch (Lost Replies)
**What it is**: WhatsApp's privacy feature sends inbound messages with LID JIDs (`xxx@lid`) instead of phone-number JIDs (`xxx@s.whatsapp.net`). The adapter normalizes the JID to a phone number for Core's `user_id`, then reconstructs `xxx@s.whatsapp.net` for replies. The reply is sent to a non-existent address and silently lost.

**ISLI mitigation** (Fixed 2026-05-29):
- **JID preservation**: `_handle_inbound_message()` stores the original `remote_jid` in `self.user_jids[agent_id][phone_number]`.
- **Reply routing**: `send_message()` looks up the preserved JID before calling the sidecar, falling back to `xxx@s.whatsapp.net` only if no LID was recorded.

### F24: Python 3.12 `datetime.UTC` AttributeError
**What it is**: Core's command handler uses `datetime.now(datetime.UTC)`, which does not exist in Python 3.12 (only `timezone.utc` from the `datetime` module). The `/new` command crashes with `AttributeError: type object 'datetime.datetime' has no attribute 'UTC'`, leaving the user with no response and a broken session state.

**ISLI mitigation** (Fixed 2026-05-29):
- **Import fix**: Changed `from datetime import datetime, timedelta` to `from datetime import datetime, timedelta, timezone`.
- **Usage fix**: Replaced all four occurrences of `datetime.UTC` with `timezone.utc` in `commands.py`.

### F18: DNS Caching & Stale Service IPs
**What it is**: After a container rebuild or restart, a service is assigned a new internal IP. Upstream proxies (like the Board's Nginx or Traefik) continue attempting to use the old cached IP, leading to 502 Bad Gateway errors despite the service being healthy.

**ISLI mitigation**:
- **Service Restart Orchestration**: Restarting the proxy/frontend service (e.g., `isli-board`) alongside backend updates forces a cache flush.
- **Resolver Tuning**: Nginx is configured with a short `valid` interval on the resolver (`resolver 127.0.0.11 valid=30s;`) to limit the window of stale connectivity.
- **Traefik Dynamic Discovery**: Traefik handles dynamic IP changes automatically via the Docker provider; however, static Nginx configs within containers require the manual restart or tuning mentioned above.

### F26: Streaming Event Bus Failure
**What it is**: The agent emits streaming events (token_delta, tool_call, etc.) during its turn, but the WebSocket connection drops, Redis is unavailable, or Core's WS gateway crashes. If streaming failures propagate into the agent's ReAct loop, they could crash the agent or corrupt the final response.

**ISLI mitigation** (Implemented 2026-05-31):
- **Broad exception swallowing**: Every `_emit_stream_event()` call is wrapped in `try/except Exception` that logs a warning and swallows the error. Streaming failures never propagate into the ReAct loop.
- **Redis draft persistence**: Partial text is stored in `session:{id}:draft` so Board clients reconnecting mid-stream can recover the accumulated response.
- **Debug event isolation**: `debug_prompt` and `debug_response` events are stored in a Redis list (`session:{id}:debug_trace`) and exposed only via an admin-only REST endpoint (`GET /v1/sessions/{id}/debug-trace`). They are never broadcast over the WebSocket, preventing prompt injection data exposure.
- **Fallback to silent mode**: If the agent cannot resolve its streaming mode or the mode is invalid, it defaults to `silent` (legacy batch behavior) rather than raising.
- **Per-session override**: A session can override the agent's streaming mode via `session_metadata`. If the override is invalid, it falls back to the agent default.

---

### F25: Model Routing Failure (Routed Model Unavailable or Wrong)
**What it is**: An agent is configured with model routing enabled, but the Keeper-selected model is unavailable (e.g., provider outage, invalid API key), or the Keeper hallucinates a non-existent model name. The agent crashes or silently degrades to an even cheaper model, producing poor output without warning.

**ISLI mitigation** (Implemented 2026-05-31):
- **Explicit three-tier fallback** in `AgentRunner._model_with_fallback()`:
  1. Attempt the routed model (if `routed_model_id` is present and valid)
  2. Attempt the agent's **default** model (`model_provider` / `model_id`) — **never skipped**
  3. If both fail, raise `RuntimeError` and halt the turn (no silent downgrade to unconfigured models)
- **Startup guard**: `AgentRunner.__init__` asserts that `model_provider` and `model_id` are non-null. An agent with no default model cannot start.
- **Validation gate**: Core validates the Keeper's returned `model_id` against the agent's `secondary_models` whitelist before writing it to the task/session record.
- **Fail-open heuristic**: If the Keeper returns invalid JSON or an unknown model, Core immediately falls back to the default model and logs a telemetry event.
- **Session-lifetime lock**: Once a model is chosen for a session, it is never re-routed, preventing mid-session model swaps that would break context continuity.

### F28: Model Over-Refusal (Tool Safety Paranoia)
**What it is**: An LLM (particularly reasoning-heavy models like Kimi K2.6) treats a benign tool as high-stakes and refuses to execute it even when explicitly requested by the user. The model invents constraints ("four parameters are strictly required," "may escalate to Telegram based on your account preferences") that do not exist in the actual tool schema, and enters an infinite approval loop.

**ISLI mitigation** (Fixed 2026-06-01):
- **System prompt counter-instruction**: Added explicit language: *"When the user asks you to send a notification, use notify_user immediately. The user's request is their approval — do not ask for additional confirmation."*
- **Tool description neutralization**: Replaced caution-triggering words ("unified notification system", "may escalate to Telegram", "proactive outreach") with neutral language ("Display a notification card in the user's web UI").
- **Session metadata injection**: The runner injects `user_id` into the system prompt so the model has all required parameters and cannot claim they are "missing from context".
- **Effective user_id fallback**: For web sessions where `user_id` is `NULL`, the runner falls back to `session_id` so the tool always has a valid target.

---

### F27: Model API Authentication Failures (Auth Error Cascades)
**What it is**: An agent's LLM API key expires or is revoked (e.g., Gemini `API_KEY_INVALID`). The agent crashes with a raw exception trace, burning tokens on every retry attempt. The user sees an opaque error message. The agent stays `"online"` in the Board UI even though every request will fail. The crash-loop continues indefinitely, maxing out rate limits and generating support tickets.

**ISLI mitigation** (Implemented 2026-06-01):
- **Error classification**: `AgentRunner._classify_model_error()` uses `isinstance` checks on LiteLLM exceptions (`AuthenticationError`, `RateLimitError`, `Timeout`, `ServiceUnavailableError`, `BadRequestError`) with string fallback. Auth errors get a user-friendly message: *"The AI model's API key is invalid or has expired. Please contact the administrator."*
- **No raw traces to users**: Fatal error catch blocks map all exceptions to `user_message` strings — never `str(e)`.
- **Retry only transients**: `_acompletion_with_retry()` retries `rate_limit`/`timeout`/`overloaded` up to 3 times with exponential backoff + ±50% jitter. Auth errors raise immediately.
- **Auth-guarded fallback**: `_model_with_fallback()` short-circuits on `ModelErrorCategory.AUTH` — falling back to another model with the same dead key wastes tokens.
- **Circuit breaker**: After 3 consecutive auth failures, the runner opens a circuit. New tasks fail fast for 5 minutes, then one half-open probe is allowed. Success closes the circuit; failure re-opens it. This stops the token-burn loop.
- **Self-healing on restart**: If Core shows `status="flagged"` with `auth_error`, the runner restores the circuit with the half-open window already elapsed — an operator who fixed the key and restarted gets instant recovery.
- **Durable ops visibility**: `POST /v1/agents/{id}/model_error` sets `Agent.status = "flagged"` in Core. `POST /v1/agents/{id}/model_recovery` sets it back to `"online"`. The Board UI reflects agent health truthfully.

---

## Summary Table

| Failure Mode | Primary Defense | Secondary Defense |
|-------------|----------------|------------------|
| Role ambiguity | `task_types` enforcement | Scoped agent personas |
| Spec drift | Immutable task input | Kanban visibility |
| No verification | Judge agent pattern | Human Kanban review |
| Context drift | Keeper compaction + re-inject | 4-tier memory |
| Goal drift | Task goal always injected | Immutable task input |
| Echo chamber | Agent isolation via Kanban | Multi-model diversity |
| Loops | Loop detection + hard limit | Task auto-expiry |
| History loss | 4-tier memory | Compaction to PostgreSQL |
| Hallucination cascade | Evidence-first skills | Judge agent |
| Silent failures | Schema validation | Keeper anomaly flags |
| Cascading errors | Kanban chain visibility | Human cancel |
| Monoculture | Keeper = different model | Mixed providers |
| Prompt injection | Keeper pre-processes input | Skill output sanitization |
| Credential escalation | Scoped JWT + skill proxy | Tier 4 audit log |
| Token runaway | Token budget enforcement | Per-agent daily cap |
| Flat org chaos | Delegation graph rules | Kanban routing |
| Schema quirks | Provider-specific normalization | Tool call format fallbacks (XML + JSON) |
| DNS Caching | Service restart orchestration | Nginx resolver tuning |
| WhatsApp HMAC mismatch | Sidecar computes HMAC-SHA256 | Channels validates with `compare_digest` |
| WhatsApp secret mismatch | Core reads `WEBHOOK_SECRET` from env | Both channels share unified secret |
| WhatsApp JID mismatch | Adapter preserves original JID | `send_message` looks up LID before routing |
| `datetime.UTC` crash | `timezone.utc` import | Consistent usage across command handlers |
| Model routing failure | Explicit routed → default → halt fallback | Validation against secondary_models whitelist |
| Streaming bus failure | Broad exception swallowing in `_emit_stream_event` | Redis draft persistence + debug event isolation |
| Model auth failure | Error classification + circuit breaker | Half-open self-healing + Core `flagged` status |
| Keeper congestion | Internal Priority Queue (P0-P3) | Adaptive Throttling (429) |
| Latency spikes | Latency SLO Monitoring (P95) | Queue Depth Observability |

---

## Discovered Gaps (Post-Research, 2026-05-11)

The 2026 research review identified structural resilience patterns that ISLI currently lacks. These are not new MAST categories but missing implementation depth within existing ones:

| Gap | Related MAST Mode | Status | Recommended Fix |
|-----|-------------------|--------|---------------|
| Circuit breakers (CLOSED/OPEN/HALF_OPEN) | F7, F11, F15 | **Implemented in Core / SDK** | `isli_core.circuit_breaker` wraps Skills proxy and agent runner cloud-model calls. **Removed from Keeper 2026-06-03** — local Ollama proxy uses "honest 503" instead. Extend to WebSocket pool |
| **Workload Prioritization (P0-P3)** | F7, F15 | **Fixed 2026-06-02** | Implemented `PriorityManager` in Keeper; P0 bypasses P3 backlog |
| **Latency SLOs & Percentiles** | F10, F15 | **Fixed 2026-06-02** | Dashboard tracks p50/p95/p99; automated SLO health status |
| **Adaptive Throttling (429)** | F15 | **Fixed 2026-06-02** | Keeper rejects P3 tasks if queue depth > 50 |
| No checkpointing for agent turn state | F8, F11 | **Implemented 2026-05-30** | `CheckpointManager` + `POST /tasks/{id}/checkpoint` + `CheckpointRecoveryWorker` recover stalled tasks from PostgreSQL-saved turn state |
| No BICR governance (Buffer, Isolate, Challenge, Recover) | F6, F11 | **Missing** | Model BICR: Buffer = Keeper pre-processing; Isolate = sandbox; Challenge = Judge + similarity gate; Recover = rollback + fallback |
| No chaos engineering validation | All | **Missing** | Create fault-injection suite to assert mitigations F1–F16 actually trigger |
| No automatic rollback for delegation chains | F11 | **Missing** | Implement delegation saga log with per-step compensation actions |
| No e-stop / global pause mechanism | All | **Missing** | Implement global pause topic that rejects new tasks and closes active WebSockets |
| No dead-letter queue for failed tasks | F7, F10 | **Implemented 2026-05-30** | `failed` status in `VALID_STATUSES`; `retry_count` on `Task` model; `CheckpointRecoveryWorker` marks poison pills after max retries; Board shows Failed column |
| No bulkhead pattern for resource isolation | F15, F16 | **Missing** | Add per-agent connection limits and per-skill thread pools |
| Delegation cycle detection missing from F7 | F7 | **Implemented 2026-05-30** | `isli_core/delegation.py` enforces `MAX_DEPTH = 3` and `CycleDetectedError` on agent-id recurrence in ancestor chains |
| Token budget enforcement unimplemented (F15) | F15 | **Implemented 2026-05-21** | `POST /v1/agents/{id}/usage` checks agent/task/user/org budgets; agent SDK reports LiteLLM usage after each turn; Board Cost Analytics page shows real-time spend |
| Heartbeat commits token revocation before guaranteeing delivery | F14 | **Fixed 2026-05-18** | Moved `token_issued_at` update to after all side effects in heartbeat endpoint |
| Agent task API calls use JWT instead of admin key | F14 | **Fixed 2026-05-18** | `complete_task()`, `move_task()`, `save_checkpoint()` now pass `use_admin=True` to `_get_headers()` |
| JWT token revocation | F14 | **Implemented 2026-05-18** | `token_issued_at` column + `POST /v1/agents/{id}/token` invalidates old tokens on recovery |
| Keeper timeout chain too short for slow hardware | F7, F15 | **Fixed 2026-05-18** | Core→Keeper timeouts increased to 180s (journal/heartbeat), 120s (context injection); Keeper→Ollama to 120s; Ollama client timeout raised to 300s |
| Session compaction cron redundant with JournalWorker | F8 | **Fixed 2026-05-18** | Deprecated `compact_sessions`; JournalWorker already truncates to last 10 messages |
| Agent task path ignores pre-computed context | F4 | **Fixed 2026-05-18** | `AgentRunner._execute_task()` now reads `task.context_summary` first |
| Crude token counting triggers compaction too early | F15 | **Fixed 2026-05-18** | `len(str(messages))` → `len(str(messages)) // 4` (4-char/token heuristic) |
| Session soft-delete causes duplicate key violation on revival | F8 | **Fixed 2026-05-18** | `channel_webhook` now queries for soft-deleted sessions and revives them instead of re-inserting |
| Soft-delete wipes raw messages (history loss) | F8 | **Fixed 2026-05-18** | Removed `sess.messages = []` from `expire_sessions` and `detect_idle`; raw messages persist |
| Revival code wipes structured journal | F8 | **Fixed 2026-05-18** | Removed `journal = None` and `context_summary = None` from session revival in `channels.py` |
| Event payload never includes journal | F8 | **Fixed 2026-05-18** | `session:message` event now includes `"journal": sess.journal`; agent prepends it to system prompt |
| Heartbeat validator flags agents on single flaky LLM response | F14 | **Fixed 2026-05-18** | Redis counter `agent:heartbeat:anomaly:{id}` requires 3 consecutive anomalies before `flagged`; valid heartbeat auto-unflags |
| Cascading timeouts during heartbeat validation | F7, F15 | **Fixed 2026-05-19** | Implemented per-request timeouts (30s) for heartbeat validation in Keeper; fails open with `is_valid: True` and warning log on timeout/error. |
| Anomaly detection choking on large logs | F7 | **Fixed 2026-05-20** | Added activity log compression (deduplication + truncation) in `isli-keeper`. |
| Heartbeat validator false-positives from stale memories | F7, F10 | **Fixed 2026-05-28** | Activity log entries now prefixed with timestamps; prompt instructs LLM to disregard entries older than 24h. |
| Episodic memories never garbage-collected | F8 | **Fixed 2026-05-28** | `MemoryGCWorker` runs every 24h with exponential-decay importance scoring and physical deletion. |
| Infinite tool loop recursion | F7 | **Fixed 2026-05-20** | Added `MAX_CONSECUTIVE_TOOL_FAILURES` (3) in `isli-agent-sdk`. |
| Infinite reasoning loops | F7 | **Fixed 2026-05-20** | Added `MAX_LLM_TURNS` (50) in `isli-agent-sdk`. |
| Silent agent failure (ghosting) | F7 | **Fixed 2026-05-20** | Added `CheckAgentStalenessWorker` in `isli-core` to mark stale agents (5m) as `unresponsive`. |
| WebSocket auth bypasses token revocation | F14 | **Fixed 2026-05-18** | WebSocket endpoint now calls `_check_token_revocation` after `verify_internal_token` |
| Silent event drop when agent WebSocket offline | F7, F8 | **Fixed 2026-05-18** | `send_to_agent` now queues to Redis list `agent:events:{id}` with TTL 1h / max depth 50 |
| Agent never catches up on reconnect | F8 | **Fixed 2026-05-18** | `connect_agent` drains queued Redis events immediately upon WebSocket connect |
| No automatic offline detection | F7 | **Fixed 2026-05-18** | `CheckpointRecoveryWorker` now sets `agent.status = "offline"` on stale heartbeat and triggers `FallbackManager` |
| Short task lease reclaims long-running work | F7 | **Fixed 2026-05-18** | `task_lease_minutes` increased from 5 to 30 |
| Core→Channels delivery swallowed with no retry | F10 | **Fixed 2026-05-18** | `reply_to_session` now uses `exponential_backoff` with 3 retries; Telegram adapter retries 3× with backoff |
| Checkpoint recovery crashes on tuple unpacking | F7, F11 | **Fixed 2026-05-18** | `rows_map[task.id] = (task, agent)` comprehension now unpacks `for _, (task, agent) in rows_map.items()` |
| Agent runner opaque error messages | F10 | **Fixed 2026-05-18** | `runner.py` catch-all now classifies overloaded/timeout vs generic; `acompletion` has `timeout=120` |
| Gemini API key sync issues | F14, F17 | **Fixed 2026-05-22** | `client.py` now explicitly calls `/v1/agents/{id}/config` after registration to prevent `api_key` stripping during sanitized sync. |
| Gemini 400 Bad Request on message history | F17 | **Fixed 2026-05-22** | `runner.py` now strips `function_call: None` and empty `tool_calls: []` using `model_dump(exclude_none=True)`. |
| Gemini crashes on tool argument types | F17 | **Fixed 2026-05-22** | `runner.py` argument parser now handles both raw JSON strings and pre-parsed Python dicts from Gemini. |
| Agent crash status not persisted to DB | F7, F10 | **Fixed 2026-05-28** | `AgentProcessManager._watch_docker()` now calls `_update_agent_status()` to write `"crashed"` or `"stopped"` to PostgreSQL on exit |
| Docker container logs lost on crash | F10 | **Fixed 2026-05-28** | `_stream_docker_logs()` streams container stdout/stderr to Redis (`agent:{id}:logs` and `:history`) so Board shows crash output |
| Stale container 409 conflict blocks restart | F7 | **Fixed 2026-05-28** | `_spawn_docker()` defensively force-removes any existing container with the same name before creating a new one |
| Agent-runner SDK bind-mount breaks image | F10 | **Fixed 2026-05-28** | Skipped volume mount in Docker mode; image already contains baked-in SDK. Prevents `ModuleNotFoundError: No module named 'isli_agent'` |
| DB pool exhaustion during startup burst | F7, F15 | **Fixed 2026-05-28** | `db.py` now uses `pool_timeout: 60` and `pool_recycle: 3600` to handle all background workers connecting simultaneously |
| WebSocket 401 recovery gap (token revocation) | F14 | **Fixed 2026-05-28** | Runner `_ws_loop` now recovers token on 401 (not just 403), matching heartbeat loop behavior |
| Heartbeat 401 lockout (re-validated) | F14 | **Re-validated 2026-05-28** | `token_issued_at` commit remains at end of heartbeat endpoint after all side effects; fix confirmed still in place |
| WhatsApp consent gate silently drops messages | F10 | **Fixed 2026-05-29** | `WhatsAppAdapter._handle_inbound_message()` catches 403 and sends auto-reply: "Please send /start" |
| WhatsApp context injection fails silently | F10 | **Fixed 2026-05-29** | `SessionContextInjectorWorker` sends proactive message to user when session reaches `context_failed` |
| WhatsApp sidecar returns 500 for 403 | F10 | **Fixed 2026-05-29** | `whatsapp_sidecar_webhook` catches adapter errors and returns appropriate status codes |
| WhatsApp adapter state lost on restart | F8 | **Fixed 2026-05-29** | `get_status()` and `get_qr()` query sidecar directly instead of in-memory dicts |
| WhatsApp sidecar sends raw secret instead of HMAC | F21 | **Fixed 2026-05-29** | `forwardEvent()` in `index.js` now computes `crypto.createHmac('sha256', ...)` over JSON body |
| Core hardcodes wrong webhook secret for WhatsApp | F22 | **Fixed 2026-05-29** | `config.py` reads `WEBHOOK_SECRET` from env; `docker-compose.yml` passes it to `core` service |
| WhatsApp replies lost due to LID JID mismatch | F23 | **Fixed 2026-05-29** | `WhatsAppAdapter` preserves original `remote_jid` and uses it for outbound `send_message()` |
| `/new` command crashes on `datetime.UTC` | F24 | **Fixed 2026-05-29** | Replaced `datetime.UTC` with `timezone.utc` in `commands.py` |
| Agent ignores tool calls from XML/JSON models | F17 | **Fixed 2026-05-29** | `runner.py` added `_extract_xml_tool_calls()` and `_extract_json_tool_calls()` with `_ParsedToolCall` normalization; strips markup from final response; injects synthetic `tool_calls` into history |
| Board UI 502 because `core` unresolvable from `board` container | F22 | **Fixed 2026-06-03** | `board` service added to `isli-mesh` network in `docker-compose.yml` so nginx `proxy_pass` to `core:8000` resolves via Docker DNS |
| Agents orphaned on wrong Docker network | F7, F22 | **Fixed 2026-06-03** | `AGENT_NETWORK` changed from `isli_isli` to `isli_isli-mesh` in `docker-compose.yml`; ensures spawned agents share a network with Core |
| `websockets` 14+ `extra_headers` API break | F17 | **Fixed 2026-06-03** | `runner.py` changed `extra_headers=` to `additional_headers=` in `websockets.connect()` call; agent-runner image rebuilt |
| Ollama-init cannot reach internet | F15 | **Fixed 2026-06-03** | `ollama-init` added to `isli-mesh` network (in addition to `isli-data`) so `registry.ollama.ai` is resolvable |
| Missing `WEBHOOK_SECRET` causes 401 everywhere | F14, F22 | **Fixed 2026-06-03** | Added `WEBHOOK_SECRET` and `SKILL_REGISTRY_TOKEN` to `.env` and `docker-compose.yml`; verified both are passed to Core and Skills services |
| `.env.example` missing required secrets | F22 | **Fixed 2026-06-03** | `.env.example` updated to document `WEBHOOK_SECRET`, `SKILL_REGISTRY_TOKEN`, and `AGENT_ID` |

> **Note:** Many mitigations have been implemented since the 2026-05-11 research review. Items marked **Fixed** or **Implemented** are in production code. A smaller number remain design-only; see inline status markers for details.
