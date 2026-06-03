# 05 — Dashboard & Kanban

## Overview

The ISLI Board has evolved from a single-view Kanban into a multi-layered orchestration suite. The system landing page is now a high-density **System Dashboard**, while the **Kanban Board** has moved to a dedicated route to focus on task execution.

---

## System Dashboard (`/`)

The Dashboard provides real-time telemetry and health monitoring for the entire ISLI node. It follows the **Industrial** design anchor, prioritizing precision and tabular data.

### Key Telemetry
- **Blackboard Load**: Real-time count of total tasks and active (running) orchestration units.
- **Agent Swarm**: Online agent count vs. total registered units.
- **Resource Burn**: Financial telemetry showing total USD spend and cumulative unit cycles.
- **Keeper Latency**: Average latency of the background intelligence layer and model readiness status.
- **Service Pulse**: 1px left-border signal indicators (Acid Lime = Nominal, Amber = Degraded) for Core API, Redis, Keeper, Vector DB, and Audit Log.
- **Inference Log**: A live stream of the latest 6 inferences across all agents, showing model targets, latency (ms), and token counts.

---

## Observability Hub (`/logs`)

The Observability Hub serves as a centralized high-fidelity technical interface for system telemetry. It follows the **Industrial** design anchor, utilizing semantic signal colors and real-time status indicators.

### Log Categories
1.  **EXECUTION.LOG**: Live stdout/stderr capture from all active autonomous agents (Redirects to `/agents`).
2.  **AUDIT.TRAIL**: Cryptographically signed records of all system-level state changes.
3.  **MEMORY.JOURNALS**: Journal diffs for Episodic and Semantic memory hydration events (Redirects to `/keeper`).
4.  **CORE.SYSTEM**: Internal logs for `isli-core`, Redis, and PostgreSQL telemetry.
5.  **TASK.HISTORY**: Full lifecycle tracking of task transitions and owner handoffs (Redirects to `/kanban`).
6.  **GATEWAY.LOGS**: Inbound/outbound traffic logs for Telegram, WhatsApp, Web, and SDK channels.

### Design Features
- **Live Tickers**: Each category displays a real-time status (streaming, idle, archived) and key metrics (e.g., `LIVE`, `SYNCED`, `99.9% UP`).
- **Technical immersion**: Includes industrial labeling, a "System Entropy" footer, and interactive scanline effects on hover.
- **Background Ticker**: Uses a large `LOGS_INFRA` background decoration to anchor the technical context.

---

## Kanban Board (`/kanban`)

The Kanban board remains ISLI's **central nervous system for human oversight**.

```
┌──────────┬──────────┬─────────────┬──────────┬─────────┬──────┬──────────┐
│  INBOX   │ ASSIGNED │ IN PROGRESS │  REVIEW  │ BLOCKED │ DONE │ ARCHIVED │
├──────────┼──────────┼─────────────┼──────────┼─────────┼──────┼──────────┤
│ [card]   │ [card]   │ [card]      │ [card]   │ [card]  │[card]│          │
│ [card]   │          │             │          │         │[card]│          │
│          │          │             │          │         │      │          │
└──────────┴──────────┴─────────────┴──────────┴─────────┴──────┴──────────┘
```

Columns are fixed. Cards move left to right: `Inbox → Assigned → In Progress → Review → Done`.

### The "Review" Column (Violet)
The **Review** status is a critical human-in-the-loop gating mechanism. 

*   **Role**: A safety buffer between agent execution and system adoption. It handles high-risk actions like autonomous skill registration or deep delegation.
*   **Logic**: 
    *   Agents explicitly move tasks to `review` via the `move_task` tool after completing complex or high-risk sub-tasks.
    *   The system prevents agent sessions from being garbage collected while a task is in `review`, ensuring context remains "warm" while waiting for human validation.
    *   Tasks with `needs_human_approval: true` automatically land here.
*   **Human Action**: Operators must inspect the output in the Task Detail Modal and manually drag the card to **Done** to signify approval.

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
  scheduled_at?: string;           // One-time or next occurrence
  cron_expression?: string;        // Standard 5-field cron
  last_triggered_at?: string;      // Last time recurring task spawned a clone
  attachments: TaskAttachment[];
  retain_attachments: boolean;
}

