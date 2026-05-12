# Research Agent 12: Channels & User Experience — Findings Report

**Date:** 2026-05-11
**Scope:** `07-channels.md`, `05-kanban.md`, `04-agents.md` (plus supporting context from `01-architecture.md`, `02-keeper.md`, `03-memory.md`, `08-failure-modes.md`)
**Author:** Research Agent 12

---

## Domain Summary

ISLI's channel gateway architecture is a thin adapter pattern that translates platform-specific messages (Telegram, WhatsApp, Email, Web) into ISLI Tasks and back again. While the interface is clean and extensible, the documented message flows are optimistic "happy path" designs with no evident retry, deduplication, ordering, or graceful-degradation semantics. Production deployments will need substantial reliability engineering before the gateway layer can survive platform outages, duplicate webhooks, or gateway process crashes.

---

## Findings Table

| ID | Severity | Category | Description | Evidence | Recommendation |
|----|----------|----------|-------------|----------|----------------|
| CH-01 | **High** | Reliability | **No idempotency key handling for inbound webhooks.** Duplicate webhook deliveries (common from Telegram, Twilio, Meta) would create duplicate Task cards in INBOX. | `07-channels.md` lines 73–91: webhook POST → parse update → POST /api/tasks. No deduplication key, hash, or sequence number is extracted or checked. | Add idempotency key extraction per platform (e.g., `update_id` for Telegram, `MessageSid` for Twilio) and maintain a Redis-based deduplication window (≥24h) before task creation. |
| CH-02 | **High** | Reliability | **No delivery confirmation or retry mechanism for outbound messages.** If the Telegram/WhatsApp API call fails, the response is silently dropped with no retry, DLQ, or user-visible failure state. | `07-channels.md` lines 95–109: Agent → Core API → Gateway → Platform API. No acknowledgment path, retry count, or delivery status is shown. | Implement at-least-once delivery: attach a delivery status enum (`pending`, `sent`, `delivered`, `failed`, `dead_letter`) to the Task model; add exponential-backoff retry and a dead-letter queue for permanent failures. |
| CH-03 | **High** | Reliability | **In-flight messages are lost on gateway crash.** There is no transactional handoff or persistence layer between Core API and the gateway process. | `07-channels.md` describes gateways as "thin adapters" with no message queue between Core API and Platform API. `01-architecture.md` places gateways at Layer 4 with no local store. | Insert a durable message queue (Redis Streams, NATS, or RabbitMQ) between Core API and channel gateways so in-flight outbound messages survive gateway restarts. |
| CH-04 | **Medium** | UX / Identity | **No cross-channel user identity linking.** The same human user on Telegram and WhatsApp receives two independent sessions with two different session IDs. | `07-channels.md` lines 113–121: "Each unique `(channel, channel_user_id)` pair gets its own session ID." No user identity registry or linking mechanism exists. | Add a `user_profiles` table with verified identity linking (e.g., OTP, deep-link token, or email verification) so a single `user_id` can own multiple `channel_user_id` entries and sessions merge. |
| CH-05 | **Medium** | UX | **Channel-specific message size limits are not enforced.** Telegram (4096 chars) and WhatsApp (~1600 chars) limits are not mentioned; long responses may be truncated or rejected by platform APIs. | `07-channels.md` `send_message` interface accepts raw `text: str` with no size parameter, chunking logic, or platform-aware truncation. | Extend `ChannelAdapter.send_message` to compute per-platform limits and auto-split long messages into sequential chunks, or warn the agent to summarize. |
| CH-06 | **Medium** | Reliability | **No offline message queue for unavailable platforms.** If Telegram or Twilio is down, outbound messages are dropped immediately rather than queued for later delivery. | `07-channels.md` outbound flow shows a direct Platform API call with no fallback path or queue. | Implement per-channel offline queues (TTL-based) that hold outbound messages during platform outages and retry once health checks pass. |
| CH-07 | **Medium** | Reliability | **No message ordering guarantee within a session.** Concurrent gateway requests or async processing could append messages to Session Memory out of order. | `07-channels.md` shows async webhook → parse → POST /api/tasks. `03-memory.md` Tier 1 appends messages immediately with no sequence number or causal ordering primitive. | Add a monotonic `sequence_number` per session to every inbound message; enforce ordering in Session Memory append or reject out-of-order updates. |
| CH-08 | **Medium** | Reliability | **No platform rate-limit backoff strategy.** When Telegram or Twilio returns HTTP 429, the gateway has no documented adaptive backoff, circuit breaker, or queue-and-retry behavior. | `01-architecture.md` line 157 mentions "Rate limited" at the Channels boundary, but `07-channels.md` contains zero rate-limit handling logic. | Implement per-platform circuit breakers and adaptive backoff (e.g., respect `Retry-After` headers). Queue messages while the breaker is open and alert operators via the Kanban board. |
| CH-09 | **Medium** | UX | **Attachments are not normalized across channels.** The inbound flow extracts attachments, but the outbound `send_message` interface only accepts text. There is no cross-channel media conversion. | `07-channels.md` line 79: "Extract user_id, message_text, attachments" in inbound. Lines 95–109: outbound only sends `text`. `ChannelAdapter` interface has no attachment parameter. | Extend `ChannelAdapter` with `send_media(channel_user_id, media_type, url_or_bytes, caption)` and implement per-channel format/size conversion (e.g., HEIC→JPEG for WhatsApp, size limits for Telegram). |
| CH-10 | **Medium** | Reliability | **Agent restart does not preserve in-flight channel tasks.** While Keeper re-injects compaction summaries on restart, tasks that are `in_progress` and their pending outbound messages are not checkpointed or resumed. | `08-failure-modes.md` F8: "On agent restart, Keeper re-injects the last compaction summary." `04-agents.md` shows standalone processes with no task checkpointing. | Add task-level checkpointing: serialize agent turn state to PostgreSQL on every tool call; on restart, reload the latest checkpoint and resume the turn, preserving pending outbound messages. |
| CH-11 | **Low** | Dependencies | **Voice (phone) channel ASR/TTS dependencies are undefined.** The channel is marked "Planned" with Twilio Voice + ASR, but no ASR/TTS provider, fallback strategy, or latency budget is specified. | `07-channels.md` line 69: "Voice (phone) — Planned — Twilio Voice + ASR." No further detail on ASR engine (Whisper? Google? Azure?) or TTS provider. | Document ASR/TTS provider selection criteria, fallback to text-only mode when speech services fail, and latency SLAs before implementation begins. |

