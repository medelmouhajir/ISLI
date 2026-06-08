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
    provider: pyaileys               # pyaileys (WhatsApp Web) | twilio | meta-cloud
    auth_dir: /auth/whatsapp        # pyaileys: per-agent auth folder (mounted volume)

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
| Telegram | ✅ Built-in | `python-telegram-bot` — bot token per agent |
| WhatsApp Web (Baileys) | ✅ Built-in | Node.js sidecar, QR code pairing, per-agent phone number |
| Web Chat (board) | ✅ Built-in | Native WebSocket |
| Email (SMTP/IMAP) | ✅ Built-in | Any SMTP provider |
| WhatsApp (Twilio) | 📋 Planned | Twilio Messaging API |
| WhatsApp (Meta Cloud) | 📋 Planned | Meta Business API |
| Lark/Feishu | 📋 Planned | Lark Event API |
| Slack | 📋 Planned | Slack Bolt SDK |
| Discord | 📋 Planned | discord.py |
| SMS (Twilio) | 📋 Planned | Twilio SMS |
| Voice (Telegram) | ✅ Built-in | Auto-transcribed via `isli-audio` (faster-whisper); agent receives text |
| Voice (Board UI) | ✅ Built-in | Browser `MediaRecorder` → `POST /v1/stt/transcribe` → text inserted into chat input with auto-send toggle |
| Voice (phone) | 📋 Planned | Twilio Voice + ASR |
| Web Push (PWA) | ✅ Built-in | Standard Web Push API via Service Worker; multi-device support |

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
- **Streaming modes** (added 2026-05-31): When the agent's `streaming_mode` is not `silent`, live events (`token_delta`, `tool_call`, `phase_start`, etc.) flow agent → Core → Board WebSocket. External channels (Telegram, WhatsApp) still receive only the final assembled text — streaming is WebSocket-only.
- **Agent-driven UI components** (added 2026-05-29, expanded 2026-05-30): Assistant replies may include a `components` array with structured React payloads (`table`, `card`, `button_group`, `comparison_table`, `form`, `json_viewer`, `status_timeline`, `metric_grid`). The Board renders these inline below the message bubble. User interactions (clicks, form submits) create action messages that flow back to the agent. See [`Docs/13-immersive-chat-ui.md`](./13-immersive-chat-ui.md).

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

Users can manage their session, inspect context, pin memories, and control in-flight tasks directly from **Telegram** and **WhatsApp** using slash commands.

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

Session IDs are deterministic by default:
- Telegram: `sess_tg_{agent_id}_{user_id}`
- WhatsApp: `sess_wa_{agent_id}_{phone_number}`

To support genuinely new sessions, the adapter tracks the active session ID per user in Redis:

- **Telegram Redis key:** `active_session:telegram:{agent_id}:{user_id}`
- **WhatsApp Redis key:** `active_session:whatsapp:{agent_id}:{user_id}`
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

## Notification Escalation (Added 2026-06-01)

When Core's `NotificationEngine` determines a notification should be sent to an external channel (typically Telegram or Web Push), it delegates delivery to the relevant handler.

### Telegram Escalation Flow

```
Core NotificationEngine
  └─→ _external_channels_for_event()
        └─→ Outbox entry with topic="notification:external"
              └─→ OutboxWorker polls and executes
                    └─→ deliver_external()
                          ├─→ Check user presence (suppress non-critical if inactive)
                          ├─→ Format text: "🔔 *{title}*\n{body}"
                          └─→ POST /v1/skills/send-message/send
                                └─→ Core channels proxy
                                      └─→ TelegramAdapter.send_message(parse_mode="Markdown")
                                            └─→ Telegram Bot API
```

### Web Push Escalation Flow

Web Push allows the browser or mobile OS to receive and display notifications even when the Board UI is closed.

