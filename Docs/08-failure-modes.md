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

### F10: Silent Correctness Failures
**What it is**: Agent produces output that looks correct but isn't. No error is raised.

**ISLI mitigation**:
- Skill `json-parse` with Pydantic schema validation on structured outputs
- Keeper anomaly detection on task outputs: length, format, confidence signals
- Budget meter: agents report token usage; runaway token usage (3x expected) triggers Kanban alert

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

---

## Discovered Gaps (Post-Research, 2026-05-11)

The 2026 research review identified structural resilience patterns that ISLI currently lacks. These are not new MAST categories but missing implementation depth within existing ones:

| Gap | Related MAST Mode | Status | Recommended Fix |
|-----|-------------------|--------|---------------|
| Circuit breakers (CLOSED/OPEN/HALF_OPEN) | F7, F11, F15 | **Implemented** | `isli_keeper/circuit_breaker.py` wraps Ollama calls; extend to WebSocket pool and Skills proxy |
| No checkpointing for agent turn state | F8, F11 | **Missing** | Add agent-side turn checkpointing to PostgreSQL before each tool call |
| No BICR governance (Buffer, Isolate, Challenge, Recover) | F6, F11 | **Missing** | Model BICR: Buffer = Keeper pre-processing; Isolate = sandbox; Challenge = Judge + similarity gate; Recover = rollback + fallback |
| No chaos engineering validation | All | **Missing** | Create fault-injection suite to assert mitigations F1–F16 actually trigger |
| No automatic rollback for delegation chains | F11 | **Missing** | Implement delegation saga log with per-step compensation actions |
| No e-stop / global pause mechanism | All | **Missing** | Implement global pause topic that rejects new tasks and closes active WebSockets |
| No dead-letter queue for failed tasks | F7, F10 | **Missing** | Add `Failed` Kanban column with retry count, failure reason, and human retry action |
| No bulkhead pattern for resource isolation | F15, F16 | **Missing** | Add per-agent connection limits and per-skill thread pools |
| Delegation cycle detection missing from F7 | F7 | **Missing** | Extend loop detection to inter-agent delegation DAGs, not just intra-agent state revisits |
| Token budget enforcement unimplemented (F15) | F15 | **Missing** | Implement hard token caps at Core API level before any model call |
| Heartbeat commits token revocation before guaranteeing delivery | F14 | **Fixed 2026-05-18** | Moved `token_issued_at` update to after all side effects in heartbeat endpoint |
| Agent task API calls use JWT instead of admin key | F14 | **Fixed 2026-05-18** | `complete_task()`, `move_task()`, `save_checkpoint()` now pass `use_admin=True` to `_get_headers()` |
| JWT token revocation | F14 | **Implemented 2026-05-18** | `token_issued_at` column + `POST /v1/agents/{id}/token` invalidates old tokens on recovery |
| Keeper timeout chain too short for slow hardware | F7, F15 | **Fixed 2026-05-18** | Core→Keeper timeouts increased to 180s (journal/heartbeat), 120s (context injection); Keeper→Ollama to 120s; circuit breaker recovery to 120s |
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

> **Note:** Most documented mitigations are architectural intent only. The circuit breaker (`isli_keeper/circuit_breaker.py`) and JWT token revocation are implemented; the rest remain design-only.