interface TaskAttachment {
  name: string;
  path: string;
  size_bytes: number;
  attached_by: string;
  attached_at: string; // ISO timestamp
}
```

### Task Attachments

Tasks can carry file attachments from the agent's workspace. When an agent completes a task and produces an output file, it may attach the file to the task card so humans or downstream agents can retrieve it.

**Attachment flow:**
1. Agent writes a file to its workspace via `file-write` skill.
2. Agent calls `POST /v1/tasks/{task_id}/attachments/attach` with `source_path` and `target_path`.
3. Core API proxies to `isli-workspace` `/attachments/attach`, which copies the file into the `_attachments/{task_id}` scope.
4. Core appends a `TaskAttachment` record to `task.attachments`.
5. The Board's **Task Detail Modal** renders the attachment list with file name, size, and download button.

**Retention:** When a task moves to `done`, the `retain_attachments` flag (default `true`) determines whether the attachment files are kept in the workspace scope. If `false`, files are purged during the next archival sweep.

**Download:** The Board calls `GET /download?scope=attachment&scope_id={task_id}&path={attachment.path}` via the Core proxy to serve the file to the user.

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

The board subscribes to a **single shared WebSocket** stream from Core API via `BoardSocketContext` (`isli-board/src/contexts/BoardSocketContext.tsx`). All consumers (Kanban, Sessions, Keeper dashboard) read from one connection — no duplicate sockets.

Event types:

```typescript
type BoardEvent =
  | { type: "task:created";    task: Task }
  | { type: "task:updated";    task_id: string; changes: Partial<Task> }
  | { type: "task:moved";      task_id: string; from: TaskStatus; to: TaskStatus }
  | { type: "agent:heartbeat"; agent_id: string; status: AgentStatus; anomaly?: string }
  | { type: "agent:online";    agent_id: string }
  | { type: "agent:offline";   agent_id: string }
  | { type: "session:updated"; session_id: string }
  | { type: "session:message"; session_id: string; agent_id: string }
  | { type: "session:stream_event"; session_id: string; event_type: string; data: object }
  | { type: "keeper:event";    event_type: string; payload: object }
  | { type: "system:alert";    severity: string; message: string }
```

**Streaming events** (`session:stream_event`) carry live agent turn telemetry:
- `token_delta` — partial text chunks for the `StreamingMessageBubble`
- `tool_call` — skill invocation started/done for the `ToolCallBar`
- `phase_start` / `phase_end` — context injection, checkpoint recovery for the `ProcessTracePane`
- `cost_report` — token usage after the turn completes

### Update Strategy

React Query caches server state. WebSocket events update the cache **surgically** to avoid HTTP refetch storms:

- **Tasks** — `setQueryData(['tasks'], ...)` patches the list in-place.
- **Agents** — `setQueryData(['agents'], ...)` patches the agent record.
- **Sessions** — `setQueryData(['sessions'], ...)` bumps `last_activity_at` on the affected session; only `['sessions', session_id]` is invalidated for a detail refetch.

Session queries use `staleTime: 30000` with `refetchOnWindowFocus: false` and `refetchOnReconnect: false`. Real-time freshness comes from WebSocket events, not polling.

WebSocket configuration: `reconnectInterval: 3000`, `reconnectAttempts: 20`.

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
| Open Cost Analytics | Sidebar → "Costs" or navigate to `/costs` |

---

## Delegation Visualization

When Agent A delegates to Agent B, the board shows a **linked card pair**:

```
[DONE] Research task #123  ──delegates──▶  [IN PROGRESS] Analysis task #124
       Agent: Research                              Agent: Analysis