```
Core NotificationEngine
  └─→ _external_channels_for_event()
        └─→ Outbox entry with topic="notification:web_push"
              └─→ OutboxWorker polls and executes
                    └─→ deliver_web_push()
                          ├─→ Fetch all active subscriptions for user
                          ├─→ Prepare payload (4KB limit)
                          ├─→ Sign with VAPID keys
                          └─→ Trigger Push Service (Chrome/Safari/Firefox)
                                └─→ Browser Service Worker (sw.ts)
                                      └─→ self.registration.showNotification()
```

**Key characteristics:**
- **Local-first:** No third-party accounts (FCM/OneSignal) required.
- **Privacy:** Subscriptions are stored in the local ISLI database.
- **Deep-linking:** Clicking a notification opens the Board and navigates directly to the relevant task or agent.
- **Stale Pruning:** Stale endpoints (410 Gone) are automatically removed from the database on delivery failure.

### iOS Support

On iOS (16.4+), Web Push requires the user to **"Add to Home Screen"** first. The Board UI detects this and provides a guidance prompt if the user is on iOS but hasn't installed the app yet.

### Telegram Formatting

Notification escalations use **Markdown formatting** (`parse_mode="Markdown"`) for bold titles:

```python
await bot.send_message(
    chat_id=user_id,
    text="🔔 *Agent Research crashed*\nThe agent stopped unexpectedly.",
    parse_mode="Markdown",
)
```

This requires the Telegram adapter's `send_message()` to accept and pass through `parse_mode`. The adapter was updated in 2026-06-01 to support this kwarg.

### Presence Suppression

Non-critical notifications are suppressed if the user hasn't read messages recently. This prevents spamming inactive users with routine updates. Critical (`agent:crash`, `system:alert`) always bypass suppression.

### Requirements for Escalation

1. The target agent must have `"telegram"` in its `channels` list.
2. The agent must have `"send-message"` in its `skills` list.
3. Core validates both before forwarding. If either is missing, the notification remains in-app only and a warning is logged.

---

## Voice & Audio Messages (Added 2026-05-29 / Expanded 2026-06-01)

ISLI handles **inbound** voice messages at the **channel adapter level** via automatic transcription, so the agent always receives text. ISLI also supports **outbound** TTS-generated audio delivery to Telegram, WhatsApp, and the Board web UI — both as explicit agent-initiated voice messages and as a session-level "Voice Mode" that auto-synthesizes every reply.

### Inbound: Telegram Voice Messages

When a user sends a voice message to a Telegram bot:

```
Telegram voice message (.ogg)
  └─→ TelegramAdapter.handle_webhook()
        └─→ Detects `message.voice` attachment
              ├─→ Downloads audio bytes from Telegram file API
              ├─→ Stores bytes in Redis Blob Store (DB 10)
              └─→ Sends `blob:audio:{uuid}` token to Core API
                    └─→ Core API (channels router)
                          ├─→ Detects blob token
                          ├─→ POST /stt/transcribe to isli-audio (passing audio_ref)
                          └─→ Replaces token with transcription in Session flow
```

**Key characteristics:**
- The agent never sees the raw audio; it receives transcribed text in the session message
- The transcription is transparent to the user — they can continue the conversation normally
- Language is auto-detected by faster-whisper unless overridden
- Uses **multipart/form-data** upload (not base64-in-JSON) for efficiency

---

### Outbound: TTS Audio Delivery (Added 2026-06-01 / Refactored 2026-06-07)

Agents can deliver synthesized voice messages to users across all supported channels. This works in two modes:

#### Phase 1 — Explicit Agent-Initiated Voice Messages

The agent invokes the `send_voice_message` SDK convenience wrapper (or manually calls `text-to-speech` followed by `send-message` with `audio_ref`):

```python
from isli_agent import send_voice_message

await send_voice_message(
    channel="telegram",
    channel_user_id="123456789",
    text="Welcome to ISLI. How can I help you today?",
    voice="piper-en-us-lessac-medium",
    language="en",
    core_client=client
)
```

