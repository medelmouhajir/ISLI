# 07 — Channels & Gateways

## Concept

A **Channel** is the interface between the outside world and an agent. Each channel adapter translates platform-specific messages (Telegram updates, WhatsApp webhooks, emails) into ISLI Tasks, and translates Task outputs back into platform-specific responses.

A **Gateway** is a running Channel adapter process.

---

## Agent-Channel Assignment

Each agent can own one or more channels. The assignment is exclusive by default:

```
Telegram Bot "ResearchBot" → Agent: Research
WhatsApp +212-XXX-XXXX     → Agent: Sales
Web Chat (isli-board)       → Any agent
Email inbox@company.com     → Agent: Communications
```

This means users reach the intended agent by choosing the right channel. The Kanban board shows which channel each task came through.

---

## Channel Configuration (in `agent.yaml`)

```yaml
channels:
  - type: telegram
    bot_token_env: TELEGRAM_RESEARCH_BOT_TOKEN
    allowed_user_ids: [123456789]   # Telegram user IDs (empty = all)
    group_chat: false

  - type: whatsapp
    provider: twilio                 # twilio | 360dialog | meta-cloud
    account_sid_env: TWILIO_SID
    auth_token_env: TWILIO_TOKEN
    from_number: "+12025551234"
    allowed_numbers: []             # empty = all verified numbers

  - type: email
    smtp_host_env: SMTP_HOST
    smtp_port: 587
    smtp_user_env: SMTP_USER
    smtp_pass_env: SMTP_PASS
    inbox_address: agent@company.com
    imap_host_env: IMAP_HOST        # for receiving

  - type: web
    # No config needed — served by isli-board
```

---

## Supported Channel Adapters

| Channel | Status | Notes |
|---------|--------|-------|
| Telegram | ✅ Built-in | `python-telegram-bot` |
| WhatsApp (Twilio) | ✅ Built-in | Twilio Messaging API |
| WhatsApp (Meta Cloud) | ✅ Built-in | Meta Business API |
| Web Chat (board) | ✅ Built-in | Native WebSocket |
| Email (SMTP/IMAP) | ✅ Built-in | Any SMTP provider |
| Lark/Feishu | 🔧 Adapter | Lark Event API |
| Slack | 🔧 Adapter | Slack Bolt SDK |
| Discord | 🔧 Adapter | discord.py |
| SMS (Twilio) | 🔧 Adapter | Twilio SMS |
| Voice (phone) | 📋 Planned | Twilio Voice + ASR |

---

## Message Flow: Inbound — Direct Session (User → Agent)

When a message is addressed to a specific agent (e.g., Telegram bot assigned to `agent_id: kimi-02`), it bypasses the Kanban board entirely and creates a **Session**:

```
Platform (e.g., Telegram)
  └─→ Webhook POST to Gateway (/webhook/telegram/{agent_id})
        └─→ Gateway parses update
              ├─ Extract user_id, message_text
              ├─ Normalize to ISLI Message format
              └─→ Core API: GET or CREATE Session
                    {
                      id: "sess_tg_kimi-02_123456789",
                      agent_id: "kimi-02",
                      channel: "telegram",
                      channel_user_id: "123456789",
                      messages: [...],
                      status: "pending_context"
                    }
              ├─ Core: SessionContextInjectorWorker polls sessions with status="pending_context"
              ├─ Core: POST /context/inject to Keeper (with session_id)
              └─ Core: Update session status="ready", context_summary set
                    └─→ Core: emit "session:message" via Redis → WebSocket
                          └─→ Agent Runner (kimi-02) receives event
                                └─→ Agent LLM generates reply
                                      └─→ Core: POST /v1/sessions/{id}/reply
                                            └─→ Gateway: sendMessage to user
```

**Key characteristics of Session flow:**
- No Kanban card is created
- Messages are stored in the `sessions` table (`messages` JSON column)
- Context injection is session-scoped (Keeper receives `session_id`)
- Reply is delivered directly via `POST /v1/sessions/{id}/reply`

## Message Flow: Inbound — Kanban Task (User → Board, or Agent → Agent)

When a message has no specific `agent_id` (e.g., board web chat, or agent delegation), it creates a **Task**:

```
Platform (e.g., Web Chat or Agent Delegation)
  └─→ Core API: POST /api/tasks
        {
          type: "user_request",
          agent_id: "agent_research",
          input: "...",
          channel: "web",
          session_id: "sess_web_123456789"
        }
        └─→ Kanban board: new card in INBOX
              └─→ ContextInjectorWorker polls tasks with status="pending_context"
                    └─→ Keeper: /context/inject (with task_description)
                          └─→ Core: task status="inbox", context_summary set
                                └─→ Core: emit "task:updated" via Redis → WebSocket
                                      └─→ Agent Runner receives task
                                            └─→ Agent LLM executes task
                                                  └─→ Core: task status="done", output set
```