```

Parent and child cards are visually connected with an arrow. Clicking either shows the delegation chain.

---

## Sessions & Chat Interface

Beyond the Kanban board, the `isli-board` provides a dedicated **Sessions** page for direct multi-agent interaction.

### Purpose
The Sessions page allows users to:
- **Direct Messaging**: Chat with any online agent in real-time.
- **Session Persistence**: Continue existing conversations or start new ones.
- **Human-to-Agent Loop**: Manually inject messages into the agent's context.

### Interaction Flow
1. **Selection**: User chooses an existing session from the list or starts a new one by selecting an agent.
2. **Inbound Message**: When a user sends a message, the session is set to `pending_context`.
3. **Context Injection**: `isli-core` (via `SessionContextInjectorWorker`) injects episodic and semantic memory from the Keeper.
4. **Agent Notification**: Core API broadcasts a `session:message` event via WebSockets.
5. **Agent Reply**: The assigned agent processes the request (ReAct loop) and replies via `POST /v1/sessions/{id}/reply`.
6. **Real-time Update**: The UI receives a `session:updated` event and refreshes the chat view.

### UI Features
- **Two-Pane Layout**: Left pane for conversation history/selection, right pane for the active chat.
- **Status Indicators**: Real-time visualization of whether an agent is "thinking" or "injecting context".
- **Responsive Shell**: The interface uses a fixed viewport (`h-screen`) to ensure the chat container is independently scrollable.
- **Live Streaming** (2026-05-31): When the agent's `streaming_mode` is not `silent`, the chat renders live telemetry:
  - `StreamingMessageBubble` — monospace text with a blinking cursor, fed by `token_delta` events
  - `ToolCallBar` / `ToolCallCard` — skill cards that transition from spinner to checkmark as `tool_call` events arrive
  - `ProcessTracePane` — collapsible timeline showing `phase_start`, `turn_start`, `tool_call`, `cost_report` events
  - Draft persistence: reconnecting clients fetch the current draft via `GET /v1/sessions/{id}/draft` and resume mid-stream

---

## Channel Conversations Manager (`/chats`)

A dedicated page for managing external channel conversations (Telegram, WhatsApp, etc.).

### Purpose
The Chats page allows operators to:
- **Browse by Agent + Channel**: Select an agent and one of its assigned channels to view all active conversations.
- **Client List**: Grouped by `user_id`, showing the latest message preview, relative timestamp, and aggregate status across all sessions for that client.
- **Full Message History**: Loads both live and archived messages via `GET /v1/sessions/{id}/history`, sorted chronologically.
- **Admin Reply**: Send messages directly into any active session from the dashboard.
- **Closed Session Visibility**: Includes closed sessions (`include_closed=true`) so operators can review completed conversations.

### Interaction Flow
1. **Filters**: Select an agent, then one of its channels.
2. **Client List**: Sessions are grouped by `user_id`; the most recently active session per client drives the preview.
3. **Conversation View**: Clicking a client loads the full combined history and allows admin replies.
4. **Real-time**: `session:updated` and `session:message` WebSocket events invalidate `chat-sessions` and `session-history` query keys.

### Route
Navigate to `/chats` from the sidebar (between Sessions and Costs).

---

## Recurring Tasks & Upcoming View (Added 2026-06-02)

ISLI supports both one-time scheduling and robust recurring tasks via cron expressions.

### Scheduling Logic
- **One-time**: Setting `scheduled_at` moves a task to `pending` status. The `SchedulerWorker` activates it when the time arrives.
- **Recurring**: Setting `cron_expression` enables the **Full Scheduler**. 
    - When a recurring task triggers, the system **clones** the parent task into a new execution instance (linked via `parent_task_id`).
    - The original parent task is rescheduled for its next occurrence using `croniter`.
    - This preserves the "Template" task while providing a full execution history.
- **Idempotency**: The `last_triggered_at` field prevents double-triggering within the same polling window.

### UI Features
- **Upcoming Filter**: The Kanban header includes an "Upcoming" date filter that displays future-scheduled tasks and recurring parents.
- **Cron Builder**: The Task Detail Modal features a visual Cron Builder with common presets (Daily, Weekly, etc.) and real-time validation.
- **Execution History**: Recurring tasks show a history list of all their past clones and their individual statuses.

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

## Agent Self-Delegation (Added 2026-05-24)

Agents are no longer restricted to human-assigned tasks. Using the `create-kanban-task` skill, agents can now programmatically create sub-tasks or delegate work to other specialists.

### Protocol Rules:
1. **Parent-Child Link**: Any task created by an agent MUST set its `parent_task_id` to the current task's ID to maintain the delegation chain.
2. **Peer Awareness**: An agent can only delegate to agents listed in its `known_agent_ids` (configured per-agent in the Board UI). The Core API rejects delegation tasks where `assigned_to` is not in the creator's known-agent set.
3. **Cycle Detection**: The Core API (`delegation.py`) automatically blocks any delegation that would create a circular dependency (e.g., Agent A → Agent B → Agent A).
4. **Depth Limits**: Core enforces a maximum delegation depth (default: 3). Tasks at depth 2 or higher are automatically marked for `needs_human_approval` in their payload.

### Discovery Before Delegation

When an agent encounters a task outside its domain, it can discover suitable peers at runtime:

```python
# AgentRunner ReAct turn
peers = await list_agents()          # SDK tool → GET /v1/agents
researcher = next(p for p in peers if "web-research" in p["skills"])