**Architecture (Claim Check):**
```
Agent SDK (send_voice_message)
  └─→ POST /v1/skills/text-to-speech/synthesize → isli-audio (piper-tts)
        ↓
  ┌─→ isli-audio stores WAV bytes in Redis Blob Store (DB 10)
  │     └─→ returns `audio_ref: "blob:audio:{uuid}"` to Core
  │
  ├─→ Core (reply_to_session): 
  │     ├─→ Web/Board: Rewrites token to signed URL: `/v1/blobs/{uuid}`
  │     ├─→ External Channels: Forwards `audio_ref` token to gateway
  │     │     ↓
  │     │     TelegramAdapter: Fetches from Redis (DB 10) → WAV → Opus/OGG → bot.send_voice()
  │     └─→ OutboxWorker: Promotes from Redis to Workspace disk (_attachments/)
  └───────────────────────────────────────────────────────────────────────────────→
```

#### Phase 2 — Session-Level Voice Mode

Users can enable **Voice Mode** from the Board chat input (toggle button next to auto-send). When enabled:

1. Board sends `voice_mode_enabled: true` with every message to `POST /v1/sessions/{id}/message`
2. Core persists the flag in `Session.session_metadata`
3. On every agent reply, Core's `reply_to_session` automatically:
   - Calls `POST /tts/synthesize` with the agent's text
   - Uploads the resulting WAV to the workspace
   - Appends `audio_url` to the message dict
   - Forwards `audio_b64` to the channel gateway
   - **Failure resilience:** If TTS fails (Ollama down, text too long, etc.), Core logs a warning and delivers the text-only reply. Audio is best-effort; text is the contract.

#### Audio Storage & Serving

