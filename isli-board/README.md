# isli-board

ISLI Kanban Board — React real-time task board and session interface.

## Overview

The board is the human-facing layer of ISLI. It provides:

- **Kanban Board** (`/`) — Real-time task visualization with drag-and-drop across columns (Inbox → Assigned → In Progress → Blocked → Done → Archived)
- **Sessions** (`/sessions`) — Direct multi-agent chat interface with persistent conversations
- **Keeper Dashboard** (`/keeper`) — Live telemetry for the local Ollama sidecar
- **Agent Management** (`/agents`, `/agents/:id`) — Agent registry and detail views

## Architecture

### Shared WebSocket Context

The board uses a single shared WebSocket connection owned by `BoardSocketContext` (`src/contexts/BoardSocketContext.tsx`). All components consume events via `useBoardSocket()` instead of opening their own connections. This prevents duplicate sockets and reconnect storms.

```
BoardSocketProvider (1 useWebSocket instance)
  ├── App.tsx          → listens for task/agent/session events
  ├── useKeeperStream  → listens for keeper:inference events
  └── any future consumer
```

Configuration: `reconnectInterval: 3000`, `reconnectAttempts: 20`.

### Real-Time Data Flow

React Query (`@tanstack/react-query`) handles server state. WebSocket events update the cache surgically:

- **Tasks** — `task:created` / `task:updated` / `task:moved` events use `setQueryData` for instant UI updates without HTTP refetching.
- **Agents** — `agent:heartbeat` / `agent:online` events patch the agent list in-place.
- **Sessions** — `session:message` / `session:updated` events:
  1. Update the sessions list cache via `setQueryData` (bumping `last_activity_at`) so the sidebar timestamp refreshes.
  2. Invalidate only the detail query `['sessions', sessionId]` — the list is not refetched.

Session queries use `staleTime: 30000` with `refetchOnWindowFocus: false` and `refetchOnReconnect: false` to avoid fetch storms. Real-time freshness comes from WebSocket events, not polling.

## Tech Stack

- React 18 + TypeScript
- Vite (build)
- TailwindCSS (styling)
- react-router-dom (navigation)
- @dnd-kit/core + sortable (drag and drop)
- @tanstack/react-query (server state)
- react-use-websocket (WebSocket wrapper)
- date-fns (timestamp formatting)

## Development

```bash
cd isli-board
npm install
npm run dev          # Vite dev server on :5173
npm run build      # Production build
npm run typecheck  # tsc --noEmit
npm run lint       # ESLint
```

## Key Files

| File | Purpose |
|------|---------|
| `src/contexts/BoardSocketContext.tsx` | Shared WebSocket provider |
| `src/hooks/useSessions.ts` | Session queries + send-message mutation |
| `src/hooks/useBoardSocket.ts` | Thin re-export of context consumer |
| `src/hooks/useKeeperStream.ts` | Keeper inference log buffer |
| `src/components/SessionsPage.tsx` | Two-pane chat UI |
| `src/components/KanbanBoard.tsx` | Drag-and-drop task board |
| `src/App.tsx` | Top-level router + WebSocket event handler |

## Deployment

The board is served as static files via nginx inside a Docker container. Core API endpoints are proxied under `/api/`.

```bash
docker compose up -d --build board
```
