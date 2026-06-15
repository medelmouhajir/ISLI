# Plan: Admin Cleanup Endpoint for Stale `known_agent_ids` + Board Button

## Goal

Give admins a one-click way to remove deleted/non-existent agent IDs from every surviving agent's `known_agent_ids` (the "DELEGATION_MAP"). This fixes pre-existing staleness that the delete-time scrubber cannot reach retroactively.

## Changes

### 1. Backend: New admin cleanup endpoint in `isli-core/src/isli_core/routers/agents.py`

Add a response model and endpoint at the bottom of the agents router:

```python
class CleanupPeerRefsOut(BaseModel):
    cleaned: int
    affected_agent_ids: list[str]


@router.post("/cleanup-peer-refs", response_model=CleanupPeerRefsOut)
async def cleanup_peer_references(
    db: AsyncSession = Depends(get_db),
    admin: str = Depends(require_admin_auth),
):
    """Remove all deleted/non-existent agent IDs from every non-deleted agent's known_agent_ids."""
    result = await db.execute(select(Agent))
    all_agents = result.scalars().all()

    valid_ids = {a.id for a in all_agents if a.deleted_at is None}
    affected_agent_ids: list[str] = []

    for agent in all_agents:
        if agent.deleted_at is not None:
            continue
        peer_ids = _safe_json(agent.known_agent_ids, []) or []
        cleaned = [pid for pid in peer_ids if pid in valid_ids]
        if cleaned != peer_ids:
            agent.known_agent_ids = cleaned
            agent.updated_at = datetime.now(UTC)
            affected_agent_ids.append(agent.id)

    if affected_agent_ids:
        await db.commit()
        for agent_id in affected_agent_ids:
            await EventManager.emit(
                "agent:config_updated",
                {"agent_id": agent_id, "fields": ["known_agent_ids"]},
            )
            await ContextCache.invalidate_for_agent(agent_id)

    logger.info("agents.cleanup_peer_refs", cleaned=len(affected_agent_ids))
    return CleanupPeerRefsOut(
        cleaned=len(affected_agent_ids),
        affected_agent_ids=affected_agent_ids,
    )
```

This reuses the same patterns as `_scrub_peer_references` added earlier.

### 2. Backend: Test in `isli-core/tests/test_api_agents.py`

Add:

```python
    @pytest.mark.asyncio
    async def test_cleanup_peer_refs_removes_deleted_agents(self, client: AsyncClient):
        """POST /v1/agents/cleanup-peer-refs should strip deleted agent IDs from peers."""
        await client.post("/v1/agents", json={
            "id": "cleanup-a",
            "name": "Cleanup A",
            "model_provider": "ollama",
            "model_id": "qwen3:1.7b",
        })
        await client.post("/v1/agents", json={
            "id": "cleanup-b",
            "name": "Cleanup B",
            "model_provider": "ollama",
            "model_id": "qwen3:1.7b",
        })
        # A lists both B and a never-existing ID
        await client.put("/v1/agents/cleanup-a", json={
            "known_agent_ids": ["cleanup-b", "ghost-agent"],
        })

        # Delete B
        await client.delete("/v1/agents/cleanup-b")

        # Run cleanup
        resp = await client.post("/v1/agents/cleanup-peer-refs", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert data["cleaned"] == 1
        assert "cleanup-a" in data["affected_agent_ids"]

        resp = await client.get("/v1/agents/cleanup-a")
        assert resp.status_code == 200
        assert resp.json()["known_agent_ids"] == []

        # Cleanup
        await client.delete("/v1/agents/cleanup-a")
```

### 3. Board UI: Add API helper in `isli-board/src/lib/api.ts`

Add `postJSON` already exists. If we need a typed response:

```typescript
export async function postJSON<T>(path: string, body: unknown): Promise<T>
```

No new helper needed; reuse `postJSON<CleanupPeerRefsOut>('/v1/agents/cleanup-peer-refs', {})`.

### 4. Board UI: Add hook in `isli-board/src/hooks/useAgents.ts`

Add:

```typescript
export function useCleanupPeerRefs() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => postJSON<{ cleaned: number; affected_agent_ids: string[] }>(
      '/v1/agents/cleanup-peer-refs',
      {}
    ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agents'] })
    },
  })
}
```

