# Plan: Update Skill Smith Prompts and Descriptions

## Goal
Refresh all LLM-facing copy for the Skill Smith trio (`test-skill`, `register-skill`, `update-skill`) so agents understand the new USR workspace-to-Core lifecycle, use the `workspace_path` parameter correctly, and always call `test_skill` before `register_skill`.

## Scope
- **Skill Smith trio only** — `test-skill`, `register-skill`, `update-skill`.
- **Hot-reloadable descriptions** — `TEST_SKILL_DEF`, `REGISTER_SKILL_DEF`, and `UPDATE_SKILL_DEF` in the SDK will load their descriptions from `prompts.yaml` like most other tools.

## Files to modify

### 1. `prompts.yaml`
Update `agent:tool_descriptions` for the three Skill Smith tools and add a workflow note to the system prompt.

- `test_skill`: describe dry-run Docker build against an agent-workspace directory that must contain `isli-skill.yaml` + `Dockerfile`; no container is started; returns build result or errors.
- `register_skill`: describe installing a USR microservice from a workspace directory after a successful `test_skill`; Core copies source, builds, runs, probes `/health`, and the calling agent becomes the skill owner.
- `update_skill`: describe updating an installed USR skill from a workspace directory using a clean sync and blue/green swap; automatic rollback if the new container fails its health probe.
- `system_prompt_template`: append a short `skill_smith_workflow` sentence that says:
  > When creating a new skill, first write the directory with `isli-skill.yaml`, `Dockerfile`, and service code, then call `test_skill`, and only call `register_skill` after `test_skill` succeeds.

### 2. `isli-core/src/isli_core/routers/skills.py`
Update the `SKILL_METADATA` entries for `test-skill`, `register-skill`, `update-skill` to match the USR wording, and add concise `hint` fields for Keeper intent classification.

### 3. `isli-agent-sdk/src/isli_agent/tools/engineering.py`
- Add a local `_get_tool_desc(name, default)` helper (same pattern as `system.py`) that loads from `prompts.yaml`.
- Replace the static `description` strings in `TEST_SKILL_DEF`, `REGISTER_SKILL_DEF`, and `UPDATE_SKILL_DEF` with `_get_tool_desc(...)` calls, keeping the new USR strings as fallbacks.
- Update the docstrings of `test_skill`, `register_skill`, and `update_skill` to match for developer clarity.

### 4. Docs
- `Docs/06-skills.md` was already refreshed in the previous task; only minor wording alignment is needed if any drift appears after the prompt edits.

## Validation
1. Unit-style check: run `isli-agent-sdk` import and verify that `_get_tool_desc('test_skill', ...)` returns the text from `prompts.yaml`.
2. Regression tests in `isli-core`:
   ```bash
   cd /home/projects/ISLI_AI/ISLI/isli-core
   python3 -m pytest tests/test_usr_skill_lifecycle.py -q
   ```
3. Lint the touched files with `ruff`.

## Deployment (Docker Compose)
1. `prompts.yaml` edits take effect after restarting agent containers (it is mounted into `agent-runner`).
2. Because `SKILL_METADATA` lives in the `core` source, rebuild and recreate Core:
   ```bash
   docker compose build --no-cache core
   docker compose up -d --force-recreate core
   ```
3. Because `engineering.py` is baked into the `agent-runner` image, rebuild it:
   ```bash
   docker compose build --no-cache agent-runner
   ```
   Any running agents must be restarted from the Board or Agent Process Manager to pick up the new SDK.

## Open questions handled
- **Scope:** Skill Smith trio only.
- **Hot-reload:** descriptions will come from `prompts.yaml`.
