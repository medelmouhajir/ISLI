## Double Persona Injection — Remove Persona from Keeper Context

### Problem
The agent's persona appears twice in the prompt stack:

1. **SDK (`isli-agent-sdk`)** — In the system prompt template (`prompts.yaml`) under `=== IDENTITY ===` as `Persona: ...`. This is rendered by `runner.py::_assemble_system_prompt()` and appears **first** in the final prompt.
2. **Keeper (`isli-keeper`)** — In the context summary under `=== AGENT IDENTITY ===` as `Persona: ...`. This is injected by the `/context/inject` endpoint and appended later in the prompt.

Because the SDK version appears first, it is the authoritative source. The Keeper duplicate wastes tokens and adds noise.

### Solution
Remove persona from the Keeper context injection pipeline entirely. The SDK is the single source of truth for agent identity.

### Files to Change

1. **`isli-keeper/src/isli_keeper/main.py`**
   - Remove `agent_persona: str | None = None` from `ContextInjectRequest`
   - Remove the `if req.agent_persona:` block from the `=== AGENT IDENTITY ===` assembly

2. **`isli-core/src/isli_core/memory/keeper_client.py`**
   - Remove `agent_persona: str | None = None` parameter from `KeeperClient.get_context_injection()`
   - Remove `"agent_persona": agent_persona` from the payload dict

3. **`isli-core/src/isli_core/jobs/context_injector.py`**
   - Remove `Agent.persona` from the SELECT statement
   - Remove `agent_persona = row[3]`
   - Re-index subsequent row variables (`agent_config` → `row[3]`, `model_routing_enabled` → `row[4]`, `secondary_models_raw` → `row[5]`, `default_provider` → `row[6]`, `default_model` → `row[7]`)
   - Remove `agent_persona=agent_persona` from the `KeeperClient.get_context_injection()` call

4. **`isli-core/src/isli_core/jobs/session_context_injector.py`**
   - Same changes as `context_injector.py`, with the same row re-indexing
   - `agent_user_id` becomes `row[8]` (was `row[9]`)

5. **`isli-core/src/isli_core/routers/agents.py`**
   - Remove `agent_persona=agent.persona` from the `KeeperClient.get_context_injection()` call (~line 533)

### No Test Changes Needed
Existing keeper tests (`test_memory_injection.py`) do not reference `agent_persona`.

### Verification
- After the change, Keeper's context summary still contains `=== AGENT IDENTITY ===` with Name / ID / Description, but **no Persona line**.
- The SDK system prompt remains the single source of truth for persona under `=== IDENTITY ===`.
- Functional behavior for agents is unchanged — they still see persona in the system prompt.
- Token usage is slightly reduced by eliminating the duplicate.
