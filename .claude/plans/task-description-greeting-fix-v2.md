# Plan: Fix Kanban tasks completing with only a greeting (v2)

## Problem Statement

Tasks created from the Board UI are marked `done`, but their output is a generic greeting/status message instead of actually doing the requested work. The task description never reaches the LLM.

## Root Cause (two independent bugs)

### Bug 1: Keeper `/context/inject` drops the task description

- Core sends `task_description` to Keeper (`isli-core/src/isli_core/memory/keeper_client.py:25-45`).
- Keeper's `/context/inject` (`isli-keeper/src/isli_keeper/main.py:462-594`) uses `task_description` **only** for semantic memory search; the returned `context_summary` is built from identity, journal, recent messages, and memories — the task description itself is never included.
- Result: the agent's system prompt `=== CONTEXT ===` block lacks the work order.

### Bug 2: Agent runner reads the wrong field as the user work order

- Board-created tasks populate `title` and `description`; `input` defaults to `""` (`isli-board/src/components/CreateTaskModal.tsx:35-44`).
- Agent runner `ReActLoop.execute_task` builds the user message from `task_data.get("input", "")` (`isli-agent-sdk/src/isli_agent/runner/react_loop.py:201`).
- Because `input` is empty, the LLM receives an empty user message on top of a context summary that also lacks the task.
- The agent has no actionable instruction and falls back to a greeting/status card, then `complete_task()` marks the task `done`.

### Secondary issue: PII-mesh path also loses the task description

- When `agent.config.pii_mesh_enabled` is true, Core calls `PIIKeeperClient.session_prep()` (`isli-core/src/isli_core/jobs/context_worker.py:315-340`) but does not pass `task_description` into the combined text.
- The unified `/session-prep` endpoint (`isli-keeper/src/isli_keeper/session_prep.py:209-344`) therefore never sees the task either.

---

## Verified field usage (from grep)

| Caller | Sets `title` | Sets `description` | Sets `input` | Notes |
|--------|-------------|--------------------|--------------|-------|
| **Board UI** (`CreateTaskModal.tsx`) | ✅ | ✅ | ❌ never | `input` defaults to `""` |
| **Agent SDK** (`create_kanban_task`, `kanban.py:36-45`) | ✅ | ✅ | ✅ from `input_data` | Explicit "specific input or context required to start the task" |
| **Core skill proxy** (`skills.py:1695`) | ✅ | ✅ | ✅ maps `input_data` | Same as SDK path |
| **Scheduler worker** (`scheduler_worker.py:106`) | cloned | cloned | cloned | Preserves whatever the parent had |
| **Direct REST API** | optional | optional | optional | Any combination possible |
| **Slash commands / channels** | — | — | — | No direct task creation found in `commands.py`, `channels.py`, or `sessions.py` |

**Conclusion:** `input` is empty for Board-created tasks, but is deliberately populated by programmatic and agent-driven callers. The correct precedence is therefore:

```python
work_order = task_data.get("input") or build_from_title_description(task_data)
```

`input` wins when present and non-empty because it is an explicit execution payload from a caller who chose that field. `description`/`title` is the fallback for the Board case where `input` was never populated.

No caller was found that sets `input` and `description` to *different* things in a way that creates ambiguity. The SDK allows it, but that is a deliberate agent choice; `input_data` is documented as the specific execution input.

---

## Revised Implementation Scope

### Immediate fixes

#### 1. Fix agent runner `execute_task` user message

File: `isli-agent-sdk/src/isli_agent/runner/react_loop.py`

Replace:

```python
messages = [{"role": "user", "content": task_data.get("input", "")}]
```

with:

```python
def _build_task_work_order(task_data: dict) -> str:
    task_input = task_data.get("input", "")
    if task_input:
        return task_input

    title = task_data.get("title", "")
    description = task_data.get("description", "")
    if description and description != title:
        if title:
            return f"Task: {title}\n\n{description}"
        return description
    if title:
        return f"Task: {title}"
    return ""

work_order = _build_task_work_order(task_data)
messages = [{"role": "user", "content": work_order}]
```

This is the highest-impact fix and will resolve the symptom on its own.

#### 2. Properly propagate `task_description` through PII-mesh path (Option B)

