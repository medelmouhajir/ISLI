# Plan: Strict Reasoning Budgets (with model-aware enforcement)

## Current state

- `Agent.reasoning_budget` and `Task.reasoning_token_budget` columns already exist in `isli-core/src/isli_core/models.py`.
- `isli_core/budget.py` checks `reasoning_tokens > agent.reasoning_budget` per turn, but it is not exposed in any API schema, not returned to the agent runner, and not surfaced in the Board UI.
- The agent runner (`isli-agent-sdk/src/isli_agent/runner.py`) reports `reasoning_tokens` back to Core after each inference, but it never receives the budget, so it cannot proactively cap reasoning at the LLM API layer.
- LiteLLM parameter names for reasoning caps differ by provider (`reasoning_effort`, `max_completion_tokens`, `extra_body.thinking.budget_tokens`), and no provider mapping exists today.
- `isli-board/src/components/AgentModelPage.tsx` has "Lifetime Limit" and "Per-Turn Cap" fields, but no dedicated "Reasoning Budget" field.

## Goal

Make reasoning budgets **strict** by enforcing them in three places:

1. **LLM API layer** — runner passes provider-specific caps so the model physically cannot exceed the budget.
2. **Pre-flight check** — runner estimates reasoning cost before calling the model and fails fast if the prompt will obviously blow the budget.
3. **Post-flight hard stop** — Core pauses the agent if the reported `reasoning_tokens` ever exceeds the configured budget.

Plus an enhanced idea: **model-aware defaults and reasoning-effort mapping** — when an operator selects `o1`, `o3-mini`, `claude-sonnet-4-6-thinking`, etc., the Board auto-suggests a sensible default reasoning budget and maps the numeric budget to the provider's qualitative effort level (low/medium/high).

## Enhanced feature set

| Feature | Why |
|---|---|
| Per-agent `reasoning_budget` | Primary ask: cap hidden thinking tokens per turn. |
| Model-aware default budgets | `o1`/`o3`/`claude-opus-4-7-thinking` get safe defaults so trivial tasks do not burn thousands of reasoning tokens. |
| Provider-specific LLM params | OpenAI: `max_completion_tokens` + `reasoning_effort`; Anthropic: `extra_body.thinking.budget_tokens`; DeepSeek/Gemini where supported. |
| Pre-flight prediction | SDK estimates reasoning tokens before the call and short-circuits, avoiding wasted API spend. |
| Cumulative reasoning tracking | New `Agent.reasoning_tokens_used` column so Core can also enforce lifetime reasoning caps and show burn-rate dashboards. |
| Budget-aware model fallback | If the selected reasoning model cannot satisfy the budget, prefer a non-reasoning model from the agent's secondary models. |
| Board UI control | Add a "Reasoning Budget" field with badge + default suggestion on `AgentModelPage`. |
| Per-task inheritance | Tasks without an explicit `reasoning_token_budget` inherit from the agent's `reasoning_budget`. |

## Design decisions

1. **Per-turn vs. lifetime reasoning budget**
   - `Agent.reasoning_budget` is a **per-turn** cap on hidden reasoning tokens.
   - New `Agent.reasoning_tokens_used` is a **lifetime** accumulator, charged alongside `token_used`.
   - This mirrors the existing `token_budget` / `token_used` split.

2. **Where the cap is applied**
   - Runner applies the API-level cap before calling LiteLLM (proactive).
   - Core's `check_budget` raises if the reported usage violates the budget (reactive).
   - Both are required: reactive catches provider non-compliance; proactive prevents most violations.

3. **Cross-package dependency**
   - Do **not** import `isli_core` from `isli_agent_sdk` (violates container isolation per project memory).
   - Keep a small, duplicated list of reasoning models in the SDK, or add the list to the `AgentConfig` payload from Core.
   - Decision: **add `is_reasoning_model` bool to `AgentConfigOut`** so the runner does not need to duplicate the detector.

4. **Default values**
   - Only set defaults when the selected model is a reasoning model and the operator leaves the field empty.
   - Defaults: `o1`/`o3` 8 000, `claude-opus-4-7-thinking` 6 000, `o3-mini`/`claude-sonnet-4-6-thinking`/`deepseek-r1` 4 000, `gemini-2.0-flash-thinking` 3 000.

5. **Reasoning-effort mapping**
   - Derive `reasoning_effort` from the budget as a fraction of the model's default max.
   - < 25 % of default → `low`; 25–75 % → `medium`; > 75 % → `high`.
   - Anthropic does not support effort strings; use explicit `budget_tokens` instead.

6. **Migration**
   - Add Alembic migration for `Agent.reasoning_tokens_used`.
   - Native dev SQLite requires either deleting `isli-core/isli_dev.db` or running `alembic upgrade head`.

## Implementation phases

### Phase 1 — Core plumbing & hard enforcement

Files:
- `isli-core/src/isli_core/models.py`
  - Add `reasoning_tokens_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)`.
- `isli-core/src/isli_core/budget.py`
  - Remove the misleading `current_reasoning = agent.token_used` line.
  - Update `charge_tokens` to increment `reasoning_tokens_used`.
  - Add `reasoning_budget` to `BudgetEngine.*` projections.
  - Add `check_reasoning_budget` helper that sets `status="paused"` and `status_reason` on violation.
- `isli-core/src/isli_core/routers/agents.py`
  - Add `reasoning_budget` to `AgentCreate`, `AgentUpdate`, `AgentOut`, `AgentConfigOut`.
  - Emit `agent:config_updated` when `reasoning_budget` changes.