- **Storage:** Core uploads raw WAV bytes to `isli-workspace` under `_attachments/audio/{session_id}/{uuid}.wav`
- **Serving:** Core exposes `GET /v1/audio/{session_id}/{filename}` which proxies workspace download with session auth, returned as `StreamingResponse(media_type="audio/wav")`
- **Board playback:** Assistant messages with `audio_url` render an `<audio controls preload="metadata" src={`/api${msg.audio_url`}}>` player below the text bubble
- **Size limits:** Two-layer defense — Pydantic `max_length=6_700_000` on `audio_b64` schema field (~5 MB decoded) + secondary decoded-bytes check

#### Audio Cleanup

An `AudioCleanupWorker` runs every 24 hours and purges workspace audio files under `_attachments/audio/*` older than 7 days. This prevents unbounded disk growth from voice mode usage.

#### Channel-Specific Behavior

| Channel | Text Ordering | Audio Format | Notes |
|---------|--------------|----------------|-------|
| **Telegram** | Text sent first, then voice follow-up | WAV → Opus/OGG via ffmpeg (libopus, 24k bitrate) | `bot.send_message()` then `bot.send_voice()`; caption limited to 1024 chars |
| **WhatsApp** | Text sent first (chunked if >1600 chars), then voice | WAV forwarded as base64 to sidecar → temp file → Baileys `ptt: true` | Original `remote_jid` preserved for privacy mode |
| **Board** | Text + inline audio player | WAV streamed via `/v1/audio/{session_id}/{filename}` | `<audio controls>` rendered below assistant bubble; Voice Mode toggle in `ChatInput` |

#### Security & Resilience

- **TTS failure handling:** `try/except` around auto-TTS in `reply_to_session`; warning log; continues with text-only delivery
- **Schema validation:** `audio_b64` max length enforced at Pydantic layer before any processing
- **Workspace scoping:** Audio files stored in per-agent workspace scope; session auth required for download
- **Attachment column:** `ChannelMessage.attachments` JSON column stores metadata for audit and future features

---

## Gateway Adapter Interface

All channel adapters implement the same Python interface:

```python
class InboundMessage(BaseModel):
    channel: str
    channel_user_id: str
    text: str
    attachments: list[dict[str, Any]] = []
    raw_payload: dict[str, Any] = {}
    metadata: dict[str, Any] = {}

class ChannelAdapter(ABC):
    @abstractmethod
    async def start(self): ...
    # Initialize the adapter (e.g., start polling, register webhooks, scan auth folders)

    @abstractmethod
    async def stop(self): ...
    # Gracefully shut down the adapter

    @abstractmethod
    async def send_message(self, channel_user_id: str, text: str, **kwargs) -> bool: ...
    # Send a message to a user. kwargs may include agent_id for per-agent routing.

    @abstractmethod
    async def send_typing(self, channel_user_id: str): ...
    # Show "typing..." indicator while agent is working

    @abstractmethod
    def parse_update(self, raw_update: dict) -> Optional[InboundMessage]: ...
    # Parse platform-specific update into normalized InboundMessage

    @abstractmethod
    async def health_check(self) -> bool: ...
    # Verify connection to the platform's API
```

This makes adding new channels straightforward — implement the interface, register in `main.py`, add platform constants to `chunking.py` / `rate_limit.py` / `attachments.py`.

---

## WhatsApp Web (Baileys Sidecar) — Deep Dive

ISLI's WhatsApp channel uses a dedicated **Node.js sidecar** running the **Baileys** library (`@whiskeysockets/baileys`) for QR code pairing and real-time messaging. This architecture was adopted in May 2026 to resolve protocol stability issues with older Python-based libraries.

### Architecture

The WhatsApp integration is split into two components:
1.  **`isli-whatsapp-sidecar` (Node.js)**: Manages the raw WhatsApp protocol, maintains persistent WebSockets, and handles local credential storage.
2.  **`WhatsAppAdapter` (Python)**: A proxy within the `isli-channels` service that coordinates with the sidecar via HTTP REST and receives incoming events via webhooks.

```
isli-channels (Python) <--- Webhook (POST) --- isli-whatsapp-sidecar (Node.js)
        |                                              |
        +-------------- REST (HTTP) ----------------->+
```

### QR Code Pairing Flow

1.  **Admin initiates pairing** via `POST /whatsapp/sessions/{agent_id}` in `isli-channels`.
2.  `isli-channels` proxies this to the sidecar: `POST /session/{agent_id}/start`.
3.  The sidecar initializes a Baileys socket and generates a QR code.
4.  The sidecar sends a **Webhook** back to `isli-channels` with the QR data.
5.  **Admin polls** `GET /whatsapp/sessions/{agent_id}/qr` in `isli-channels` to retrieve the QR data.
6.  **User scans QR** with WhatsApp mobile app.
7.  The sidecar detects the connection is "open" and sends a webhook to update `isli-channels`.

### Credential Persistence & Isolation

- **Storage**: Credentials are saved in `/auth/whatsapp/{agent_id}/` (mapped to the `isli_whatsapp_auth` Docker volume).
- **Isolation**: Each agent has a completely separate directory, preventing session collisions.
- **Permissions**: The volume is owned by the `node` user (UID 1000) inside the container.

### Authentication (Fixed 2026-05-29)

The sidecar and channels service mutually authenticate with **HMAC-SHA256 signatures**:

1. **Sidecar → Channels:** The sidecar computes an `HMAC-SHA256` hex digest of the JSON request body and sends it in the `X-Sidecar-Secret` header:
   ```javascript
   const signature = crypto.createHmac('sha256', SIDECAR_WEBHOOK_SECRET)
       .update(body)
       .digest('hex');
   headers['X-Sidecar-Secret'] = signature;
   ```
   Channels validates it via `WebhookValidator.verify_generic()` before processing.
   - **Fixed 2026-05-29:** Previously, the sidecar sent the **raw secret string** as the header value, causing Channels to reject every webhook with `401 Unauthorized` because it expected the HMAC digest.

2. **Channels → Sidecar:** All REST calls carry `Authorization: Bearer <token>` (configured via `SIDECAR_API_TOKEN`). The sidecar's Express middleware rejects requests with missing or invalid tokens.

3. **Channels → Core:** The WhatsApp adapter signs forwarded payloads with `WEBHOOK_SECRET` using `X-Webhook-Signature`. Core's `config.py` reads this secret from the `WEBHOOK_SECRET` environment variable so all channels use the same secret:
   ```python
   _webhook_secret = os.getenv("WEBHOOK_SECRET") or "telegram-secret"
   webhook_secrets = {
       "telegram": _webhook_secret,
       "whatsapp": _webhook_secret,
   }
   ```
   - **Fixed 2026-05-29:** Previously, Core hardcoded `"whatsapp-secret"` for the WhatsApp channel, which did not match the Channels adapter's `WEBHOOK_SECRET` value (`"telegram-secret"`), causing all forwarded messages to be rejected with `401 Unauthorized`.

Both secrets are configured via `.env`:
```bash
SIDECAR_WEBHOOK_SECRET=...
SIDECAR_API_TOKEN=...
WEBHOOK_SECRET=...
```

> **Important:** `WEBHOOK_SECRET` must be passed to the `core` service in `docker-compose.yml` or Core will default to `"telegram-secret"` regardless of the `.env` value.

### Reliability (Webhook Retries)

To prevent missing inbound messages if `isli-channels` is restarting, the sidecar implements an **Outbound Webhook Dispatcher** with:
- **Exponential Backoff**: 3 retry attempts for every event (network errors, 5xx, and 429).
- **Payload Sanitization**: Objects are stripped of circular references before serialization to ensure `axios` stability.
- **Awaited Forwarding:** Event handlers `await forwardEvent()` so unhandled promise rejections don't silently drop messages.

### JID Preservation for Replies (Fixed 2026-05-29)

WhatsApp's privacy feature ("Hide my phone number") causes inbound messages to arrive with **LID JIDs** (`xxx@lid`) instead of traditional phone-number JIDs (`xxx@s.whatsapp.net`). If replies are constructed using only the normalized phone number, they are sent to the wrong address and silently lost.

**Fix:** `WhatsAppAdapter._handle_inbound_message()` stores the original `remote_jid` in a per-agent dictionary:
```python
self.user_jids.setdefault(agent_id, {})[phone_number] = remote_jid
```

`send_message()` retrieves the preserved JID before forwarding to the sidecar:
```python
jid = agent_jids.get(channel_user_id, f"{channel_user_id}@s.whatsapp.net")
```

This ensures replies reach the correct WhatsApp identity regardless of whether the user has enabled privacy mode.

### Graceful Shutdown

On `SIGTERM`/`SIGINT`, the sidecar calls `sock.end()` on all active Baileys sockets before exiting, preventing abrupt disconnections that could flag the WhatsApp account.

### Session Management Endpoints (isli-channels)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/whatsapp/sessions/{agent_id}` | Initiate QR pairing |
| GET | `/whatsapp/sessions/{agent_id}/qr` | Get current QR code |
| GET | `/whatsapp/sessions/{agent_id}/status` | Get connection state (open/closed/connecting) |
| DELETE | `/whatsapp/sessions/{agent_id}` | Logout and wipe credentials |
| GET | `/whatsapp/sessions` | List all active sessions |

---

## Multi-Language Support

Channel gateways support **automatic language detection**:
- Incoming message language is detected (using `langdetect` or Keeper embedding classification)
- Language tag added to Task metadata
- Agent receives language hint in context injection
- Agent responds in the detected language

Supported languages for detection: Arabic, French, Darija (Moroccan Arabic), English, Spanish, and any language the assigned model supports.

---

## Security & Authentication

### WhatsApp Webhook Authentication (2026-05-28)

To prevent unauthorized injection of fake messages, the WhatsApp channel implements **dual-layer authentication**:

1. **Sidecar → Channels:** The sidecar sends `X-Sidecar-Secret` header on every webhook. Channels validates it via `WebhookValidator.verify_generic()` before processing.
2. **Channels → Sidecar:** All REST calls from channels to the sidecar carry `Authorization: Bearer <token>`. The sidecar's Express middleware rejects requests with missing or invalid tokens.

Both secrets are configured via `.env`:
```bash
SIDECAR_WEBHOOK_SECRET=...
SIDECAR_API_TOKEN=...
```

### Session Secret

The shared `WEBHOOK_SECRET` is used to HMAC-sign payloads between channels and Core API (`X-Webhook-Signature` header).

---

## Reliability Guarantees

### Outbound Message Retry (WhatsApp)

`WhatsAppAdapter.send_message()` implements 4 attempts with capped exponential backoff (`delay = min(1.0 * 2^attempt, 10.0)`). If all attempts fail, the error is logged with `whatsapp.send_failed_final` and the method returns `False`.

### Message Chunking

Long LLM responses are split via `MessageChunker.chunk(text, "whatsapp")` before sending. WhatsApp limit: 1600 characters per message.

### Webhook Idempotency

Duplicate Baileys events (common during reconnections) are deduplicated via `WebhookIdempotency` using Redis (`webhook:dedup:whatsapp:{message_id}`). TTL: 5 minutes.

### Sidecar Auto-Recovery

- The sidecar auto-restarts sessions from `/auth/whatsapp/{agent_id}/` on startup.
- Individual agent failures are isolated with `try/catch` — one corrupt auth folder does not block other agents.
- `axiosRetry` retries failed webhook forwards on network errors, 5xx, and 429 responses.

### Consent Gate & Auto-Reply (2026-05-29)

New WhatsApp users must grant consent before their messages are processed. If a user sends a normal message before `/start`:

1. Core returns **HTTP 403** (`UserConsent` missing).
2. The WhatsApp adapter catches the 403 and sends an auto-reply:
   > *"Welcome! Please send /start to begin chatting with this agent."*
3. The user sends `/start` → Core grants consent and returns a welcome message.
4. Subsequent normal messages flow to the agent as usual.

This prevents silent message loss for new users who don't know about the `/start` requirement.

**Implementation:** `WhatsAppAdapter._handle_inbound_message()` wraps `_forward_to_core()` in `try/except httpx.HTTPStatusError`. On 403, it calls `self.send_message()` with the consent prompt instead of raising.

---

## WhatsApp Access Mode System (Added 2026-05-29)

Each agent can configure its own **WhatsApp access mode** via `Agent.config` JSONB. This replaces the single hardcoded opt-in behavior with five distinct modes, each suited to different deployment scenarios.

### Supported Modes

| Mode | Behavior | Best For |
|------|----------|----------|
| **`opt_in`** *(default)* | User must send `/start` first. Consent is explicit and recorded in `UserConsent`. | Private agents, GDPR-first deployments |
| **`open`** | Anyone can message. Consent is auto-granted on first inbound message. Optional Redis rate limit per JID. | Client support bots, public info agents |
| **`whitelist`** | Only configured phone numbers/JIDs are allowed. All others rejected with an auto-reply. | Internal team agents, beta testers, specific client groups |
| **`closed`** | Exactly one allowed phone number. Owner-only agent. | Personal assistant, admin bot |
| **`scheduled`** | Access is gated by time windows (timezone + days of week + from/to times). Off-hours inbound gets a custom auto-reply. Falls through to `opt_in` consent check when within hours. | Business-hours support, time-zone-aware agents |

### Config Schema (per-agent `Agent.config` JSONB)

```json
{
  "whatsapp_access_mode": "open",
  "whatsapp_allowed_jids": ["212600000001@s.whatsapp.net"],
  "whatsapp_allowed_user_id": "212600000001",
  "whatsapp_open_rate_limit": {
    "max_msgs": 20,
    "window_seconds": 3600
  },
  "whatsapp_schedule": {
    "timezone": "Africa/Casablanca",
    "windows": [
      { "days": [1, 2, 3, 4, 5], "from": "09:00", "to": "18:00" }
    ],
    "off_hours_reply": "Our team is offline. We're available Mon–Fri 9am–6pm Morocco time."
  }
}
```

**Fields used per mode:**

| Mode | Required fields | Optional fields |
|------|-----------------|-----------------|
| `opt_in` | *(none — backward compatible)* | — |
| `open` | — | `whatsapp_open_rate_limit` |
| `whitelist` | `whatsapp_allowed_jids` (array of strings) | — |
| `closed` | `whatsapp_allowed_user_id` (single string) | — |
| `scheduled` | `whatsapp_schedule` | `whatsapp_schedule.off_hours_reply` |

### Architecture: Core `resolve_access()`

The access gate is implemented in `isli-core/src/isli_core/access.py`:

```python
async def resolve_access(db, agent_id, user_id, channel) -> None:
    """Raises HTTPException(403/429) if access denied."""
```

**Flow:**
1. Core receives the webhook (`channels.py`)
2. Calls `resolve_access()` before session creation
3. Mode is read from `Agent.config['whatsapp_access_mode']`
4. On denial, Core raises `HTTPException` with a machine-readable `detail` string
5. The channel adapter catches `403`/`429` and maps `detail` to a user-facing localized reply

### Rate Limiting (`open` mode)

Open mode includes optional per-JID Redis rate limiting using a fixed-window counter:

```python
key = f"rate_limit:{user_id}:{window_seconds}"
current = await redis.incr(key)
if current == 1:
    await redis.expire(key, window_seconds)
if current > max_msgs:
    raise HTTPException(status_code=429, detail="rate_limited")
```

- Key auto-expires when the window elapses (no manual cleanup)
- If Redis is unavailable, rate limiting is silently skipped (availability over strictness)

### Schedule Checking (`scheduled` mode)

Uses Python 3.9+ `zoneinfo.ZoneInfo` to handle daylight saving and regional offsets correctly:

```python
def _is_within_schedule(schedule_cfg) -> bool:
    tz = ZoneInfo(schedule_cfg["timezone"])
    now = datetime.now(tz)
    for window in schedule_cfg["windows"]:
        if now.weekday() + 1 in window["days"]:
            if window["from"] <= now.time() <= window["to"]:
                return True
    return False
```

- `days` are 1-based: `1=Monday` … `7=Sunday`
- Invalid timezone falls back to `UTC` with a warning log
- Malformed time strings are skipped with a warning log

### Adapter Reply Mapping

Both WhatsApp and Telegram adapters share the same `_REJECTION_REPLIES` map:

| `detail` | Auto-reply text |
|----------|-----------------|
| `closed_mode` | "This assistant only accepts messages from its owner." |
| `not_in_whitelist` | "You're not on the access list for this agent." |
| `outside_schedule` | Custom `off_hours_reply` from config, or generic fallback |
| `consent_required` | "Welcome! Please send /start to begin chatting with this agent." |
| `rate_limited` | "You've sent too many messages. Please try again later." |

The `outside_schedule` reply supports a custom message from config so agents can say things like *"We're offline until 9am Morocco time."* instead of a generic error.

### UI Configuration (Board)

The agent detail page (`isli-board/src/components/AgentDetailPage.tsx`) includes a conditional form section inside the **Communication Channels** card:

- **Mode dropdown** — selects the access mode
- **Open mode** — max messages + window (seconds) inputs
- **Whitelist mode** — textarea for allowed numbers (one per line)
- **Closed mode** — single owner phone number input
- **Scheduled mode** — timezone `<select>`, day-of-week toggle buttons, from/to `<input type="time">`, off-hours reply `<textarea>`

Changes are saved into `Agent.config` via the existing `PUT /v1/agents/{id}` endpoint.

### Python 3.12 `datetime.UTC` Compatibility (Fixed 2026-05-29)

The Core command handler (`isli-core/src/isli_core/routers/commands.py`) used `datetime.now(datetime.UTC)` which does not exist in Python 3.12's `datetime` module. This caused the `/new` command to crash with:
```
AttributeError: type object 'datetime.datetime' has no attribute 'UTC'
```

**Fix:** Replaced all instances of `datetime.UTC` with `timezone.utc` (from `datetime import timezone`).

### Sidecar Healthcheck (2026-05-29)

The `whatsapp-sidecar` service now includes a Docker healthcheck:

```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:3001/health"]
  interval: 10s
  timeout: 5s
  retries: 5
  start_period: 30s
```

The `channels` service depends on `whatsapp-sidecar` with `condition: service_healthy` instead of `service_started`, ensuring the sidecar is fully ready before channels attempts to proxy requests to it.

### Direct Sidecar Queries (2026-05-29)

`WhatsAppAdapter.get_status()` and `get_qr()` now query the Node.js sidecar directly via `httpx.Client()` instead of relying on in-memory Python dicts. This means:

- Status and QR survive `isli-channels` container restarts.
- `create_session()` queries the sidecar first to check if the agent is already connected, preventing duplicate sessionstarts.

---

## Channels & Gateways Gaps (2026-05-11 Research)

The following gaps were identified during a parallel 12-agent research review. **Status reflects fixes applied on 2026-05-28.**

### High
| Gap | Status | Notes |
|-----|--------|-------|
| No webhook idempotency keys | ✅ Fixed | `WebhookIdempotency` wired into `handle_webhook`; dedup key extracts `payload.key.id` |
| No delivery confirmation or retry | ✅ Fixed | `send_message` retries 4x with exponential backoff; DLQ infrastructure exists but not yet wired |
| In-flight messages lost on crash | 🔄 Partial | `OfflineMessageQueue` exists but not yet integrated into send flow |
| WhatsApp "Connect" button does nothing | ✅ Fixed 2026-05-29 | Frontend surfaces errors; adapter queries sidecar directly; sidecar has Docker healthcheck |
| WhatsApp connected but no reply | ✅ Fixed 2026-05-29 | Multiple root causes fixed: (1) sidecar HMAC auth, (2) Core webhook secret env var, (3) JID preservation for LID privacy mode, (4) consent 403 auto-reply |

### Medium
| Gap | Status | Notes |
|-----|--------|-------|
| No cross-channel user identity linking | ❌ Open | Same person on Telegram and WhatsApp gets independent sessions |
| Channel-specific message size limits | ✅ Fixed | `MessageChunker` enforces WhatsApp 1600-char limit |
| No offline message queue | 🔄 Partial | `OfflineMessageQueue` implemented but not auto-drained on recovery |
| No message ordering guarantee | ❌ Open | Concurrent processing could append messages out of order |
| No platform rate-limit backoff | 🔄 Partial | `RateLimiter` exists; wired in `main.py` but not in adapter send flow yet |
| Attachments not normalized | ✅ Fixed | WhatsApp adapter extracts image/video/audio/document metadata and forwards to Core |
| Agent restart loses in-flight tasks | ❌ Open | No checkpointing for pending outbound messages |

### Low
- ~~**Voice (phone) channel dependencies undefined**~~ — **Fixed 2026-05-29**. Telegram voice messages are auto-transcribed via `isli-audio` (faster-whisper + piper-tts). ASR/TTS providers, fallback strategy, and latency budget are now documented in `isli-audio`. Phone channel remains planned (Twilio Voice).

### Compliance
- **No user consent capture** — personal data is processed from the first inbound message with no documented legal basis.
  - **Fixed 2026-05-29:** WhatsApp adapter now auto-replies with `/start` prompt when consent is missing. Core `/start` command grants consent and sends welcome message.
- **CAN-SPAM / TCPA gaps** — Email and SMS channels lack unsubscribe, opt-out, and prior-express-consent mechanisms.
- **No Data Processing Agreements** — no DPAs documented for Telegram, Twilio, Meta Cloud, or SMTP hosts.

> See `Memory/ISLI-Research-Report.md` for full details and recommendations.
>
> **Update 2026-05-21:** WhatsApp Web channel (pyaileys) is now implemented with QR code pairing, per-agent auth folders, reconnection watchdog, and platform-specific constants (chunking, rate limits, attachments, idempotency). Some Medium-priority gaps above (chunking, rate limits) are already addressed in code but were flagged during the 2026-05-11 review before the implementation was complete.
>
> **Update 2026-05-28:** Critical security and reliability fixes deployed:
> - Webhook authentication (X-Sidecar-Secret + Bearer token)
> - Fixed idempotency key extraction (`payload.key.id`)
> - Added outbound retry with exponential backoff
> - Message chunking enforced for WhatsApp
> - Attachment forwarding from WhatsApp to Core
> - Real health checks via sidecar `/health`
> - Redis session keys now have 30-day TTL
> - Hardened sidecar auto-start loop with per-agent error isolation