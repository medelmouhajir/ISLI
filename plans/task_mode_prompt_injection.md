# Plan: Task-Mode System Prompt Injection

## Goal
Prevent agents from greeting/status-carding their way out of Kanban tasks (e.g., Harvey marking a research task done without calling the research skill or writing the deliverable).

## Architecture Clarification
- The `system_prompt_template` lives in `prompts.yaml` and is loaded by **both** Core and the Agent SDK.
- **Rendering happens in the SDK**, in `isli-agent-sdk/src/isli_agent/runner.py::_assemble_system_prompt()`.
- There is **no `current_task_id` column on the `agents` table**. Task mode is determined per-execution by whether the SDK is inside `_execute_task(task_data)`.
- Therefore, the block must be injected by the SDK when it is assembling the prompt for a task, not by Core.

## Proposed Implementation

### 1. Add `task_execution_block` to `prompts.yaml`
File: `/home/projects/ISLI_AI/ISLI/prompts.yaml`

Under the existing `agent:` section, add a new key `task_execution_block`. Wording is adapted to actual SDK behavior (the SDK calls `complete_task` automatically on the LLM’s final non-tool text, so we do not tell the model to “call complete_task” as a tool):

```yaml
agent:
  system_prompt_template: |
    ... existing template stays unchanged ...

  task_execution_block: |
    ## Kanban Task Execution Rules (non-negotiable)

    You are currently executing an assigned Kanban task. The task title, description, and relevant history are in the === CONTEXT === section above.

    TASK MODE rules:
    1. Read the task title and description carefully — that is your work order.
    2. Execute the work: call the relevant skills, search tools, or APIs described in the task.
    3. If the task requires a file deliverable, you MUST call file-write (or shared_file_write / promote_output) before producing your final response.
    4. Your final non-tool text response will be saved as the task result and the task will be marked done.
    5. NEVER render a greeting card, status card, or "I am ready" message as your final task output.
    6. NEVER rely on ui_components, send_message, or notify_user as a substitute for doing the actual work.
    7. If you are unsure how to proceed, create a sub-task or mark the task blocked; do NOT mark it done.

    Violation check (run mentally before each tool call):
    "Am I about to call ui_components, send_message, or notify_user without having done the substantive work yet?" → STOP. Do the work first.
```

### 2. Modify SDK `_assemble_system_prompt()`
File: `isli-agent-sdk/src/isli_agent/runner.py`

Signature change:
```python
def _assemble_system_prompt(
    self,
    context_summary: str,
    session_info: dict | None = None,
    relevant_skills: list[str] | None = None,
    task_mode: bool = False,
) -> str:
```

After the template is rendered and before the UI-rendering instructions are appended, conditionally append the block:

```python
# Inject task-mode execution discipline
if task_mode:
    block = prompts.get("agent", {}).get("task_execution_block")
    if block:
        system_prompt += "\n\n" + block
    else:
        logger.warning("runner.task_execution_block_missing")
```

This keeps the block close to the core instructions and above optional session/peer/UI addenda.

### 3. Enable task mode in `_execute_task()`
File: `isli-agent-sdk/src/isli_agent/runner.py`

Change the call at line ~1249 from:
```python
system_prompt = self._assemble_system_prompt(context_summary, relevant_skills=relevant_skills)
```
to:
```python
system_prompt = self._assemble_system_prompt(
    context_summary, relevant_skills=relevant_skills, task_mode=True
)
```

Leave the session-message path (`_handle_session_message`) at line ~1561 with the default `task_mode=False`, so chat behavior is unaffected.

### 4. Add unit tests
File: `isli-agent-sdk/tests/test_runner_sync.py`

Add a test that confirms the block is injected only in task mode and that it contains the key behavioral anchors:

```python
def test_assemble_system_prompt_includes_task_block_in_task_mode(self, agent_config):
    runner = AgentRunner(agent_config, "http://localhost:8000")
    prompt = runner._assemble_system_prompt("Task context", task_mode=True)
    assert "## Kanban Task Execution Rules" in prompt
    assert "NEVER render a greeting card" in prompt
    assert "MUST call file-write" in prompt
    assert "=== IDENTITY ===" in prompt  # base template still present

def test_assemble_system_prompt_omits_task_block_in_chat_mode(self, agent_config):
    runner = AgentRunner(agent_config, "http://localhost:8000")
    prompt = runner._assemble_system_prompt("Chat context", task_mode=False)
    assert "## Kanban Task Execution Rules" not in prompt
```

Also test the existing `test_assemble_system_prompt_includes_tools` still passes with the default `task_mode=False`.

### 5. Rebuild and redeploy
Because the Agent SDK is baked into the `isli-agent-runner` Docker image (per project memory: user rejects `docker cp`, rebuild only), update both files and run:

```bash
cd /home/projects/ISLI_AI/ISLI
docker compose up -d --build agent-runner
```

If any agent containers (e.g., `isli-agent-harvey`) were spawned from a previous image, recreate them so they pick up the new SDK:

```bash
docker compose up -d --force-recreate isli-agent-harvey
```

`prompts.yaml` is mounted into the Core/Keeper/agent-runner containers, so edits to the YAML itself do not require an image rebuild — but the SDK code change does.

## Optional Follow-Ups (out of scope for this plan)

1. **Core-side deliverable guard**: Add a check in `complete_task` / task move to `done` that inspects `skill_runs` and `attachments`. If the task description mentions a file deliverable but no `file-write`/`shared_file_write`/`promote_output` skill run exists, reject the move or warn. This is a stronger safety net but requires parsing intent and is more invasive.

2. **SDK prompt hot-reload**: The SDK caches `prompts.yaml` with `lru_cache(maxsize=1)`. Today, editing `prompts.yaml` via the Board UI only reloads Core/Keeper; agent runners need a restart to see changes. A future improvement could add an internal endpoint or WebSocket event to clear the SDK cache.

3. **Per-agent opt-out**: Some agents may legitimately be chat-only. If needed later, add `config.task_execution_block_enabled` (default `true`) so the block can be disabled per agent.

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Block is too aggressive for conversational tasks | Only injected in `_execute_task`; session/chat path unchanged |
| Missing `task_execution_block` key in prompts.yaml | Code falls back to warning; no crash |
| Old agent-runner images still running | Force-recreate agent containers after rebuild |
| Tests fail because prompts.yaml not present in test env | Ensure test uses same relative-path lookup as `prompts_loader.py` (repo root) or mock `get_prompts` |

## Acceptance Criteria
- [ ] `prompts.yaml` contains `agent.task_execution_block` with the behavioral rules.
- [ ] SDK `_assemble_system_prompt` accepts `task_mode` and appends the block when `True`.
- [ ] `_execute_task` passes `task_mode=True`.
- [ ] Session/chat path continues to use `task_mode=False`.
- [ ] New unit tests pass; existing tests still pass.
- [ ] Agent-runner image is rebuilt and agent containers are recreated in Docker Compose.
- [ ] Re-running a similar task (e.g., Moroccan-law research) results in the agent calling the skill and writing a file instead of returning a greeting card.
