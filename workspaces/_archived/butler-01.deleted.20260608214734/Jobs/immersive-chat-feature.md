# Immersive Chat — Feature Specification
**ISLI AI Board · WAN Solutions**
*Product Feature · UI/UX + Agent Protocol*

---

## Overview

Immersive Chat is an alternative view mode for the existing conversation session interface in the ISLI AI Board. When activated, the chat expands to full-page, and a structural protocol is established between the frontend and the active agent — allowing the agent to respond not just in plain text, but in rich, structured UI components rendered natively inside the conversation.

The feature has two co-dependent layers: the **frontend renderer**, which understands a set of pre-defined block types and knows how to display them, and the **agent tool protocol**, which gives the agent the ability to compose and emit those blocks as structured tool calls. Neither layer has value without the other.

The net result is a chat session that can function as a lightweight dynamic interface — built by the agent, in real time, in response to context — without any pre-built screens.

---

## Activation

Immersive Chat is accessible from any open session via a toggle in the session header. It is not the default view — users explicitly switch into it when they want a richer interaction experience. Switching back to the standard view at any point is non-destructive; the conversation history is preserved in full.

When the mode is activated, two things happen simultaneously:

- The frontend transitions to a full-page layout, repositioning the message list, input bar, and introducing a right-side canvas panel.
- The backend injects the **UI Protocol Tool** into the agent's active tool configuration for that session, making the block-rendering capability available to the agent on its next response.

When the mode is deactivated, the tool is removed from the agent's context on the next turn, and the layout reverts to the standard view.

---

## Layout

The immersive layout has three zones:

**Message area** occupies the left and center of the screen. It renders the full conversation thread, with both plain text messages and block-based responses displayed inline in sequence, exactly as they were emitted. This area scrolls independently.

**Canvas panel** occupies the right side. It is a persistent workspace where blocks can be "pinned" — meaning they remain visible regardless of scroll position in the message area. Pinned blocks carry a unique `block_id` and persist across multiple turns of conversation. The agent is aware of the canvas state and can reference or mutate pinned blocks in subsequent responses.

**Input bar** is anchored at the bottom, full-width, consistent with the standard view but styled for the immersive context.

---

## The UI Protocol Tool

When Immersive Chat is active, the agent gains access to a tool called `render_ui_block`. Calling this tool is how the agent produces structured visual output instead of — or alongside — plain text.

The tool accepts a list of **blocks**. Each block has a `type` field that determines how the frontend renders it. Blocks can be mixed freely within a single response — for example, a stat row followed by a table followed by a button group is a valid single response.

The tool also accepts optional metadata per block: whether the block should be pinned to the canvas, what `block_id` to assign it, and whether it should subscribe to live updates via SignalR.

The agent is instructed — via its system prompt amendment when immersive mode is active — on when and how to use this tool. The instruction set includes guidance on which block type to prefer for which kind of content, how to compose multi-block responses, and how to reference previously pinned canvas blocks by their IDs.

---

## Block Type System

Blocks are organized into four functional categories.

### Core — Content Display

These are the foundational blocks used in the majority of agent responses. Every agent is expected to use these regardless of domain.

**Text / Markdown** is the default block for unstructured prose, code snippets, and inline formatting. It is the fallback for any response that does not benefit from richer structure, and is always available even when more specific blocks would be appropriate.

**Card** represents a bounded entity — a contact, a document, a contract, a lead, an agent profile. It has a title, optional subtitle, body fields rendered as key-value pairs, and optionally a leading icon or status badge. Cards are the standard way for the agent to present a single named thing.

**Table** renders rows and typed columns with support for client-side sorting and filtering. It is the standard block for comparisons, search results, reports, and any response that naturally takes the form of structured rows.

**Stat Row** presents two to four metric tiles side by side — each with a value, a label, and an optional delta indicator. It is used for KPI summaries, dashboard snapshots, and quick performance readouts at the top of a longer response.

**List** renders an ordered or unordered sequence of items, each optionally carrying a leading icon and a sub-label. It is preferred over markdown bullet points whenever items have semantic metadata attached.

**Alert / Notice** renders an inline notice in one of four semantic variants — informational, success, warning, or danger. It is used for important caveats, confirmation messages, error states, and anything the agent needs the user to notice before proceeding.

### Interaction — User Can Act

These blocks allow the user to take action directly inside the conversation, with the result returning to the agent as a structured input.

**Button Group** renders one to five labeled action buttons. Each button can either send a predefined message back to the agent or trigger a direct callback. It is the primary mechanism for decision branches — the agent presents options and waits for the user to choose.

**Form** renders a dynamically composed set of input fields — text, select, date picker, numeric, toggle — with a submit action. The submitted data is returned to the agent as a structured tool result. This eliminates the need for the agent to collect inputs through back-and-forth natural language exchanges.

**Confirm Dialog** renders an inline confirmation prompt with accept and cancel actions, optionally labeled with a risk level. The dialog blocks further agent output until the user responds. It is used for destructive or irreversible actions.

**Checklist** renders a list of tickable items, some of which the agent may pre-check. The user completes the remainder and submits the state. The full checked/unchecked state is returned to the agent, enabling it to continue based on what the user confirmed.

**Poll / Vote** renders a single or multi-select voting interface with live progress bars once a choice is made. The selection is returned to the agent as a tool result. It is used for lightweight preference gathering without requiring a full form.

### Data Visualization — When Numbers Need Shape

These blocks give the agent a way to present quantitative or sequential information visually, without requiring the agent to produce any rendering code.

**Chart** accepts a typed specification — chart type (bar, line, pie), labels, and value series — and delegates all rendering to the frontend. The agent never writes rendering logic; it only emits a data structure.

