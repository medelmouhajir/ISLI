# Plan: Fix Kanban tasks completing with only a greeting

## Problem Statement

Tasks created from the Board UI are marked `done`, but their output is a generic greeting/status message instead of actually doing the requested work. The task description appears to never reach the agent.

## Root Cause (two related bugs)

### Bug 1: Keeper `/context/inject` drops the task description

- Core sends `task_description` to Keeper for context injection (`isli-core/src/isli_core/routers/tasks.py:282`, `isli-core/src/isli_core/memory/keeper_client.py:25-45`).
- Keeper's `/context/inject` (`isli-keeper/src/isli_keeper/main.py:462-594`) uses `task_description` **only** to run a semantic memory search (lines 470-496).
- The returned `context_summary` is assembled from agent identity, session journal, recent messages, memories, and peer agents — **but the task description itself is never included**.
- Result: the agent's system prompt `=== CONTEXT ===` block has no information about what it is supposed to do.

### Bug 2: Agent runner uses the wrong field as the user work order

- Board-created tasks populate `title` and `description`; `input` defaults to `""` (`isli-core/src/isli_core/models.py:102`, `isli-board/src/components/CreateTaskModal.tsx:35-44`).
- Agent runner `ReActLoop.execute_task` builds the user message from `task_data.get("input", "")` (`isli-agent-sdk/src/isli_agent/runner/react_loop.py:201`).
- Because `input` is empty, the LLM receives an empty user message on top of a context summary that also lacks the task.
- The agent therefore has no actionable instruction and falls back to a greeting or status card, then `complete_task()` marks the task `done`.

### Secondary issue: PII-mesh path also loses the task description

- When `agent.config.pii_mesh_enabled` is true, Core calls `PIIKeeperClient.session_prep()` (`isli-core/src/isli_core/jobs/context_worker.py:315-340`) but does **not** pass `task_description` as a user message or in `context_summary`.
- The unified `/session-prep` endpoint (`isli-keeper/src/isli_keeper/session_prep.py:209-344`) therefore never sees the task either, so both `original_context_summary` and the scrubbed version omit it.

## Proposed Fix

### 1. Include the task description in Keeper's context summary (legacy `/context/inject`)

File: `isli-keeper/src/isli_keeper/main.py`

In `/context/inject`, when `req.task_description` is provided, prepend a `=== CURRENT TASK ===` block to `context_parts` (before other context). This makes the work order visible in the agent's system prompt regardless of session state.

```python
if req.task_description:
    context_parts.append(f"=== CURRENT TASK ===\n{req.task_description}")
```

### 2. Pass the task description through the PII-mesh path (`/session-prep`)

Files:
- `isli-core/src/isli_core/jobs/context_worker.py`
- `isli-keeper/src/isli_keeper/session_prep.py` (optional, if the client-side change is enough)

Option A (recommended, minimal):
- In `_call_keeper`, when `pii_mesh_enabled` is true, set the request's `context_summary` to the task description if no session context exists, or append it.
- This reuses the existing `context_summary` channel and avoids changing Keeper's API.

Option B (cleaner long-term):
- Add a `task_description` field to `SessionPrepRequest`, pass it from Core, and have `_assemble_combined_text` include it as a `task: ...` line.
- Requires updating `isli-keeper/src/isli_keeper/pii_models.py` and the Core PII client.

**Recommended approach:** Option A for now. The PII path already receives `context_summary` from the session; for tasks without a session, setting it to the task description ensures the work order is injected. For tasks with a session, append the task description to the existing summary.

### 3. Build the agent runner's user message from `description`/`title`, not `input`

File: `isli-agent-sdk/src/isli_agent/runner/react_loop.py`

Change the user message construction in `execute_task` from:

```python
messages = [{"role": "user", "content": task_data.get("input", "")}]
```

to:

```python
task_title = task_data.get("title", "")
task_description = task_data.get("description", "")
work_order = task_description or task_title or task_data.get("input", "")
if task_title and task_description and task_description != task_title:
    work_order = f"Task: {task_title}\n\n{task_description}"
elif task_title and not task_description:
    work_order = f"Task: {task_title}"

messages = [{"role": "user", "content": work_order}]
```

This guarantees the LLM receives the actual work order even if Keeper context injection is delayed or empty.

### 4. Add regression tests

Add or update tests in:
- `isli-agent-sdk/tests/test_runner_sync.py` or a new `test_runner_tasks.py` — verify `execute_task` passes `description` to the LLM payload when `input` is empty.
- `isli-core/tests/` (context worker / tasks) — verify `task_description` reaches Keeper request payload.
- `isli-keeper/tests/` (if any) — verify `/context/inject` returns a summary containing the task description.

## Verification Steps

1. Rebuild the Docker images from source (`docker compose up -d --build`) per project policy (no `docker cp`).
2. Create a Kanban task from the Board with a description like "Write a one-sentence summary of project X".
3. Wait for context injection and agent processing.
4. Confirm the task output is the requested work, not a greeting.
5. Check agent logs for the `runner.turn_start` event and confirm the user message contains the task description.

## Files to Modify

| File | Change |
|------|--------|
| `isli-keeper/src/isli_keeper/main.py` | Add `=== CURRENT TASK ===` block to `/context/inject` when `task_description` is present |
| `isli-core/src/isli_core/jobs/context_worker.py` | Ensure PII-mesh path forwards `task_description` into `session_prep` context |
| `isli-agent-sdk/src/isli_agent/runner/react_loop.py` | Use `description`/`title` instead of `input` for task user message |
| Test files (TBD) | Regression coverage |

## Rollback

Each change is independent. If issues arise, the agent-runner change (Bug 2) alone is sufficient to fix the greeting symptom, while the Keeper changes improve context quality.