Files:
- `isli-keeper/src/isli_keeper/pii_models.py` — add `task_description: str | None = None` to `SessionPrepRequest`
- `isli-keeper/src/isli_keeper/session_prep.py` — include `task_description` in `_assemble_combined_text` as a `Task:` line
- `isli-core/src/isli_core/compliance/pii_keeper_client.py` — accept and forward `task_description`
- `isli-core/src/isli_core/jobs/context_worker.py` — pass `task_description` when calling `PIIKeeperClient.session_prep()`

This avoids overloading `context_summary` with dual meanings and makes the PII path behave the same as the legacy path.

#### 3. Regression tests

- `isli-agent-sdk/tests/` — add a test that `execute_task` passes `description` to the LLM when `input` is empty, and passes `input` when it is non-empty.
- `isli-core/tests/` — verify `ContextWorker` passes `task_description` to both legacy and PII-mesh Keeper calls.
- `isli-keeper/tests/` — verify `/session-prep` includes `task_description` in the assembled context.

### Deferred to backlog

#### A. Keeper legacy `/context/inject` task-description inclusion (Bug 1)

The runner fix makes this non-critical because the work order is delivered directly in the user turn. Adding it to the system prompt is belt-and-suspenders and can be done separately.

#### B. Guard against hollow task completions

The agent can currently call `complete_task()` with a greeting. A future guard could check for suspiciously short/generic outputs or require tool usage for tasks that obviously need it. This is not in scope for the current bug.

---

## Verification Steps

1. Rebuild images from source: `docker compose up -d --build`.
2. For a non-PII agent (`pii_mesh_enabled=false`):
   - Create a Board task with title "Test" and description "Write exactly: 'TASK_RECEIVED_OK'".
   - Wait for completion.
   - Confirm output contains `TASK_RECEIVED_OK` and is not a greeting.
   - Check agent logs: `runner.turn_start` should show the user message containing the description.
3. For a PII-mesh agent (`pii_mesh_enabled=true`):
   - Repeat the same task.
   - Confirm output contains `TASK_RECEIVED_OK`.
   - Check Keeper logs: `/session-prep` should receive `task_description` and include it in context.
4. For an agent that creates sub-tasks via `create_kanban_task` with `input_data` set:
   - Confirm the sub-task receives `input` as the primary work order, not title/description.

---

## Files to Modify

| File | Change |
|------|--------|
| `isli-agent-sdk/src/isli_agent/runner/react_loop.py` | Build user message from `input` first, falling back to `description`/`title` |
| `isli-keeper/src/isli_keeper/pii_models.py` | Add `task_description` to `SessionPrepRequest` |
| `isli-keeper/src/isli_keeper/session_prep.py` | Include `task_description` in combined text |
| `isli-core/src/isli_core/compliance/pii_keeper_client.py` | Forward `task_description` to Keeper |
| `isli-core/src/isli_core/jobs/context_worker.py` | Pass `task_description` to PII session prep |
| Test files (TBD) | Regression coverage |

---

## Status

- [x] Implemented
- [x] Lint clean for changed files (`ruff`)
- [x] Unit tests added and passing
- [x] End-to-end verified in Docker Compose for both PII-off and PII-on paths

### Verification results

- **PII-off path** (`pii_mesh_enabled=false`): created task `b1a57e2c-d553-4476-aaa1-e13c70b74806` with description `Respond with the exact phrase: PII-OFF-DESCRIPTION-REACHES-AGENT-7281`; output was the exact phrase.
- **PII-on path** (`pii_mesh_enabled=true`): created task `4d3e0270-ff51-47bb-aad3-65577a2ab643` with description `Respond with the exact phrase: PII-ON-DESCRIPTION-REACHES-AGENT-9922`; output was the exact phrase.
- Agent `auto-agent-01` config was restored to `pii_mesh_enabled=false` after verification.
- Regression tests:
  - `isli-agent-sdk/tests/test_runner_task_work_order.py`: 6 passed
  - `isli-keeper/tests/test_session_prep_task_description.py`: 3 passed

## Rollback

- The runner fix alone resolves the symptom. If the PII-mesh changes cause issues, they can be reverted independently.
- No database schema changes are required for the runner fix. PII-mesh changes only add an optional field to a Pydantic model.
