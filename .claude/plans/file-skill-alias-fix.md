# Fix `file-search` / `file-describe` skill name alias gap

## Problem

Agent logs show:

```
runner.tool_not_found  skill=file-search  normalized=file_search
runner.tool_not_found  skill=file-describe  normalized=file_describe
```

Core registers workspace skills as `file-search` and `file-describe` (see `isli-core/src/isli_core/routers/skills.py` `SKILL_REGISTRY`).
The SDK normalizes hyphenated skill names (`-` → `_`), then looks up the result in `SKILL_TOOL_REGISTRY` or via `SKILL_NAME_ALIASES`.

- `file-search` → `file_search` (not a registry key)
- `file-describe` → `file_describe` (not a registry key)

The SDK registry keys are `search_workspace_file` and `describe_workspace_file`.
`SKILL_NAME_ALIASES` already maps similar Core/SDK mismatches (e.g. `web_browse_navigate` → `browser_navigate`) but is missing these two.

## Scope

- `isli-agent-sdk/src/isli_agent/tools/__init__.py` — add aliases
- `isli-agent-sdk/tests/test_tools_workspace.py` — add regression test for auto-registration with `file-search` / `file-describe`
- Optionally add a coverage test that iterates a canonical list of Core skill names and asserts each resolves to a registry key or alias
- `isli-agent-sdk` — run `pytest`, `ruff`, `mypy`
- Docker Compose — rebuild `agent-runner` image with `--no-cache`, restart all agents, verify logs

## Implementation

1. Add to `SKILL_NAME_ALIASES` in `isli-agent-sdk/src/isli_agent/tools/__init__.py`:

   ```python
   "file_search": "search_workspace_file",
   "file_describe": "describe_workspace_file",
   ```

2. Add regression test `TestAgentRunnerWorkspaceTools::test_auto_register_file_search_and_describe`:

   - Create `AgentConfig` with `skills=["file-search", "file-describe"]`
   - Call `await runner._auto_register_tools_from_skills()`
   - Assert `search_workspace_file` and `describe_workspace_file` are in tool definitions
   - Assert no `runner.tool_not_found` warning is emitted (capture logs)

3. (Optional) Add `test_all_core_skills_resolve` that imports a static list of Core skill names, normalizes each, and asserts each normalized name is either in `SKILL_TOOL_REGISTRY` or `SKILL_NAME_ALIASES`. This prevents future alias gaps.

4. Validation:

   ```bash
   cd isli-agent-sdk
   pytest
   ruff check .
   ruff check . --fix
   mypy src/isli_agent
   ```

5. Deployment:

   ```bash
   docker compose build --no-cache agent-runner
   docker compose up -d agent-runner
   # Restart each running agent via Core API so they pick up the new image
   for agent in butler coder-01 donna harvey sara auto-agent-01; do
     curl -s -k -X POST "https://isli.mangati.ma/api/v1/agents/$agent/restart?rebuild=false" \
       -H "Authorization: Bearer $ADMIN_API_KEY"
   done
   ```

6. Verification:

   - `docker compose ps` shows agent containers healthy
   - `docker logs --tail=20 isli-agent-...` shows `runner.tool_registered` for `file-search` / `file-describe` and no `runner.tool_not_found`

## Risks / Trade-offs

- **Minimal change**: just two alias entries. No Core or skills-service changes required.
- **Alternative**: expose tool metadata from Core for `file-search` / `file-describe` so `fetch_dynamic_tools` can register them dynamically. That is larger scope and less consistent with how other static workspace skills are handled.
- **Alternative**: rename SDK tools to `file_search` / `file_describe`. Breaks existing calls, tests, and docs; rejected.

## Backwards Compatibility

- The alias only adds new resolution paths; existing `AgentConfig(skills=["search_workspace_file"])` or direct `add_tool("search_workspace_file", ...)` calls remain unchanged.
- `filter_by_relevance` also uses `SKILL_NAME_ALIASES`, so Keeper-classified `file-search` will now correctly keep `search_workspace_file` in the active tool set.