**Timeline** renders a vertical sequence of dated events, each with a label, optional description, and status indicator. It is used for project history, activity logs, roadmap views, and any chronological narrative.

**Progress** renders a labeled progress bar or a step indicator showing position within a multi-stage process. It is used for onboarding flows, task completion tracking, and pipeline status.

**Diff** renders a before-and-after comparison in either side-by-side or inline format. It is used for contract edits, configuration changes, translated text pairs, and any situation where the agent is showing what changed between two versions of content.

### Composite — Multi-Part Structures

These blocks allow the agent to compose more complex layouts from multiple pieces of content.

**Accordion** renders a set of collapsible sections. Each section has a title and can contain any block type as its body. It is used when a response is long but not all parts are equally relevant — the user expands only what they need.

**Wizard / Stepper** renders a multi-step sequential flow with navigation controls. Each step is an independent block container. It is used for guided workflows where the agent needs to walk the user through a process — onboarding, configuration, intake — in a controlled sequence.

**Card Grid** renders a two or three column grid of cards. It is used for listing multiple comparable entities — search results, agent profiles, product options — where the user needs to scan and choose.

**Split Panel** renders two columns side by side, each containing an independent block. It is used for show-and-tell layouts: a summary on the left and a supporting table or chart on the right.

---

## Advanced Concepts

### Canvas Object — Persistent Pinnable Blocks

Any block emitted by the agent can optionally be designated as a canvas object. A canvas object is assigned a stable `block_id` and is rendered in the canvas panel rather than the message stream. It persists across turns — it does not scroll away as the conversation continues.

The agent receives a serialized snapshot of the current canvas state at the start of each turn, injected into its context. This means the agent knows what is currently displayed on the canvas, can refer to specific blocks by ID, and can issue targeted mutations — updating a table row, changing a card field, altering a status badge — without re-rendering the entire block.

Users can also interact with canvas objects directly: pinning or unpinning them, reordering them, and dismissing individual blocks. These interactions are communicated back to the session context so the agent remains in sync.

This transforms the right panel from a passive display area into a collaborative workspace that the agent and user build together across an extended session.

### Live Block — Real-Time Updates via SignalR

A block can be created with a `subscription_id`. When present, the frontend maintains a SignalR subscription for that ID. Any update event pushed to that subscription — from a background job, a pipeline monitor, another agent, or a webhook handler — is applied to the block in real time without requiring a new user message or agent turn.

This enables the agent to establish a live status board inside the chat. A task card showing an in-progress pipeline can update its status from "running" to "done" the moment the job completes. A stat block showing active agent load can refresh on a polling interval. A timeline can receive new entries as events occur upstream.

The user is watching the canvas and the message stream simultaneously — this makes the immersive chat feel less like a turn-based conversation and more like a live operational view.

### Nested Chat Block — Inline Agent Delegation

When an agent delegates a sub-task to another agent in the OpenClaw network, the exchange between the two agents can be embedded directly in the immersive view as a collapsible nested chat block. The block shows the delegating agent's handoff message, the sub-agent's identity and responses, and the result returned to the parent.

The user can inspect the sub-conversation in full or keep it collapsed. This makes multi-agent workflows transparent without overwhelming the primary conversation thread. It also provides a natural audit trail — every delegation is visible inline, at the point in the conversation where it occurred.

### Decision Tree Block — Session-Scoped Dynamic Branching

Rather than a static flow, the decision tree block is generated by the agent at runtime based on the current session context. The agent emits a root node and its immediate children; as the user selects options, the agent generates the next level of branches on demand.

This allows complex guided flows — legal intake, procurement qualification, troubleshooting sequences — to be driven entirely by agent logic, with no pre-built decision tree authored in advance. The tree adapts to user inputs, context gathered in the current session, and any external data the agent queries along the way.

---

## Agent Instruction Amendment

When Immersive Chat mode is active, the session's system prompt is amended with a UI protocol appendix. This appendix instructs the agent to:

- Prefer structured blocks over plain prose wherever content naturally fits a known block type.
- Compose multi-block responses as arrays — not as separate tool calls per block.
- Use `button_group` as the default close for any response that implies a next action or decision.
- Reference canvas block IDs explicitly when updating or building upon previously pinned content.
- Use `alert` blocks for anything the user must acknowledge before the conversation continues.
- Reserve plain `text` blocks for narrative responses where structure would reduce rather than add clarity.

The amendment is scoped to the active session. It does not persist to other sessions or modify the agent's base configuration.

---

## Integration Points

**Frontend stack:** React + Vite + TailwindCSS. The block renderer is a single switch-on-type component tree. Each block type is an isolated React component. The canvas panel is a separate state slice, synced with the message list but rendered independently.

**Backend stack:** ASP.NET Core API. The streaming endpoint detects `tool_use` events with `name === "render_ui_block"` and forwards them to the client as a dedicated SSE event type, distinct from plain text delta events. The frontend handles these separately and does not render them in the text stream.

**Real-time layer:** SignalR hub extended with a `BlockUpdate` event type, keyed on `subscription_id`. Any service in the WAN Solutions stack can push to this hub to update a live block.

**Agent runtime:** OpenClaw. The `render_ui_block` tool is registered as a session-scoped skill, injected at session start when Immersive mode is active and removed when it is deactivated.

---

## Non-Goals

Immersive Chat is not a general-purpose dashboard builder. Blocks are composed by the agent in response to user messages — they are not authored manually by the user or pre-configured by an administrator for a given session type.

It is also not a replacement for the standard chat view. The standard view remains the default and remains appropriate for the majority of interactions. Immersive Chat is an enhancement for sessions where richer output is expected — complex reports, guided workflows, live monitoring, multi-agent coordination.

---

*Document status: Working specification — pre-implementation*
*Owner: WAN Solutions · CTO Office*