**Key characteristics of Task flow:**
- Kanban card is created and visible on the board
- Tasks support delegation chains (`parent_task_id`, `child_task_ids`)
- Status lifecycle: `inbox` → `doing` → `done`
- Agent-to-agent communication happens exclusively through Tasks

---

## Message Flow: Outbound (Agent → User)

There are two mechanisms for an agent to send a message back to a user:

### 1. Session Reply (Automatic Delivery)

When an agent receives a `session:message` event (direct user message), it calls:

```python
await core_client.reply_to_session(session_id, text)
```

Core automatically forwards this to the channel gateway (`POST /send`). This is the default path for conversational replies.

### 2. Proactive Send-Message Skill

When an agent needs to reach out unprompted (e.g., from a Kanban task or a scheduled notification), it invokes the `send-message` skill:

```python
# Tool call the LLM generates:
{"channel": "telegram", "channel_user_id": "+212668507183", "text": "Hello"}

# AgentRunner injects agent_id and core_client, then calls:
POST /v1/skills/send-message/send
```

**Requirements for proactive send:**
1. The agent's `channels` list must include `"telegram"` (or target channel)
2. The agent's `skills` list must include `"send-message"`
3. Core validates channel assignment before forwarding to the gateway

If the agent lacks the channel in its `channels` field, Core returns `403 Channel not assigned to agent`.

---

## Session Continuity per Channel

Each unique `(channel, channel_user_id)` pair gets its own **session ID** that persists across messages. This means:
- Telegram user 123456789 always continues the same session with Research agent
- Keeper maintains their message history across conversations
- Agent remembers who they are and past interactions

Sessions expire after 24 hours of inactivity (configurable).

### Session Soft-Delete and Revival

Sessions can be **soft-deleted** by `SessionLifecycleManager` when:
- `expires_at` has passed (default: 24 hours from last activity), OR
- `last_activity_at` is older than the idle timeout (default: 30 minutes)

When a new message arrives for a soft-deleted session, the session is **revived** rather than recreated:
- `deleted_at` is cleared
- `expires_at` is reset to 24 hours from now
- `status` returns to `"pending_context"`
- **Raw `messages` and structured `journal` are preserved** so the agent retains conversation history

**Important:** Prior to 2026-05-18, soft-deletion wiped `messages = []` and revival wiped `journal = None`, causing agents to lose all conversation history. Both behaviors were fixed so that historical context survives across session lifecycles.

---

## Session Commands (Slash Commands)

Users can manage their session, inspect context, pin memories, and control in-flight tasks directly from Telegram (and future channels) using slash commands.

### Architecture: Thin Adapter, Thick Core

Commands are **intercepted by the channel adapter** before reaching the agent. All business logic lives in Core so future channels reuse the same endpoint.

```
User sends /status
  → TelegramAdapter.handle_webhook()
    → Detects "/status"
    → POST /v1/channels/telegram/commands (HMAC-signed)
      → Core commands router
        → Queries DB / Keeper / Memory
        → Returns response text
    → TelegramAdapter.send_message(response_text)
```

Commands are **never forwarded** to `/v1/channels/telegram/webhook` — the agent never sees raw slash commands as user messages.

### Available Commands

| Command | Behavior |
|---------|----------|
| `/new` | Starts a fresh session (soft-deletes current, clears messages/journal, generates new `session_id`) |
| `/compact` | Triggers journal compaction manually on the current session |
| `/context` | Shows the Keeper's current structured session journal |
| `/status` | Shows agent name, model, session age, message count, token estimate |
| `/remember <text>` | Pins a fact to Tier 3 semantic memory (ChromaDB `agent:{id}` collection) |
| `/forget <text>` | Searches semantic memory and proposes a candidate for deletion |
| `/confirm_forget` | Confirms and executes the pending deletion from the last `/forget` |
| `/memories` | Lists all pinned facts in the agent's semantic collection |
| `/retry` | Re-sends the last unanswered message (re-sets `pending_context`, re-emits `session:message`) |
| `/cancel` | Cancels the current in-progress task if the agent is stuck |
| `/help` | Lists all available commands |

### Session ID Tracking for `/new`

Session IDs are deterministic by default: `sess_tg_{agent_id}_{user_id}`. To support genuinely new sessions, the adapter tracks the active session ID per user in Redis:

- **Redis key:** `active_session:telegram:{agent_id}:{user_id}`
- On `/new`, Core generates a new session ID (`uuid4()`), returns it, and the adapter stores it in Redis.
- On normal messages, the adapter checks Redis first; if missing, falls back to the deterministic ID.
- **Race condition guard:** When `/new` is received, a transient Redis lock (`new_session_pending:{channel}:{agent_id}:{user_id}`, 10s TTL) prevents follow-up messages from attaching to the old deleted session while the new one is being created.