Need to import `postJSON` in this file.

### 5. Board UI: Add cleanup card to `SecuritySettingsPage.tsx`

Add a new admin action card below the E-Stop block:

```tsx
const cleanupPeerRefs = useCleanupPeerRefs()
const [isConfirmingCleanup, setIsConfirmingCleanup] = useState(false)

const handleCleanupPeerRefs = () => {
  cleanupPeerRefs.mutate(undefined, {
    onSettled: () => setIsConfirmingCleanup(false),
  })
}
```

JSX card (same visual style as E-Stop block):

```tsx
<div className="bg-bg-surface border border-border-dim rounded-xl p-5">
  <div className="flex items-center justify-between gap-4 mb-4">
    <div className="flex items-center gap-3">
      <div className="w-8 h-8 rounded-lg bg-bg-elevated text-text-muted flex items-center justify-center">
        <Users className="w-4 h-4" />
      </div>
      <div>
        <h2 className="text-xs font-display font-bold uppercase tracking-widest text-text-primary">
          Clean Delegation Map
        </h2>
        <p className="text-[10px] text-text-muted mt-0.5">
          Remove deleted or unknown agents from every agent's peer/delegation list.
        </p>
      </div>
    </div>
    <button
      onClick={() => setIsConfirmingCleanup(true)}
      disabled={cleanupPeerRefs.isPending}
      className="px-4 py-2 rounded-lg text-[11px] font-display font-bold uppercase tracking-wider transition-all bg-accent-cyan text-black hover:opacity-90"
    >
      {cleanupPeerRefs.isPending ? (
        <RefreshCw className="w-3.5 h-3.5 animate-spin" />
      ) : (
        'Run Cleanup'
      )}
    </button>
  </div>

  {cleanupPeerRefs.isSuccess && (
    <div className="text-[11px] text-text-secondary">
      Cleaned {cleanupPeerRefs.data.cleaned} agent(s):
      {' '}{cleanupPeerRefs.data.affected_agent_ids.join(', ') || 'none'}
    </div>
  )}
</div>

{isConfirmingCleanup && (
  <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
    <div className="bg-bg-surface border border-border-dim rounded-2xl p-6 max-w-md w-full shadow-2xl animate-in fade-in zoom-in duration-200">
      <div className="flex items-center gap-3 text-accent-cyan mb-4">
        <AlertTriangle className="w-6 h-6" />
        <h3 className="text-lg font-display font-bold">Clean Delegation Map?</h3>
      </div>
      <p className="text-sm text-text-secondary mb-6 leading-relaxed">
        This will remove every deleted or unknown agent ID from all agents'
        <code>known_agent_ids</code> lists. Running agents will receive a
        config update and reload their peer map automatically.
      </p>
      <div className="flex gap-3 justify-end">
        <button
          onClick={() => setIsConfirmingCleanup(false)}
          className="px-4 py-2 rounded-xl text-xs font-bold text-text-muted hover:bg-bg-elevated transition-colors"
        >
          Cancel
        </button>
        <button
          onClick={handleCleanupPeerRefs}
          className="px-4 py-2 rounded-xl text-xs font-bold bg-accent-cyan text-black hover:opacity-90 transition-all"
        >
          Run Cleanup
        </button>
      </div>
    </div>
  </div>
)}
```

Import `Users` from `lucide-react` and `useState` is already imported.

### 6. Update `SettingsPage.tsx`

No change needed unless we want to mention the new Security action. The Security card already covers "Authentication, access control, and audit settings"; adding delegation-map cleanup there is appropriate.

## Verification

1. Backend:
   ```bash
   cd isli-core
   .venv/bin/python -m pytest tests/test_api_agents.py::TestAgentsAPI::test_cleanup_peer_refs_removes_deleted_agents -v
   ```

2. Board:
   ```bash
   cd isli-board
   npm run typecheck
   npm run lint
   ```

## Rollout

Because the endpoint is additive and read/write only on admin request, it is safe to deploy immediately. After the build:

```bash
docker compose up -d --build --force-recreate core board
```

Then open Board → Settings → Security → "Clean Delegation Map" → confirm. The UI will show how many agents were cleaned, and running agents will receive `agent:config_updated` events so their runners reload the peer list without restart.
