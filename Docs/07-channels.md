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

## Message Flow: Inbound (User → Agent)

```
Platform (e.g., Telegram)
  └─→ Webhook POST to Gateway (e.g., /webhook/telegram/{agent_id})
        └─→ Gateway parses update
              ├─ Extract user_id, message_text, attachments
              ├─ Normalize to ISLI Message format
              └─→ Core API: POST /api/tasks
                    {
                      type: "user_request",
                      agent_id: "agent_research",
                      input: "...",
                      channel: "telegram",
                      channel_user_id: "123456789",
                      session_id: "sess_tg_123456789"  ← per-user session
                    }
                    └─→ Kanban board: new card in INBOX
```

---

## Message Flow: Outbound (Agent → User)

```
Agent completes task
Core API: task.status = done, task.output = "..."
Core API: notifies channel gateway
  └─→ Gateway: POST /send
        {
          channel: "telegram",
          channel_user_id: "123456789",
          text: "...",
          reply_to_message_id: "..."
        }
        └─→ Platform API call (Telegram sendMessage)
```

---

## Session Continuity per Channel

Each unique `(channel, channel_user_id)` pair gets its own **session ID** that persists across messages. This means:
- Telegram user 123456789 always continues the same session with Research agent
- Keeper maintains their message history across conversations
- Agent remembers who they are and past interactions

Sessions expire after 24 hours of inactivity (configurable).

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