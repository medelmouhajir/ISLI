# Plan: Fix Agent Container Env Var Injection from DB

## Problem

`AgentProcessManager._spawn_docker()` and `_spawn_subprocess()` build environment variables purely from Core's `os.environ`. They never query the database for the agent's resolved API key or model configuration. This creates a disconnect:

- The Board UI saves provider API keys to the `llm_providers` table.
- The `/config` endpoint correctly resolves the key (`agent.api_key` → `llm_providers.api_key`).
- But `process_manager.py` passes `OLLAMA_API_KEY=""` into every new container because Core's env var is empty.

While the SDK's `start_agent.py` fetches `/config` and populates `AgentConfig.api_key`, this is fragile:
1. If `/config` is temporarily unreachable at startup, the agent falls back to env vars and starts unauthenticated.
2. The subprocess backend inherits an empty env var, which LiteLLM may read and use as an explicit empty key.
3. Per-provider `api_base` is not supported at all because there's no `api_base` field in `AgentConfigOut`/`AgentConfig`.

## Current State of kimi-02

- `llm_providers.ollama.api_key` IS populated in the DB.
- The running `isli-agent-kimi-02` container fetched `/config` at startup and got the key.
- LiteLLM tests from inside the container confirm `api_key` kwarg + `https://ollama.com` work for simple prompts.
- **Yet the agent times out after exactly 120s on every turn.** This suggests the prompt + model combination may be pushing past the hardcoded 120s `litellm_timeout`, OR the 30-tool payload is causing Ollama Cloud to queue/throttle. The env-var fix alone may not resolve the timeout, but it is a necessary architectural correction.

## Changes

### 1. `isli-core/src/isli_core/services/process_manager.py`

**Add `_resolve_agent_env(agent_id: str) -> dict[str, str]`**
- Query DB for `Agent` record.
- Resolve `api_key`: `agent.api_key` → fallback to `llm_providers` row for `agent.model_provider`.
- Resolve `api_base`: check `llm_providers` row for `api_base` (new column, or fallback to Core's `os.getenv`).
- Map provider → env var:
  - `ollama` → `OLLAMA_API_KEY`
  - `openai` → `OPENAI_API_KEY`
  - `anthropic` → `ANTHROPIC_API_KEY`
  - `google` / `gemini` → `GEMINI_API_KEY`
  - `deepseek` → `DEEPSEEK_API_KEY`
- Return a dict of env keys to inject.

**Modify `_spawn_docker()`**
- After building base `env` dict, merge `_resolve_agent_env(agent_id)` on top, overriding `os.getenv` fallbacks.
- Log the resolved provider and whether a key was injected (mask the key).

**Modify `_spawn_subprocess()`**
- Similarly merge resolved env into the subprocess environment before `asyncio.create_subprocess_exec`.

### 2. `isli-core/src/isli_core/routers/agents.py`

- Add `api_base: str | None = None` to `AgentConfigOut` schema.
- In `get_agent_config()`, resolve `api_base` from `llm_providers.api_base` if available, else from Core settings/env.

### 3. `isli-core/src/isli_core/models.py`

- Add `api_base: Mapped[str | None] = mapped_column(Text, nullable=True)` to `LlmProvider` table.
- This enables per-provider base URLs in the Board UI instead of relying solely on Core's `OLLAMA_API_BASE` env var.

### 4. `isli-agent-sdk/src/isli_agent/models.py`

- Add `api_base: Optional[str] = None` to `AgentConfig`.

### 5. `isli-agent-sdk/src/isli_agent/runner.py`

- In the `api_key` env-var block (currently only sets `GEMINI_API_KEY`), add a provider map so all providers get their env var set:
  ```python
  provider_env_map = {
      "ollama": "OLLAMA_API_KEY",
      "openai": "OPENAI_API_KEY",
      "anthropic": "ANTHROPIC_API_KEY",
      "google": "GEMINI_API_KEY",
      "deepseek": "DEEPSEEK_API_KEY",
  }
  env_var = provider_env_map.get(_normalize_provider(self.config.model_provider))
  if env_var:
      os.environ[env_var] = self.config.api_key
  ```
- If `self.config.api_base`, pass `api_base=self.config.api_base` into `completion_kwargs`.

### 6. `isli-agent-sdk/examples/start_agent.py`

- Pass `api_base=data.get("api_base")` into `AgentConfig(...)`.

### 7. Board UI / Settings (optional future)

- Add `api_base` input field to the LLM provider settings form so users can set per-provider base URLs.
- Not required for this fix but makes the `api_base` column useful.

## Rollout / Verification

1. **DB migration** (Core): Add `api_base` column to `llm_providers`.
2. **Rebuild** `isli-core` image and restart the `core` container.
3. **Rebuild** `isli-agent-runner` image (SDK changes are baked in).
4. Kill `isli-agent-kimi-02` → Core respawns it with injected env vars.
5. Verify: `docker exec isli-agent-kimi-02 env | grep OLLAMA_API_KEY` shows the masked key.
6. Send a test message. If it still times out at 120s, the next step is to increase `litellm_timeout` in the agent config or switch to a faster model.

## Files to Touch

| File | Change |
|------|--------|
| `isli-core/src/isli_core/services/process_manager.py` | Add `_resolve_agent_env()`, merge into both spawn methods |
| `isli-core/src/isli_core/routers/agents.py` | Add `api_base` to `AgentConfigOut`, resolve it |
| `isli-core/src/isli_core/models.py` | Add `api_base` to `LlmProvider` |
| `isli-agent-sdk/src/isli_agent/models.py` | Add `api_base` to `AgentConfig` |
| `isli-agent-sdk/src/isli_agent/runner.py` | Set env vars for all providers; pass `api_base` to `acompletion` |
| `isli-agent-sdk/examples/start_agent.py` | Pass `api_base` into `AgentConfig` |

## Trade-offs

- **DB query per spawn:** Adds one async query per container spawn. Spawns are infrequent (agent start/restart), so this is negligible.
- **Hardcoded provider→env map:** 5 providers. Maintainable and matches LiteLLM conventions. Can be extended.
- **DB migration required:** Adding `api_base` to `llm_providers` needs an Alembic migration or schema-on-startup since other services manage their own schemas.

## Open Question for User

The 120s timeout on `kimi-k2.6` may be a separate issue from the missing env var. Do you also want to:
- Increase the default `litellm_timeout` from 120s to 300s?
- Switch `kimi-02` to a smaller/faster model (e.g., `qwen3:1.7b` local) while keeping `kimi-k2.6` as a fallback?