**Important (fixed 2026-05-20):** The old `/new` implementation appended a timestamp to the existing session ID (`{old_id}_{timestamp}`). With UUID agent IDs (~36 chars) and Telegram user IDs, this produced session IDs exceeding the `String(64)` column limit, causing PostgreSQL `StringDataRightTruncation` errors. The new implementation uses `uuid4()` (36 chars) and performs the soft-delete + insert as a single atomic database transaction. If the insert fails, the delete is rolled back — the user is never left session-less.

### Telegram Command Menu (`setMyCommands`)

The adapter registers all commands with Telegram's Bot API via `setMyCommands` so users see a command menu popup when typing `/`. Registration happens once per bot token:

- **Default token:** During `TelegramAdapter.start()` on channels service startup
- **Per-agent tokens:** The first time a custom `telegram_bot_token` is resolved via `_resolve_token()`

Commands are defined as `telegram.BotCommand` objects with lowercase names (no leading slash) and descriptions within Telegram's 3–256 character limit. The adapter tracks registered tokens in `self._commands_registered_for_tokens` to avoid duplicate API calls.

### Task Cancellation Guard

`/cancel` moves a `doing` task to `failed` and sets a Redis flag `task_cancelled:{task_id}` (60s TTL). The agent runner checks task status before committing LLM output and discards the result if the task was cancelled mid-flight, preventing wasted tokens on stale completions.

### Two-Step Memory Deletion

`/forget <text>` performs semantic search, returns the top candidate with a prompt "Reply /confirm_forget to delete this memory," and stores the pending fact ID in Redis (`pending_forget:{session_id}`, 5-min TTL). This prevents accidental deletions from semantic search mismatches.

---

## Gateway Adapter Interface

All channel adapters implement the same Python interface:

```python
class ChannelAdapter(ABC):

    @abstractmethod
    async def start_webhook(self, port: int): ...
    # Start listening for incoming messages

    @abstractmethod
    async def send_message(self, channel_user_id: str, text: str, **kwargs): ...
    # Send a message to a user

    @abstractmethod
    async def send_typing(self, channel_user_id: str): ...
    # Show "typing..." indicator while agent is working

    @abstractmethod
    def parse_update(self, raw_update: dict) -> Optional[InboundMessage]: ...
    # Parse platform webhook payload into ISLI format

    @abstractmethod
    async def health_check(self) -> bool: ...
```

This makes adding new channels straightforward — implement the interface, write `skill.yaml`, register.

---

## Multi-Language Support

Channel gateways support **automatic language detection**:
- Incoming message language is detected (using `langdetect` or Keeper embedding classification)
- Language tag added to Task metadata
- Agent receives language hint in context injection
- Agent responds in the detected language

Supported languages for detection: Arabic, French, Darija (Moroccan Arabic), English, Spanish, and any language the assigned model supports.

---

## Channels & Gateways Gaps (2026-05-11 Research)

The following gaps were identified during a parallel 12-agent research review:

### High
- **No webhook idempotency keys** — duplicate deliveries create duplicate Task cards in INBOX.
- **No delivery confirmation or retry for outbound messages** — failed platform API calls silently drop responses.
- **In-flight messages lost on gateway crash** — no transactional handoff or persistence between Core API and gateway.

### Medium
- **No cross-channel user identity linking** — same person on Telegram and WhatsApp gets independent sessions.
- **Channel-specific message size limits not enforced** — Telegram (4096 chars) and WhatsApp (~1600) limits unhandled.
- **No offline message queue for platform outages** — outbound messages dropped immediately when APIs are down.
- **No message ordering guarantee within a session** — concurrent processing could append messages out of order.
- **No platform rate-limit backoff** — no adaptive backoff, circuit breaker, or queue-and-retry on HTTP 429.
- **Attachments not normalized across channels** — inbound extracts attachments but outbound only sends text.
- **Agent restart loses in-flight channel tasks** — no checkpointing for pending outbound messages.

### Low
- **Voice (phone) channel dependencies undefined** — ASR/TTS providers, fallback strategy, and latency budget unspecified.

### Compliance
- **No user consent capture** — personal data is processed from the first inbound message with no documented legal basis.
- **CAN-SPAM / TCPA gaps** — Email and SMS channels lack unsubscribe, opt-out, and prior-express-consent mechanisms.
- **No Data Processing Agreements** — no DPAs documented for Telegram, Twilio, Meta Cloud, or SMTP hosts.

> See `Memory/ISLI-Research-Report.md` for full details and recommendations.