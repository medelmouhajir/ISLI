# 05 — Kanban Board

## Purpose

The Kanban board is ISLI's **central nervous system for human oversight**. It is not just a pretty UI — it is the primary communication protocol between agents, and the primary visibility layer for the user.

**Design priority**: Real-time agent task visibility.

---

## Board Layout

```
┌──────────┬──────────┬─────────────┬─────────┬──────┬──────────┐
│  INBOX   │ ASSIGNED │ IN PROGRESS │ BLOCKED │ DONE │ ARCHIVED │
├──────────┼──────────┼─────────────┼─────────┼──────┼──────────┤
│ [card]   │ [card]   │ [card]      │ [card]  │[card]│          │
│ [card]   │          │             │         │[card]│          │
│          │          │             │         │      │          │
└──────────┴──────────┴─────────────┴─────────┴──────┴──────────┘
```

Columns are fixed. Cards move left to right (with exception: BLOCKED can move back to IN PROGRESS).

---

## Task Card Structure

Each card on the board represents one **Task**:

```typescript
interface Task {
  id: string;                   // UUID
  title: string;                // Short description
  description: string;          // Full task details
  type: TaskType;               // user_request | delegation | system | scheduled
  status: TaskStatus;           // inbox | assigned | in_progress | blocked | done | archived
  priority: 1 | 2 | 3 | 4 | 5; // 1=critical, 5=low
  agent_id?: string;            // Assigned agent
  created_by: string;           // user | agent_id | system
  created_at: string;           // ISO timestamp
  updated_at: string;
  started_at?: string;
  completed_at?: string;
  input: string;                // What the agent received
  output?: string;              // What the agent produced
  channel?: string;             // telegram | whatsapp | web | etc.
  parent_task_id?: string;      // For delegation chains
  child_task_ids?: string[];    // Subtasks
  blocked_reason?: string;      // Why it's blocked
  token_usage?: {
    input_tokens: number;
    output_tokens: number;
    model: string;
  };
  tags?: string[];
}
```

---

## Agent Status Panel

Above the Kanban columns, a real-time **Agent Status Bar** shows each registered agent:

```
┌─────────────────────────────────────────────────────────────┐
│ AGENTS                                                       │
│  ● Research  [ACTIVE - task #123]    Last HB: 12s ago       │
│  ● Sales     [IDLE]                  Last HB: 8s ago        │
│  ● Code      [BLOCKED]  ⚠️ Stuck 5m  Last HB: 32s ago       │
│  ○ Legal     [OFFLINE]               Last HB: 2m ago        │
└─────────────────────────────────────────────────────────────┘
```

Colors: ● green = healthy, ● yellow = warning, ● red = anomaly, ○ gray = offline

---

## Real-Time Events (WebSocket)

The board subscribes to a WebSocket stream from Core API. Events:

```typescript
type BoardEvent =
  | { type: "task:created";    task: Task }
  | { type: "task:updated";    task_id: string; changes: Partial<Task> }
  | { type: "task:moved";      task_id: string; from: TaskStatus; to: TaskStatus }
  | { type: "agent:heartbeat"; agent_id: string; status: AgentStatus; anomaly?: string }
  | { type: "agent:online";    agent_id: string }
  | { type: "agent:offline";   agent_id: string }
  | { type: "keeper:event";    event_type: string; payload: object }
  | { type: "system:alert";    severity: string; message: string }
```

All events arrive in real-time. No polling.

---

## Human-in-the-Loop Actions

The board supports direct human intervention at any point:

| Action | How |
|--------|-----|
| Reassign task | Drag card to a different agent column (or use menu) |
| Pause agent | Click agent → "Pause" — agent stops accepting new tasks |
| Cancel task | Click task card → "Cancel" |
| Edit task input | Click task card → "Edit" — updates input before agent picks it up |
| Create task manually | "+" button in any column |
| Unblock task | Click blocked card → "Mark unblocked" |
| View token usage | Click any done card → expand "Token Usage" section |
| View full conversation | Click any card → "View Thread" |
| Pin to memory | Click done card → "Pin to Memory" → stores in Tier 3 |

---

## Delegation Visualization

When Agent A delegates to Agent B, the board shows a **linked card pair**:

```
[DONE] Research task #123  ──delegates──▶  [IN PROGRESS] Analysis task #124
       Agent: Research                              Agent: Analysis
```

Parent and child cards are visually connected with an arrow. Clicking either shows the delegation chain.

---

## Filtering and Search

The board supports:
- Filter by agent
- Filter by channel
- Filter by status
- Filter by date range
- Full-text search across task titles and descriptions
- Tag filter

---

## Tech Stack (Board Frontend)

```
React 18 + TypeScript
Vite (build)
TailwindCSS (styling)
@dnd-kit/core (drag and drop)
@tanstack/react-query (server state)
WebSocket (native browser API)
date-fns (timestamp formatting)
```

No heavy UI libraries. No real-time framework dependencies (pure WebSocket).

---

## Board Backend Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/tasks` | GET | List tasks (with filters) |
| `/api/tasks` | POST | Create task |
| `/api/tasks/{id}` | GET | Get task detail |
| `/api/tasks/{id}` | PATCH | Update task (status, assignment) |
| `/api/agents` | GET | List agents and their statuses |
| `/ws/board` | WS | Real-time event stream |

---

## Kanban as Communication Protocol

The most important design decision: **agents do not call each other directly**. All agent-to-agent requests become task cards.

This means:
- Every agent interaction is inspectable by the user
- Every delegation can be paused or redirected
- The board is a complete audit trail
- There are no hidden "internal" API calls between agents

This eliminates the MAST failure category of *inter-agent misalignment* — because there is no direct inter-agent communication to misalign.

---

## Kanban Board Gaps (2026-05-11 Research)

The following gaps were identified during a parallel 12-agent research review:

### Critical
- **Task state race conditions** — concurrent PATCH updates from agents and humans lack optimistic locking.
- **No event schema registry** — `BoardEvent` TypeScript unions are unversioned; breaking changes silently break clients.

### High
- **Missing backpressure on event bus** — Redis Streams broadcast to all WebSocket clients with no `MAXLEN`, consumer groups, or circuit breakers.
- **No SLOs/SLIs defined** — no p50/p95/p99 latency targets for task creation-to-completion.
- **No `Failed` Kanban column** — tasks that error have no DLQ, retry count, or human retry action.
- **No queue depth limit per agent** — agents can accumulate unlimited ASSIGNED tasks.

### Medium
- **Delegation chains not linked in distributed traces** — `parent_task_id` exists but no trace linking in OpenTelemetry.
- **No message ordering guarantee** — concurrent processing could append session messages out of order.
- **No delivery confirmation/retry for outbound messages** — failed platform API calls silently drop responses.

> See `Memory/ISLI-Research-Report.md` for full details and recommendations.