- `isli-core/alembic/versions/20260617_001_add_reasoning_tokens_used.py`
  - Add the new column.

### Phase 2 — Agent runner proactive enforcement

Files:
- `isli-agent-sdk/src/isli_agent/models.py`
  - Add `reasoning_budget: Optional[int] = None` and `is_reasoning_model: bool = False` to `AgentConfig`.
- `isli-agent-sdk/src/isli_agent/runner.py`
  - Add `_apply_reasoning_budget(self, completion_kwargs, provider, model_id)`:
    - OpenAI `o*` models: `max_completion_tokens = min(output_cap, reasoning_budget + output_reserve)` and `reasoning_effort` mapped from budget.
    - Anthropic thinking models: `extra_body={"thinking": {"type": "enabled", "budget_tokens": reasoning_budget}}`.
    - Other providers: pass `reasoning_effort` if supported, else log unsupported.
  - Add pre-flight guard: use `len(messages) // 4` heuristic to predict input tokens; if predicted reasoning > budget, fail with a user-facing message and do not call the model.
  - Hook `_apply_reasoning_budget` into both `_execute_task` and `_execute_session_message` before `_model_with_fallback`.

### Phase 3 — Model-aware defaults & Board UI

Files:
- `isli-board/src/types/index.ts`
  - Add `reasoning_budget: number | null` and `is_reasoning_model: boolean` to `Agent`.
- `isli-board/src/components/AgentModelPage.tsx`
  - Add "Reasoning Budget" input to the "Limits and Safety" card.
  - Show a small reasoning-model badge next to the field when `is_reasoning_model` is true.
  - Auto-fill a default when the user picks a reasoning model and the field is empty.
- `isli-board/src/components/CreateAgentPage.tsx`
  - Add `reasoning_budget` field and model-aware default.
- `isli-core/src/isli_core/routers/agents.py`
  - Compute `is_reasoning_model` in `AgentOut` / `AgentConfigOut` using `ReasoningDetector`.

### Phase 4 — Budget-aware fallback & task inheritance

Files:
- `isli-core/src/isli_core/cost/tiering.py`
  - Replace the hard-coded `< 5000` heuristic with a comparison of the model's predicted reasoning need vs. `reasoning_budget`.
  - Downgrade from a reasoning model to a non-reasoning secondary model when the budget is too tight.
- `isli-core/src/isli_core/budget.py`
  - In `check_budget`, if `task.reasoning_token_budget` is `None` and the agent has `reasoning_budget`, use the agent's budget for the task.

### Phase 5 — Tests & validation

- `isli-core/tests/test_reasoning_budgets.py`
  - Add tests for cumulative `reasoning_tokens_used` charging.
  - Add tests for task inheritance of agent reasoning budget.
  - Add tests for Board-compatible create/update payloads.
- `isli-agent-sdk/tests/`
  - Add unit tests for `_apply_reasoning_budget` with OpenAI and Anthropic kwargs.
  - Add pre-flight prediction test.
- `isli-board/src/components/`
  - Update any existing component tests; add model-aware default test if test harness exists.
- Run `ruff`, `mypy`, and `pytest` in affected packages.

### Phase 6 — Docker Compose deployment

- Rebuild `isli-core`, `isli-agent-sdk` (built into agent-runner image), and `isli-board` images.
- Run `alembic upgrade head` inside the `core` container (or as a one-shot migration job) for Postgres deployments.
- Native dev: delete `isli-core/isli_dev.db` and restart services so SQLite schema is recreated.

## Decisions confirmed

1. ✅ **Add `Agent.reasoning_tokens_used` lifetime counter.**
   - Enables cumulative reasoning caps and burn-rate dashboards.
   - Adds one Alembic migration for the new column.

2. ✅ **Runner tries to downgrade first, then fails.**
   - If a reasoning model cannot satisfy the budget, the runner switches to a non-reasoning secondary model.
   - If no fallback works or the pre-flight prediction still exceeds the budget, the runner fails with a user-facing message.
   - Core still hard-pauses the agent on post-flight violations.

3. ✅ **Auto-defaults use `ReasoningDetector.REASONING_MODELS`.**
   - `o1`/`o3` → 8 000
   - `claude-opus-4-7-thinking` → 6 000
   - `o3-mini`/`claude-sonnet-4-6-thinking`/`deepseek-r1` → 4 000
   - `gemini-2.0-flash-thinking` → 3 000

## Expected behavior after implementation

- An agent configured with `model_id=o3-mini` and `reasoning_budget=2000` will receive LiteLLM kwargs that cap reasoning to ~2 000 tokens.
- If a user sends a very long prompt that the runner predicts will need 5 000 reasoning tokens, the runner returns an error immediately without calling the API.
- If the provider reports more reasoning tokens than the budget, Core pauses the agent and logs the reason.
- The Board shows a "Reasoning Budget" field that auto-suggests 4 000 when `o3-mini` is selected, and a badge that says "Reasoning Model".

## Success criteria

- `pytest isli-core/tests/test_reasoning_budgets.py` passes with new tests.
- Agent runner unit tests verify OpenAI and Anthropic reasoning params.
- Board `npm run typecheck` passes with the new `reasoning_budget` field.
- Full stack boots after rebuild; creating an agent with `model_id=o3-mini` sets a default reasoning budget.