# Or use the dedicated peers endpoint (returns only known agents)
peers = await get_agent_info(agent_id)  # resolves known_agent_ids into metadata
```

The Board UI's **"Agents this agent can delegate to"** card makes this visible to operators, who toggle peer relationships as team topology changes.

---

## Tech Stack (Board Frontend)

```
React 18 + TypeScript
Vite (build)
TailwindCSS (styling)
react-router-dom (navigation)
@dnd-kit/core (drag and drop)
@tanstack/react-query (server state)
WebSocket (native browser API)
date-fns (timestamp formatting)
```

No heavy UI libraries. No real-time framework dependencies (pure WebSocket).

---

## Board Backend Endpoints

The board interacts with the `isli-core` API. All resource endpoints are versioned under `/v1`.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/tasks` | GET | List tasks (with filters) |
| `/v1/tasks` | POST | Create task |
| `/v1/tasks/{id}` | GET | Get task detail |
| `/v1/tasks/{id}` | PATCH | Update task (status, assignment) |
| `/v1/agents` | GET | List agents and their statuses |
| `/v1/agents/{id}/peers` | GET | Resolve an agent's `known_agent_ids` into full metadata |
| `/v1/sessions` | GET | List chat sessions (filters: `agent_id`, `channel`, `user_id`, `include_closed`, `limit`) |
| `/v1/sessions` | POST | Create a new chat session |
| `/v1/sessions/{id}` | GET | Fetch session details and live message history |
| `/v1/sessions/{id}/history` | GET | Fetch full conversation history (archived + live, sorted) |
| `/v1/sessions/{id}/message` | POST | Send a human message to an agent session |
| `/ws/board` | WS | Real-time event stream |
| `/v1/shared-workspaces` | GET | List shared workspaces (owner/member scoped) |
| `/v1/shared-workspaces` | POST | Create a shared workspace |
| `/v1/shared-workspaces/{id}` | GET | Get workspace details |
| `/v1/shared-workspaces/{id}` | PUT | Update workspace (owner or admin) |
| `/v1/shared-workspaces/{id}` | DELETE | Soft-delete workspace (owner or admin) |
| `/v1/shared-workspaces/{id}/members/{agent_id}` | POST | Add member (owner or admin) |
| `/v1/shared-workspaces/{id}/members/{agent_id}` | DELETE | Remove member (owner or admin) |
| `/v1/shared-workspaces/{id}/promote` | POST | Promote file into shared workspace |

---

## Shared Workspaces (`/shared-workspaces`)

Shared workspaces are collaborative filesystem scopes that multiple agents can read and write together. Unlike per-agent workspaces, a shared workspace has an explicit **owner** and a **member list**.

### Workspace Model

```typescript
interface SharedWorkspace {
  id: string;
  name: string;
  description?: string;
  owner_id: string;
  members: string[];        // agent_ids
  quota_bytes: number;      // default 500MB
  created_at: string;
  updated_at: string;
}
```

### Board UI

- **List page** (`/shared-workspaces`): Cards for each workspace the current user owns or is a member of. Owners see a "Delete" button.
- **Detail page** (`/shared-workspaces/:id`): Shows workspace info, owner badge, member list with add/remove controls, and a file browser (reads the `_shared/{workspace_id}` scope via the workspace service).

### Access Control

- **Owner** — full CRUD, can add/remove members, can update name/description/quota.
- **Member** — can read/write files inside the shared scope, can call `/promote` to copy files in.
- **Non-member** — cannot see the workspace in list or detail endpoints.

### Quota Enforcement

The workspace service enforces `quota_bytes` per shared workspace on every write, upload, and promote operation. Exceeding the quota returns HTTP `413`.

### Promote Flow

Agents (or the Board) can copy a file from an agent or attachment scope into a shared workspace:

```
Agent / Board
  → POST /v1/shared-workspaces/{id}/promote
    { agent_id, source_scope, source_scope_id, source_path, target_path, delete_source?, quota_bytes? }
  → Core proxies to workspace service /shared/promote
  → Workspace service validates access, checks quota, copies/moves the file
```

## Kanban as Communication Protocol

The most important design decision: **agents do not call each other directly**. All agent-to-agent requests become task cards.

This means:
- Every agent interaction is inspectable by the user
- Every delegation can be paused or redirected
- The board is a complete audit trail
- There are no hidden "internal" API calls between agents

This eliminates the MAST failure category of *inter-agent misalignment* — because there is no direct inter-agent communication to misalign.

---

## Settings Hub (`/settings`)

The Settings Hub provides a centralized interface for managing global configuration, provider API keys, and local Ollama model selection.

### Settings Grid

| Card | Route | Status | Description |
|------|-------|--------|-------------|
| Model API Keys | `/settings/providers` | Active | Manage LLM provider API keys (Anthropic, OpenAI, Google, Ollama Cloud) and permitted models per provider. |
| Keeper Settings | `/settings/keeper` | Active | Manage local Ollama models for the Keeper — view active `gen`/`embed` models, pull permitted alternatives, and monitor model readiness. |
| General | `#` | Coming soon | Global application preferences and defaults. |
| Security | `#` | Coming soon | Authentication, access control, and audit settings. |
| Notifications | `#` | Coming soon | Alert routing, webhooks, and communication preferences. |

### Keeper Settings (`/settings/keeper`)

The Keeper Settings page interfaces with `GET /v1/model-management/status` and `POST /v1/model-management/pull` on Core, which proxy to the Keeper's `/dashboard` and `/admin/pull` endpoints with internal JWT authentication.

**Features:**
- **Current Model Display**: Shows active `gen` and `embed` models from Keeper telemetry.
- **Permitted Model Grid**: Lists all allowed models per slot with visual active-state indicators.
- **One-Click Pull**: Download and switch models directly from the UI (blocked if active sessions exist).
- **Real-Time Status**: Displays Keeper health and Ollama readiness alongside model information.

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