---

## Cross-Cutting Concerns

1. **Memory / Session Overlap:** Session continuity is described in `03-memory.md` (Redis TTL + Keeper compaction), but channel-level message durability is completely absent. The 4-tier memory model does not extend to *undelivered outbound messages*, which means a delivery gap cannot be recovered from memory alone.

2. **Architecture Overlap:** Gateway crash recovery and backpressure are partially noted in `agent-01-architecture.md` (finding F-ARCH-04) as overlapping with the Channels domain, but no resolution is present in `07-channels.md`. The two findings should be addressed together.

3. **Observability Overlap:** Per-channel metrics are flagged in `agent-04-observability.md` (finding OBS-12) as missing. Implementing CH-01 through CH-03 will require corresponding observability changes (delivery latency, retry counts, DLQ depth) that should be tracked alongside OBS-12.

4. **Security Overlap:** Duplicate webhook handling (CH-01) is not just a reliability issue—it is also a security issue. An attacker replaying a Telegram webhook could spam the INBOX or trigger duplicate task execution. Idempotency keys also serve as replay-attack mitigation.

---

## Confidence per Finding

| Finding | Confidence | Rationale |
|---------|------------|-----------|
| CH-01 | **High** | Absence of idempotency keys is explicitly verifiable from the webhook flow diagram and `ChannelAdapter` interface. |
| CH-02 | **High** | The outbound flow diagram ends at "Platform API call" with no return path, retry logic, or status update. |
| CH-03 | **High** | Gateways are described as thin, stateless adapters with no persistence layer; message loss on crash is a direct consequence. |
| CH-04 | **High** | Session ID generation rule is explicitly `(channel, channel_user_id)` with no linking abstraction. |
| CH-05 | **High** | `send_message` signature accepts only `text: str`; no truncation or chunking is present. |
| CH-06 | **High** | Outbound flow is a direct synchronous call with no queue or retry-on-recovery path. |
| CH-07 | **High** | Session Memory appends by timestamp with no sequence number or ordering lock. |
| CH-08 | **High** | Rate-limiting is mentioned only as a boundary policy, with zero implementation detail in gateway code or docs. |
| CH-09 | **High** | Inbound extracts attachments but outbound interface has no attachment parameter; cross-channel media handling is impossible as documented. |
| CH-10 | **Medium** | Agent restart behavior is partially mitigated by Keeper compaction, but in-flight task preservation is not mentioned and likely absent. |
| CH-11 | **Medium** | Voice is a planned feature; dependencies may exist in an unreviewed backlog or design doc. The finding is based solely on the absence of detail in reviewed files. |

---

## Summary

The ISLI channel layer is architecturally clean but operationally immature. The eleven findings above cluster into three themes:

1. **Delivery Guarantees (CH-01, CH-02, CH-03, CH-06, CH-07, CH-08):** The channel layer lacks idempotency, retry, ordering, and crash recovery. These are prerequisites for production use.
2. **Cross-Channel UX (CH-04, CH-05, CH-09):** Users cannot be recognized across channels, long messages may break, and media attachments have no cross-platform path.
3. **Planned Feature Risks (CH-10, CH-11):** Session continuity under agent restart is incomplete, and the voice channel's dependencies are undefined.

Resolving the High-severity reliability findings (CH-01, CH-02, CH-03) should be the top priority before any production channel gateway deployment.
