# Plan: Agent Restart with Live Mount + Rebuild

## Goal
Make the Board UI "Restart" action immediately pick up code changes in development (Approach 1), and add an explicit "Rebuild & Restart" action that rebuilds the agent-runner image before starting (Approach 2).

## Context
- The agent-runner container is spawned dynamically by Core via the Docker socket.
- The Board UI restart is currently client-side: `stop` → poll → `start`.
- The dev-mode live SDK volume mount is dead code because `process_manager.py` requires `not self._use_docker`, which is always `False` inside the Core container.

---

## Changes

### 1. Core — Fix dev-mode live SDK volume mount
**File:** `isli-core/src/isli_core/services/process_manager.py`

- Import `IS_DEV` from `isli_core.config`.
- In `_spawn_docker()`, change the volume mount condition:
  ```python
  if IS_DEV and settings.agent_sdk_host_path:
      volumes[settings.agent_sdk_host_path] = {"bind": "/app/src", "mode": "ro"}
  ```
  This removes the broken `not self._use_docker` guard and mounts the host `isli-agent-sdk/src` into the agent container over `/app/src`.
- Rationale: `PYTHONPATH=/app/src` and the editable install inside the image will continue to resolve imports from the live host source.

### 2. Core — Add image rebuild method
**File:** `isli-core/src/isli_core/services/process_manager.py`

- Add `async def rebuild_image(self) -> None:` that:
  1. Reads `settings.agent_runner_build_context` (host path to SDK root).
  2. Validates the Docker client is available.
  3. Runs `self._docker.images.build(path=..., dockerfile="Dockerfile", tag=settings.agent_runner_image, rm=True)` via `asyncio.to_thread`.
  4. Streams build log lines through `structlog`.
  5. Re-raises on failure so the caller can update DB status.

### 3. Core — Add restart endpoint
**File:** `isli-core/src/isli_core/routers/agents.py`

- Add `POST /{agent_id}/restart` with query param `rebuild: bool = False`.
- Logic:
  1. Look up agent; 404 if missing.
  2. Call `pm.terminate(agent_id)`; set DB status to `stopped`; commit.
  3. If `rebuild`:
     - Validate `settings.agent_runner_build_context` is set; 400 if not.
     - Set DB status to `rebuilding`; commit.
     - Kick off `asyncio.create_task(_rebuild_and_start(pm, agent_id))`.
     - Return `{"status": "rebuilding", "agent_id": agent_id}` immediately.
  4. If not `rebuild`:
     - Call `pm.spawn(agent_id)`.
     - Set DB status to `starting`; commit.
     - Return `{"status": "starting", "agent_id": agent_id}`.
- Add background helper `_rebuild_and_start(pm, agent_id)`:
  1. `await pm.rebuild_image()`.
  2. `await pm.spawn(agent_id)`.
  3. Open a manual DB session and set status to `starting`.
  4. On any exception, set status to `stopped` with `status_reason` and log.

### 4. Core config — Add build context setting
**File:** `isli-core/src/isli_core/config.py`

- Add `agent_runner_build_context: str | None = None` to `Settings`.

### 5. Docker Compose — Expose build context host path
**File:** `docker-compose.override.yml`

- Under `services.core.environment`, add:
  ```yaml
  AGENT_RUNNER_BUILD_CONTEXT: ${PWD}/isli-agent-sdk
  ```
- Keep `AGENT_SDK_HOST_PATH: ${PWD}/isli-agent-sdk/src` as-is (used for live mount).

### 6. Board UI — Wire new endpoint and add rebuild action
**File:** `isli-board/src/components/AgentDetailPage.tsx`

- Replace the current client-side `handleRestart` (stop/poll/start) with a direct call:
  ```typescript
  await postJSON(`/v1/agents/${id}/restart`, {})
  ```
- Add `handleRebuildAndRestart`:
  ```typescript
  await postJSON(`/v1/agents/${id}/restart?rebuild=true`, {})
  ```
- Add a second button next to "Restart Agent":
  - Label: "Rebuild & Restart"
  - Icon: `Hammer` (or similar from lucide-react; import it).
  - Style: outlined/secondary to distinguish from plain restart.
  - Disabled while `restarting` or `agent.status === 'rebuilding'`.
- Update the auto-refresh `useEffect` to also poll when `agent?.status === 'rebuilding'` (so the UI transitions to `starting` → `online` automatically).
- Update the Restart button disabled state to also cover `agent.status === 'rebuilding'`.

### 7. Board UI — Status badge
**File:** `isli-board/src/components/StatusBadge.tsx` (if it exists)

- Add a "rebuilding" case so the badge renders correctly while the image is building.

---

## Trade-offs & Risks

| Concern | Mitigation |
|---|---|
| Volume mount replaces container `/app/src` with host source; container editable-install `.egg-info` is in `/app/` and untouched. | Verified: `PYTHONPATH=/app/src` + egg-link resolves correctly. |
| Rebuild endpoint returns immediately; user must trust background task. | UI polls agent status every 3s while `rebuilding`/`starting`, so progress is visible. |
| Background rebuild task could fail silently. | `_rebuild_and_start` catches exceptions, writes `status_reason` to DB, and logs via `structlog`. |
| Concurrent restart + rebuild requests could race. | `_spawn_docker` defensively removes stale containers by name; low-probability race, acceptable for dev. |
| Production exposure of rebuild endpoint. | `agent_runner_build_context` is `None` in production unless explicitly set; endpoint returns 400 if unset and rebuild requested. |

---

## Verification steps after implementation

1. **Live mount:** Edit `isli-agent-sdk/src/isli_agent/runner.py`, click "Restart Agent" in Board UI. The agent should pick up the change immediately without any `docker build`.
2. **Rebuild:** Add a `print` to `isli-agent-sdk/Dockerfile` or change `requirements.txt`, click "Rebuild & Restart". The UI should show "Rebuilding..." briefly, then the agent comes online with the new image.
3. **Fallback:** Call `/restart?rebuild=true` without `AGENT_RUNNER_BUILD_CONTEXT` configured → expect 400.

---

## Files touched
- `isli-core/src/isli_core/config.py`
- `isli-core/src/isli_core/services/process_manager.py`
- `isli-core/src/isli_core/routers/agents.py`
- `docker-compose.override.yml`
- `isli-board/src/components/AgentDetailPage.tsx`
- `isli-board/src/components/StatusBadge.tsx` (if exists)
