# Plan: Show only responding agents' sections in Council Room

## Problem
In the Council Room thread, every agent in the room gets a response card for every user message, even when the message only addresses one or two agents. Empty "Waiting for response..." cards appear for agents that were not addressed.

## Goal
Render a `CouncilResponseCard` only for agents that are actually responding to (or have responded to) the specific user message. Hide empty cards for agents not targeted by the message.

## Files to change
1. `isli-board/src/components/CouncilThread.tsx`
2. Possibly `isli-board/src/components/CouncilRoom.tsx` if we need to snapshot the addressed set at send time.

## Proposed approach

### Data sources per thread group
Each `ThreadGroup` already has:
- `group.userMessage` — the user message
- `group.replies` — map of `agent_id → RoomMessage` (final replies)
- `room.room_metadata.last_addressed_agent_ids` — sticky addressed set from the backend for the most recent message
- `streamingAgentIds` — agents currently processing the latest message

### Filtering rule
For each thread group:
1. Always show a card for an agent that has a final reply (`group.replies[agent.id]` exists).
2. For the **most recent / in-flight** group, also show cards for agents that are:
   - Currently streaming (`streamingAgentIds`)
   - In the room's `last_addressed_agent_ids` (backend's resolved addressed set for the last message)
   - If `last_addressed_agent_ids` is empty, fall back to the whole room roster (matches Core fallback).
3. For older groups, only show agents with actual replies. Do not show empty cards.
4. Only consider `streamingAgentIds` for the most recent group to avoid ghosting older groups.

### Layout change
Update the grid `grid-cols-*` classes to be based on the **filtered** agent count, not the full room roster count.

### Optional UX enhancement
In `CouncilRoom`, snapshot the local `addressedAgentIds` at the moment `handleSend` is called and pass it to `CouncilThread` as `pendingAddressedIds`. Use that for the latest group until the backend's `room_metadata.last_addressed_agent_ids` is refreshed, so cards appear instantly before the API round-trip. If this proves unnecessary, we can rely on `room_metadata` alone.

## Trade-offs
- **Using `room_metadata.last_addressed_agent_ids` only**: Simpler, but there is a brief window after send where the latest message's cards might not appear until the room refetches.
- **Snapshotting local state**: Cards appear immediately, but adds a small prop and state to keep in sync. Recommended for better UX.

## Recommended option
Implement both: snapshot `pendingAddressedIds` at send time and pass it down; in `CouncilThread`, prefer `pendingAddressedIds` for the latest group, then fall back to `room_metadata.last_addressed_agent_ids`, then whole roster.

## Testing / verification
1. Type `@harvey hi` in a room with Donna + Harvey → only Harvey card appears while waiting.
2. Type `@donna @harvey hi` → both cards appear.
3. Type plain `hi` with no selection → whole roster cards appear (fallback).
4. After responses arrive, older message groups show only agents that actually replied.
5. Run `npm run typecheck` in `isli-board`.
6. Rebuild `board` Docker image and hard-refresh browser.
