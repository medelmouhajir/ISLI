# 10 — Phased Development Roadmap

> **Last updated:** 2026-06-01 (all phases complete + post-roadmap additions)

This roadmap is derived from the comprehensive 12-agent research review documented in `Memory/ISLI-Research-Report.md`. It prioritizes findings by severity × likelihood, grouping them into phased milestones.

**Status: ALL PHASES IMPLEMENTED**

---

## Phase 0 — Foundation (Weeks 1–2) ✅

**Goal:** Establish the codebase and deployment infrastructure that every other phase depends on.

| Task | Finding ID | Effort | Deliverable |
|------|-----------|--------|-------------|
| Initialize repository structure | — | 1 day | `isli-core/`, `isli-keeper/`, `isli-board/`, `isli-skills/`, `isli-channels/` directories |
| Create `docker-compose.yml` on disk | F-DEP-01 | 2 days | Production-ready compose with health checks, resource limits, restart policies |
| Fix Docker networking | F-ARCH-10 | 1 day | `.env.docker` using Compose service names; separate `.env.local` for native dev |
| Add dependency manifests | F-DEP-03 | 2 days | `pyproject.toml` (Poetry/uv), `package-lock.json`, exact semver pins |
| Add database migrations | F-DEP-02 | 2 days | Alembic async setup with initial migration for all documented schemas |
| Pre-pull Ollama models | F-DEP-04 | 1 day | Init container or startup script for `ollama pull` |
| Add health check endpoints | F-OBS-04 | 2 days | `/health`, `/ready`, `/live` on Core API, Keeper, and skills |
| Add structured JSON logging | F-OBS-03 | 2 days | `structlog` with standardized schema across all services |
| Add OpenTelemetry tracing | F-OBS-01 | 3 days | Mandatory OTel with `trace_id` on Task model and W3C propagation |

**Exit criteria:** `docker-compose up` starts all services successfully; health checks pass; a test task flows from Telegram → Core → Keeper → Agent → Response with a visible trace in Jaeger. ✅

---

## Phase 1 — Safety & Governance (Weeks 3–4) ✅

**Goal:** Implement the hard safety gates that prevent runaway costs, cascading failures, and regulatory liability.

| Task | Finding ID | Effort | Deliverable |
|------|-----------|--------|-------------|
| Implement token budget enforcement | F-COST-01 | 3 days | Hard caps in Core API proxy; auto-pause on breach |
| Add circuit breakers | F-RES-01 | 4 days | On WebSocket pool, Skills proxy, model API calls |
| Add delegation cycle detection | F-COORD-01 | 2 days | DAG validation at registration + runtime cycle detector |
| Add chain depth limits | F-COORD-05 | 1 day | Max depth = 3; human approval for depth 2+ |
| Fix GDPR/Tier 4 conflict | F-COMP-01 | 4 days | Soft-delete + crypto-shredding; retention schedule; purging job |
| Add user consent capture | F-COMP-03 | 3 days | Consent-management layer per channel; gate task creation |
| Secure Ollama | F-SEC-01 | 2 days | API key or mTLS; restrict to Keeper identity only |
| Add skill internal auth | F-SEC-02 | 3 days | mTLS or internal JWT between Core API and skills |
| Add SSRF defense | F-SEC-03 | 2 days | URL blocklists + sandboxed HTTP client in `web-fetch` |
| Add event schema registry | F-ARCH-03 | 3 days | JSON Schema versioning + backward-compatibility CI check |
| Add task state locking | F-ARCH-05 | 2 days | Optimistic locking with `version` field |

**Exit criteria:** A chaos test validates that: (a) an agent exceeding its token budget is paused, (b) a cyclic delegation is rejected, (c) a user deletion request scrubs their data from all tiers, and (d) a skill directly accessed without Core API proxy is rejected. ✅

---

## Phase 2 — Resilience & Recovery (Weeks 5–6) ✅

**Goal:** Add structural resilience patterns so the system survives component failures without human intervention.

| Task | Finding ID | Effort | Deliverable |
|------|-----------|--------|-------------|
| Add agent turn checkpointing | F-RES-02 | 4 days | Serialize `messages` array to PostgreSQL before each tool call |
| Add global e-stop | F-RES-10 | 2 days | Global pause topic on Task Bus; drains in-flight turns |
| Add retry with exponential backoff | F-RES-05 | 2 days | Config in `agent.yaml` and Skills manifest; enforced in proxy |
| Add fallback agents | F-RES-08 | 2 days | `fallback_agent_id` in `agent.yaml`; auto-reassign on OFFLINE |
| Add dead-letter queue | F-RES-12 | 2 days | `Failed` Kanban column with retry count + human retry action |
| Add partial failure handling | F-RES-09 | 2 days | `PartialResult` schema + idempotency keys on skill calls |
| Add bulkhead pattern | F-RES-11 | 3 days | Per-agent connection limits + per-skill thread pools |
| ~~Add Keeper fallback~~ | F-KEEP-02 | — | **Rejected 2026-05-19 / 2026-06-03** — Keeper uses honest 503, not cloud fallback or circuit breaker. Resilience lives in Core/SDK. |
| Add Redis AOF persistence | F-DEP-06 | 1 day | Custom `redis.conf` with `appendonly yes` |
| Add backup strategy | F-DEP-05 | 3 days | pg_dump cron + ChromaDB snapshot + Redis RDB to S3/MinIO |
| Add chaos engineering suite | F-RES-06 | 4 days | Fault injection: agent crash, skill latency, Redis flush, prompt injection |

**Exit criteria:** A full-stack chaos test simulates: (a) Core API restart mid-agent-turn with state recovery, (b) Keeper failure with honest 503 propagation to Core, (c) Redis crash with AOF replay, and (d) skill failure with partial result delivery. ✅

---

## Phase 3 — Channels & Delivery Guarantees (Weeks 7–8) ✅

**Goal:** Make channel gateways production-reliable with delivery guarantees and cross-channel UX.

| Task | Finding ID | Effort | Deliverable |
|------|-----------|--------|-------------|
| Add webhook idempotency | F-CH-01 | 2 days | Platform-specific ID extraction + Redis dedup window |
| Add delivery retry + DLQ | F-CH-02 | 3 days | At-least-once delivery with exponential backoff and dead-letter queue |
| Add gateway crash recovery | F-CH-03 | 3 days | Durable message queue between Core API and gateways |
| Add message ordering | F-CH-07 | 2 days | Monotonic `sequence_number` per session |
| Add rate-limit backoff | F-CH-08 | 2 days | Per-platform circuit breakers respecting `Retry-After` |
| Add offline message queue | F-CH-06 | 2 days | Per-channel queues for platform outages |
| Add message size enforcement | F-CH-05 | 2 days | Per-platform chunking in `ChannelAdapter.send_message` |
| Add cross-channel identity | F-CH-04 | 3 days | `user_profiles` table with verified linking |
| Add attachment normalization | F-CH-09 | 3 days | Cross-channel media type conversion |
| Add webhook secret validation | F-SEC-08 | 2 days | HMAC signature verification per platform |

**Exit criteria:** A 24-hour soak test validates: (a) duplicate webhooks create zero duplicate tasks, (b) a gateway restart preserves in-flight messages, (c) a Telegram rate-limit is respected with backoff, and (d) a 5000-character response is correctly chunked for WhatsApp. ✅

---

## Phase 4 — Memory & Data Integrity (Weeks 9–10) ✅

**Goal:** Harden the 4-tier memory system for consistency, versioning, and scale.

| Task | Finding ID | Effort | Deliverable |
|------|-----------|--------|-------------|
| Pin embedding model versions | F-MEM-01 | 2 days | Store model identifier with each vector; migration job on change |
| Add ChromaDB backup | F-MEM-02 | 2 days | Scheduled snapshots to object storage + tested restore |
| Add summary/embedding validation | F-MEM-03 | 2 days | Cosine-similarity gate between summary and original |
| Add compaction quality benchmark | F-MEM-04 | 3 days | ROUGE-L or semantic similarity regression test |
| Add Tier 4 partitioning | F-MEM-05 | 2 days | Monthly PostgreSQL partitioning + cold storage migration |
| **Dual-write atomicity (Episodic)** | F-MEM-09 | 3 days | **DONE** (Integrated into PostgreSQL via pgvector) |
| **Semantic memory dedicated API** | F-MEM-10 | 2 days | **DONE** (Implemented in Core API /v1/memory) |
| Add importance decay + GC | F-MEM-11 | 2 days | Exponential decay function + scheduled physical deletion |
| **Cache invalidation** | F-MEM-12 | 1 day | **DONE** (Handled via Core API writes) |
| **Vector dimension guard** | F-MEM-13 | 1 day | **DONE** (Strictly enforced in SQLAlchemy model) |
| **Consistency regression tests** | F-MEM-14 | 3 days | **DONE** (Added semantic API and injection tests) |
| Add archival table indexes | F-MEM-15 | 1 day | Composite indexes on `(agent_id, created_at)` |

**Exit criteria:** A data integrity test validates: (a) changing the embedding model triggers a re-computation migration, (b) a compaction summary scores above the quality threshold, (c) a dual-write failure is recovered via the outbox, and (d) a 1-year-old partition is migrated to cold storage. ✅

---

## Phase 5 — Cost Optimization & Model Tiering (Weeks 11–12) ✅

**Goal:** Reduce operational costs and prevent runaway API spend.

| Task | Finding ID | Effort | Deliverable |
|------|-----------|--------|-------------|
| Build cost estimator | F-COST-02 | 2 days | Rate-card calculator with per-agent monthly projections |
| Implement model fallback | F-COST-03 | 3 days | Three-tier fallback: expensive → cheap → local → pause |
| Add root-task cost accumulator | F-COST-04 | 2 days | Sum token usage across all child tasks; alert on threshold |
| Add task-complexity routing | F-COST-05 | 3 days | Keeper-side score to route trivial tasks to cheaper models |
| Add response semantic cache | F-COST-09 | 3 days | Cache keyed by task embedding similarity; track hit rate |
| Add per-agent cost dashboard | F-COST-08 | 2 days | Cost ledger table + Kanban Agent Status Bar widget + `/costs` analytics page with recharts (spend trend, tier breakdown, agent leaderboard, budget status) |
| Add cost anomaly detection | F-COST-07 | 2 days | Per-agent p95 historical baselines + alert routing |
| Add embedding cache | F-SCA-05 | 2 days | Redis LRU cache keyed by content hash |
| Add local-model TCO worksheet | F-COST-06 | 1 day | Electricity + depreciation + labor model |

**Exit criteria:** A benchmark shows: (a) 15x cost reduction on simple tasks via model tiering, (b) 25% cache hit rate on embeddings, (c) a delegation chain that exceeds its budget is halted before the third child task, and (d) the Kanban board shows real-time per-agent spend via `POST /v1/agents/{id}/usage` endpoint, `GET /system/cost/history`, `GET /system/cost/by-tier`, and the `/costs` analytics page. ✅

---

## Phase 6 — Compliance & Audit Hardening (Weeks 13–14) ✅

**Goal:** Meet GDPR, SOC 2, and ISO 42001 requirements for production deployments.

| Task | Finding ID | Effort | Deliverable |
|------|-----------|--------|-------------|
| Add SAR fulfillment pipeline | F-COMP-04 | 3 days | Aggregate user data across Tiers 1–4; deliver JSON within 30 days |
| Add DPO assessment | F-COMP-05 | 2 days | Necessity assessment under GDPR Art. 37 and MENA laws |
| Add data residency controls | F-COMP-06 | 4 days | Geo-fenced DB instances + SCCs for cross-border transfers |
| Add CAN-SPAM/TCPA compliance | F-COMP-07 | 3 days | Unsubscribe/opt-out + consent logging for Email/SMS |
| Add DPAs with channel providers | F-COMP-08 | 3 days | Vendor compliance register with signed addenda |
| Add audit trail cryptographic integrity | F-COMP-10 | 3 days | Merkle/chain hash on each archival row |
| Encrypt raw PII in archive | F-COMP-11 | 2 days | AES-256-GCM for `content` + `channel_user_id` |
| Add Meta Business compliance addendum | F-COMP-12 | 2 days | Messaging-template rules, 24h session policies |
| Add HIPAA/SOC 2/ISO 42001 mapping | F-COMP-13 | 3 days | Control-objective mapping if serving regulated industries |
| Add Transfer Impact Assessment | F-COMP-14 | 2 days | TIA per jurisdiction with documented SCCs |

**Exit criteria:** A third-party compliance audit confirms: (a) a user deletion request scrubs all PII including embeddings, (b) an audit trail row cannot be tampered with without detection, (c) all channel providers have signed DPAs on file, and (d) data residency controls prevent EU data from leaving the EU region. ✅

---

## Phase 7 — Scale-Out & Production Topology (Weeks 15–16) ✅

**Goal:** Enable horizontal scaling beyond single-machine deployment.

| Task | Finding ID | Effort | Deliverable |
|------|-----------|--------|-------------|
| Document scale-out lane | F-SCA-03 | 2 days | Load balancer + stateless Core API + shared Redis/PostgreSQL |
| Add service mesh / reverse proxy | F-ARCH-08 | 3 days | Traefik or nginx with health-check routing |
| Add API versioning | F-ARCH-06 | 2 days | `/v1/` prefix + OpenAPI spec + SDK compatibility matrix |
| Add graceful shutdown | F-ARCH-07 | 2 days | SIGTERM handling + WebSocket draining + task persistence |
| Add Redis Sentinel/Cluster | F-SCA-06 | 3 days | HA Redis with failover |
| Add ChromaDB server mode | F-SCA-01 | 3 days | Standalone ChromaDB process or migration to pgvector |
| Add Ollama load balancing | F-KEEP-09 | 3 days | Ollama replica set or remote inference path |
| Add blue/green deployment | F-DEP-08 | 3 days | Reverse proxy with instant upstream swap |
| Add IaC modules | F-DEP-10 | 4 days | Terraform/Pulumi for compute, networking, IAM, managed DB/cache |
| Add CI/CD pipeline | F-DEP-16 | 3 days | GitHub Actions for lint, test, build, scan, push |

**Exit criteria:** A load test with 20 concurrent agents demonstrates: (a) Core API scales to 3 instances behind a load balancer, (b) Redis Sentinel fails over without session loss, (c) a blue/green deployment swaps versions with zero dropped tasks, and (d) the infrastructure can be provisioned from Terraform in < 15 minutes. ✅

---

## Milestone Summary

| Phase | Weeks | Theme | Status |
|-------|-------|-------|--------|
| 0 | 1–2 | Foundation | ✅ Complete |
| 1 | 3–4 | Safety | ✅ Complete |
| 2 | 5–6 | Resilience | ✅ Complete |
| 3 | 7–8 | Channels | ✅ Complete |
| 4 | 9–10 | Memory | ✅ Complete |
| 5 | 11–12 | Cost | ✅ Complete |
| 6 | 13–14 | Compliance | ✅ Complete |
| 7 | 15–16 | Scale-Out | ✅ Complete |

---

## Post-Roadmap — Task Attachments & Shared Workspaces (2026-05-25) ✅

**Goal:** Enable agents and users to attach files to tasks and collaborate via shared filesystem scopes.

| Task | Effort | Deliverable |
|------|--------|-------------|
| Task attachment backend | 1 day | `attachments` JSON column + `retain_attachments` boolean on `Task` model; `POST /v1/tasks/{id}/attachments/attach` endpoint; workspace `attachment` scope |
| Task attachment frontend | 1 day | `TaskAttachment` TypeScript interface; attachment list with download in `TaskDetailModal.tsx` |
| Shared workspace backend | 2 days | `SharedWorkspace` model + CRUD router with owner/member RBAC; `POST/DELETE /members/{id}`; `POST /promote`; soft delete; `quota_bytes` enforcement |
| Shared workspace frontend | 2 days | `SharedWorkspacesPage.tsx`, `SharedWorkspaceDetailPage.tsx`, `useSharedWorkspaces.ts` hooks; Sidebar nav item |
| Workspace quota parameterization | 1 day | `quota_bytes` parameter on workspace `write`, `upload`, and `promote` endpoints; shared scope reads quota from Core |
| Agent SDK shared tools | 1 day | `shared_file_read`, `shared_file_write`, `shared_file_list`, `shared_file_delete`, `promote_output` with typed exceptions |

**Exit criteria:**
- Agent can attach a file to a task and the Board shows it with a working download link.
- Owner can create a shared workspace, add members, and write files within the shared scope.
- Upload exceeding `quota_bytes` returns HTTP `413`.
- Non-member cannot list or access the shared workspace via Core or workspace service.

---

## Post-Roadmap — Runtime Configuration (2026-05-24) ✅

**Goal:** Eliminate hardcoded operational constants so administrators can tune system behavior via the Board UI without redeploying.

| Task | Effort | Deliverable |
|------|--------|-------------|
| Add `SystemSetting` model & migration | 1 day | `system_settings` table with JSON `value`, `scope`, `updated_at` |
| Build dynamic config helper | 1 day | `dynamic_config.py` with 30s TTL cache + invalidation API |
| Extend settings router with CRUD | 1 day | `GET/PUT/DELETE /v1/settings/{key}` with audit log integration |
| Wire dynamic reads into core modules | 2 days | `session_cron`, `delegation`, `retry`, `dlq`, `bulkhead`, `circuit_breaker`, `main.py` CORS |
| Build General Settings page | 2 days | `GeneralSettingsPage.tsx` with 12 grouped knobs, debounced mutations |
| Board integration | 1 day | Enable General card in `SettingsPage.tsx`, add `/settings/general` route |
| **Implement Advanced Agent Skills** | 1 day | **DONE** (`create-kanban-task`, `create-engineering-plan`) |

**Exit criteria:**
- Board → Settings → General loads and edits all 12 knobs
- `PUT /v1/settings/session_idle_timeout_minutes` returns updated value immediately
- Session cron reads the new timeout from DB on next run
- Audit logs contain a signed record for every mutation

---

## Post-Roadmap — Local Audio Service (STT/TTS) (2026-05-29) ✅

**Goal:** Add local speech-to-text and text-to-speech capabilities via a dedicated `isli-audio` microservice, managed from the same Board UI as Ollama models.

| Task | Effort | Deliverable |
|------|--------|-------------|
| Audio service scaffold | 1 day | `isli-audio/` FastAPI service with `/stt/transcribe`, `/tts/synthesize`, `/admin/*`, `/models`, `/dashboard` |
| STT engine | 0.5 day | `faster-whisper` wrapper with `int8` quantization, multipart upload |
| TTS engine | 0.5 day | `piper-tts` wrapper with auto-download from HuggingFace |
| Model manager | 0.5 day | JSON persistence for `stt`/`tts` slots + `tts_voices_by_language` mapping |
| Core integration | 0.5 day | `SKILL_REGISTRY` entries for `speech-to-text` / `text-to-speech`; model-management router routing audio slots to `isli-audio` |
| Agent SDK audio tools | 0.5 day | `speech_to_text` and `text_to_speech` async functions + LiteLLM definitions in `isli_agent/tools/audio.py` |
| Telegram voice transcription | 0.5 day | `TelegramAdapter._transcribe_voice()` with multipart upload to `isli-audio`; auto-replaces message text before Core forwarding |
| Board UI audio module | 0.5 day | Third module `[KM-03-AUD]` on `/settings/keeper` with `stt`/`tts` sub-slots |
| Docker Compose wiring | 0.5 day | `audio` service (port 8400, 4CPU/4G), `audio_models` volume, env vars, health check |
| Docs update | 0.5 day | Update `01-architecture.md`, `06-skills.md`, `07-channels.md`, `09-tech-stack.md`, `10-roadmap.md`, `04-agents.md`, `README.md` |

**Exit criteria:**
- Telegram voice message sent to agent → adapter transcribes via `isli-audio` → agent receives text.
- Agent calls `text_to_speech` skill → receives audio URL → can send to user.
- Board UI shows Audio Processing module with active/available/missing states for STT and TTS models.
- All containers healthy after `docker compose up --build`.

---

## Post-Roadmap — Enhanced WhatsApp Access Mode System (2026-05-29) ✅

**Goal:** Replace the single hardcoded opt-in behavior with five distinct access modes so each agent can define its own audience policy — from fully public support bots to owner-only private assistants.

| Task | Effort | Deliverable |
|------|--------|-------------|
| Core `resolve_access()` module | 1 day | `isli-core/src/isli_core/access.py` with `resolve_access()` supporting `opt_in`, `open`, `whitelist`, `closed`, `scheduled` |
| Core webhook router integration | 0.5 day | Replace flat consent gate in `channels.py` with mode-aware `resolve_access()` call |
| Redis rate limit helper | 0.5 day | Fixed-window counter with TTL for `open` mode per-JID throttling |
| Schedule checker helper | 0.5 day | `zoneinfo`-based time-window validation with fallback to UTC |
| WhatsApp adapter reply mapping | 0.5 day | Catch `403`/`429` and map detail strings to human-readable WhatsApp replies |
| Telegram adapter parity | 0.5 day | Same reply mapping for Telegram `403`/`429` responses |
| Board UI conditional form | 1 day | Mode dropdown + per-mode fields (rate limit, whitelist textarea, closed phone input, scheduled day/time/timezone pickers) in `AgentDetailPage.tsx` |
| Backend + adapter tests | 1 day | 30 core tests + 4 adapter tests; all passing |
| Docker rebuild & restart | 0.5 day | Rebuild `core`, `channels`, `board`; verify healthy |
| Docs update | 0.5 day | Update `07-channels.md`, `04-agents.md`, `10-roadmap.md` |

**Exit criteria:**
- An agent configured as `open` with rate limits auto-grants consent and rejects spam after the limit.
- An agent configured as `closed` rejects all messages except from the single owner number.
- An agent configured as `scheduled` rejects messages outside business hours with a custom reply.
- The Board UI shows conditional fields and saves into `Agent.config` correctly.
- All existing `opt_in` behavior remains unchanged (backward compatible).

---

## Post-Roadmap — Board UI Voice Input (STT) (2026-05-29) ✅

**Goal:** Enable hands-free message entry in the Board UI by adding a microphone button to the chat input. Recorded audio is transcribed via the local `isli-audio` service and inserted into the message input, with an optional auto-send toggle.

| Task | Effort | Deliverable |
|------|--------|-------------|
| Core `/stt/transcribe` endpoint | 0.5 day | `isli-core/src/isli_core/routers/stt.py` — admin-auth protected, accepts `multipart/form-data` audio upload, forwards base64 to `isli-audio` with internal JWT, returns `{text, language, confidence, model}` |
| Core router registration | 0.1 day | Wire `stt.router` into `isli-core/src/isli_core/main.py` under `/v1` |
| `useVoiceRecorder` hook | 0.5 day | Browser `MediaRecorder` (webm/opus fallback), mic permission handling, `FormData` upload to `/v1/stt/transcribe`, error states |
| `ChatInput` reusable component | 0.5 day | Mic button (red pulse while recording, spinner while processing), auto-send toggle, text input, send button, transient error tooltip |
| `Toggle` UI component | 0.2 day | Sharp-cornered toggle switch matching industrial theme (`rounded-none`, `accent-cyan`) |
| Integrate into SessionsPage | 0.2 day | Replace inline input with `<ChatInput>`; wire `messageText` / `handleSendMessage` |
| Integrate into ConversationsPage | 0.2 day | Same replacement; respect closed-session disabled state |
| Type-check & build | 0.2 day | `tsc --noEmit` clean; `npm run build` passes |
| Docker rebuild & restart | 0.3 day | Rebuild `core` + `board`; `docker compose up -d --force-recreate` |
| Docs update | 0.2 day | Update `01-architecture.md`, `07-channels.md`, `10-roadmap.md`, `README.md` |

**Exit criteria:**
- Board Sessions page shows a mic icon next to the input field.
- Clicking mic starts browser recording; clicking again stops and transcribes.
- Transcribed text appears in the input (auto-send OFF) or sends immediately (auto-send ON).
- Recording errors (permission denied, no mic, STT failure) show a transient error tooltip.
- All containers healthy after rebuild.

---

## Post-Roadmap — Immersive Chat UI (Agent-Driven Components) (2026-05-29 / Phase 2: 2026-05-30) ✅

**Goal:** Let agents render typed React UI components inline in the Board chat stream. User interactions (clicking rows/buttons, submitting forms) flow back as `role: action` messages into the same conversation context.

### Phase 1 (2026-05-29) — Read-only + Simple Interaction

| Task | Effort | Deliverable |
|------|--------|-------------|
| Polymorphic structured message schema | 1 day | `ComponentPayload` with `component_type`; `SessionReplyIn` + `SessionActionIn` Pydantic models; action dedup guard |
| Core session routers | 1 day | `POST /v1/sessions/{id}/reply` appends `components` to message dicts; `POST /v1/sessions/{id}/action` appends `role: action` messages; 1s dedup lock |
| SDK tool + runner stashing | 1 day | `render_ui_component()` with 8KB cap; `RENDER_UI_COMPONENT_DEF` OpenAI schema (`name: ui_components`); `_execute_tool` interception storing results in `self._pending_components`; conditional system prompt injection |
| Board component registry | 1 day | `UiComponentRegistry.tsx` mapping `component_type` → React component; `DataTable.tsx`, `DetailCard.tsx`, `ButtonGroup.tsx`, `ComparisonTable.tsx`; fallback to `<pre>` for unknown types |
| Action loop + hook | 1 day | `useSessionAction.ts` TanStack mutation wrapping `POST /v1/sessions/{id}/action`; amber inline action indicator in message stream |
| Skill registration | 1 day | `ui-components: inline` entry in `SKILL_REGISTRY`; metadata in `SKILL_METADATA`; SDK tool registry entry in `isli_agent/tools/__init__.py` |
| Documentation | 1 day | `Docs/13-immersive-chat-ui.md`; updates to `04-agents.md`, `06-skills.md`, `07-channels.md`, `README.md`, `10-roadmap.md` |

**Exit criteria (Phase 1):**
- Agent with `ui-components` in `skills` calls `ui_components` tool and Core receives reply with `components` array.
- Board renders table, card, button group, or comparison table inline in scrollback.
- Clicking a row or button emits an action message back to the agent with original `action_id` and payload.
- Action messages appear in Board with inline indicator (`↳ row_selected on order_123`).
- External channels (Telegram/WhatsApp) receive `text_fallback` with components stripped.

### Phase 2 (2026-05-30) — Editable Form + Display Components

| Task | Effort | Deliverable |
|------|--------|-------------|
| Form component | 1 day | `FormComponent.tsx` with `text`, `number`, `select`, `toggle`, `textarea` fields; local React state; `form_submitted` action with `{values: {...}}`; uses existing UI primitives |
| JsonViewer component | 0.5 day | `JsonViewer.tsx` — recursive collapsible JSON tree; syntax coloring; collapse/expand; max-height scroll |
| StatusTimeline component | 0.5 day | `StatusTimeline.tsx` — vertical step timeline; `completed`/`in_progress`/`pending`/`failed` status icons; mono styling |
| MetricGrid component | 0.5 day | `MetricGrid.tsx` — responsive CSS grid; metric mini-cards with label, value, trend arrow; 5 accent color maps |
| SDK instruction expansion | 0.5 day | Update `COMPONENT_TYPES` and `UI_RENDERING_INSTRUCTIONS` with schemas for all 4 new components |
| Board integration | 0.5 day | Update `types/index.ts` union; register components in `UiComponentRegistry.tsx`; verify `npm run typecheck` |
| Documentation | 0.5 day | Update `Docs/13-immersive-chat-ui.md` Phase 2 section; refresh `README.md`, `04-agents.md`, `06-skills.md`, `07-channels.md` |

**Exit criteria (Phase 2):**
- Agent renders a `form` with multiple field types; user fills and submits; `form_submitted` action flows back with correct `values`.
- Board renders `json_viewer`, `status_timeline`, and `metric_grid` inline without layout breakage.
- `npm run typecheck` passes with all 8 component types in the registry.
- Agent with `ui-components` skill sees the new component schemas in its system prompt.

---

## Post-Roadmap — Interactive Debugger Skill (2026-05-30) ✅

**Goal:** Give agents the ability to **set breakpoints**, **inspect variable states during execution**, and **step through code line-by-line** when diagnosing complex bugs. The existing `test-skill` only returns success/failure — the debugger provides rich execution traces.

**Architecture decision:** Batch trace model. Agents operate in a ReAct loop (discrete tool calls). A true session debugger would require dozens of sequential calls. Instead, the agent calls `interactive_debugger` once with `code + breakpoints + mode` and receives a complete line-by-line trace with variable snapshots.

| Task | Effort | Deliverable |
|------|--------|-------------|
| Trace execution engine | 1 day | `isli-skills/src/isli_skills/debugger.py` — `sys.settrace()` hook; `DebugTraceCollector`; `execute_with_trace()`; AST validation; `safe_repr`; `TraceLimitExceeded` abort; stdout/stdin redirect |
| `POST /debug` endpoint | 0.5 day | `isli-skills/src/isli_skills/main.py` — `DebugRequest` Pydantic model; `/debug` endpoint calling `execute_with_trace()`; `ValueError` → 400, generic → 500 |
| Unit tests | 0.5 day | `isli-skills/tests/test_debugger.py` — 10 tests covering trace mode, breakpoints, watch expressions, max_steps truncation, forbidden imports, exception capture, stdout capture, only-changes, payload injection, run function |
| Core skill registration | 0.2 day | `isli-core/src/isli_core/routers/skills.py` — add `interactive-debugger` to `SKILL_REGISTRY` + `SKILL_METADATA`; `docker-compose.yml` — `SKILL_INTERACTIVE_DEBUGGER_URL: http://skills:8100` |
| SDK tool wrapper | 0.5 day | `isli-agent-sdk/src/isli_agent/tools/debugger.py` — `interactive_debugger()` + `INTERACTIVE_DEBUGGER_DEF`; register in `SKILL_TOOL_REGISTRY`; `prompts.yaml` tool description |
| Board UI build fix | 0.3 day | `docker compose build --no-cache board` + `docker compose up -d --force-recreate board` — stale `dist/` from May 29 was serving old manual text-input UI instead of new dynamic `MultiSelect` |
| Docs update | 0.2 day | `Docs/06-skills.md` — add to registry table + dedicated debugger section; `Docs/04-agents.md` — add to sample `agent.yaml`; `Docs/10-roadmap.md` — this section |

**Exit criteria:**
- `GET /v1/skills` returns `interactive-debugger` with correct metadata.
- Agent with `interactive-debugger` in `skills` auto-registers the tool on startup.
- `interactive_debugger(code="...", mode="trace", breakpoints=[3], watch_expressions=["x+y"])` returns a trace with variable snapshots.
- `mode="run"` skips tracing for fast confirmation of fixes.
- Infinite loops are truncated at `max_steps` without hanging.
- Forbidden imports (`os`, `sys`, etc.) are rejected with 400.
- Board UI agent detail page shows `interactive-debugger` in the dynamic skills `MultiSelect`.

---

## Post-Roadmap — db-query Skill + ChromaDB Backup Hardening (2026-05-30) ✅

**Goal:** Implement the documented but missing `db-query` read-only SQL skill, and harden the ChromaDB backup/restore strategy from standalone scripts into an integrated scheduled worker with admin API endpoints.

| Task | Effort | Deliverable |
|------|--------|-------------|
| db-query skill engine | 0.5 day | `isli-skills/src/isli_skills/db_query.py` — `sqlparse` AST validation, forbidden-keyword deny-list, schema allow-list, `SET TRANSACTION READ ONLY`, LIMIT injection/clamping, asyncpg executor, error sanitization |
| db-query endpoint + config | 0.3 day | `POST /db-query` in `isli-skills/main.py`; `DbQueryRequest`/`DbQueryResult` Pydantic models; `database_url`, `db_query_allowed_schemas`, `db_query_max_rows`, `db_query_timeout_seconds` settings |
| db-query Core registration | 0.1 day | `SKILL_REGISTRY` + `SKILL_METADATA` entries in `isli-core/src/isli_core/routers/skills.py` |
| db-query SDK tool wrapper | 0.2 day | `isli-agent-sdk/src/isli_agent/tools/db_query.py` + `SKILL_TOOL_REGISTRY` registration + `prompts.yaml` description |
| db-query docker-compose wiring | 0.1 day | `DATABASE_URL` env var on `skills` service |
| ChromaDB backup worker | 0.5 day | `isli-core/src/isli_core/jobs/chromadb_backup_worker.py` — scheduled (6h default), subprocess call to `chromadb_backup.py`, SHA-256 verification, DB metadata storage, retention enforcement |
| ChromaDB backup model + migration | 0.2 day | `ChromaDbBackup` SQLAlchemy model; Alembic migration `20260530_2954c67aeea3` |
| ChromaDB admin router | 0.3 day | `isli-core/src/isli_core/routers/backups.py` — `POST /v1/admin/backups/chromadb/trigger`, `GET /v1/admin/backups/chromadb`, `POST /v1/admin/backups/chromadb/restore` (admin-only) |
| Core lifespan wiring | 0.1 day | Register `backups.router` and start `ChromaBackupWorker` via `startup/workers.py` |
| Standalone script hardening | 0.2 day | `scripts/chromadb_backup.py` — `--verify` flag, SHA-256 sidecar, integrity exit codes; `scripts/backup.sh` — SHA-256 sidecars for all components |
| Docs update | 0.2 day | `Docs/06-skills.md` — dedicated db-query section; `Docs/03-memory.md` — gap resolved; `Docs/runbooks/backup-restore.md` — ChromaDB restore procedure; `Docs/10-roadmap.md` — this section |

**Exit criteria:**
- `POST /v1/skills/db-query/query` with a valid SELECT returns structured `{"columns": [...], "rows": [...]}`.
- `POST /v1/skills/db-query/query` with `INSERT`, `UPDATE`, or `DELETE` returns HTTP 400 before touching the database.
- `POST /v1/skills/db-query/query` with a schema outside the allow-list returns HTTP 400.
- Agent with `db-query` in `skills` auto-registers the tool and can query the database.
- `ChromaBackupWorker` creates a verified `.tar.gz` archive every 6 hours and stores a row in `chromadb_backups`.
- Admin `POST /v1/admin/backups/chromadb/trigger` creates an on-demand backup and returns archive metadata.
- `POST /v1/admin/backups/chromadb/restore` returns a runbook URL and does not perform destructive operations automatically.
- Old backups older than retention days are deleted by the worker.

---

## Post-Roadmap — Secret Vault (`get-secret`) (2026-05-31) ✅

**Goal:** Provide a secure, encrypted-at-rest, per-agent secret vault so agents can access API keys, database credentials, and tokens at runtime without hardcoding them in source code or config.

**Security requirement:** Keeping secrets outside source code is a critical security requirement for building integrations safely and professionally.

| Task | Effort | Deliverable |
|------|--------|-------------|
| Core `Secret` model + migration | 0.5 day | `secrets` SQLAlchemy model (`agent_id`, `name`, `value_encrypted`, `description`, timestamps); Alembic migration `20260531_3a8f2e1b9c4d` with unique index on `(agent_id, name)` |
| Core secrets service layer | 0.3 day | `isli-core/src/isli_core/secrets_service.py` — `create_or_update_secret`, `get_secret_value`, `list_secrets`, `delete_secret` using existing `PIIEncryption` (AES-256-GCM) |
| Core secrets router (admin) | 0.3 day | `isli-core/src/isli_core/routers/secrets.py` — `POST /v1/secrets`, `GET /v1/secrets`, `DELETE /v1/secrets/{name}`; all admin-auth protected |
| Inline skill handler | 0.2 day | `POST /v1/skills/get-secret/get` in `skills.py` — decrypts value, audits read to `AuditLog`, commits transaction |
| Skill registry + metadata | 0.1 day | `"get-secret": "inline"` in `SKILL_REGISTRY`; category `"system"` in `SKILL_METADATA` |
| SDK tool wrapper | 0.2 day | `isli-agent-sdk/src/isli_agent/tools/secrets.py` — `get_secret()` + `GET_SECRET_DEF`; typed exceptions `SecretNotFoundError`, `SecretAccessError` |
| SDK registration | 0.1 day | `SKILL_TOOL_REGISTRY` + `SKILL_CATEGORY_MAP` entries in `isli_agent/tools/__init__.py` |
| Prompts YAML | 0.1 day | `get_secret` tool description in `prompts.yaml` (quoted to avoid YAML colon parsing issue) |
| Board UI Secrets tab | 0.5 day | `AgentSecretsPage.tsx` — list secrets, create secret form (masked value), delete with confirmation; route `/agents/:id/secrets`; nav button on `AgentDetailPage` |
| Core tests | 0.3 day | `test_api_secrets.py` — 8 tests covering create, list, update, get via skill proxy, not-found, delete, cross-agent isolation |
| SDK tests | 0.2 day | `test_tools_secrets.py` — 3 respx mock tests covering success, not-found, access-denied |
| Docker rebuild + restart | 0.3 day | Rebuild `core`, `board`, `agent-runner`; verify healthy stack |
| Docs update | 0.2 day | `Docs/06-skills.md` — registry table + dedicated Secret Vault section; `Docs/04-agents.md` — sample `agent.yaml` + Secret Vault subsection; `Docs/09-tech-stack.md` — mark gap as implemented; `Docs/10-roadmap.md` — this section |

**Exit criteria:**
- Admin creates a secret via Board UI or `POST /v1/secrets` for an agent.
- `GET /v1/secrets?agent_id=` returns names and metadata but **never** the decrypted value.
- Agent calls `get_secret("name")` → receives decrypted string → every call writes an `AuditLog` row.
- Cross-agent isolation enforced: Agent A cannot read Agent B's secrets (404).
- Board UI `/agents/:id/secrets` renders correctly with create/delete functionality.
- `docker compose up --build` starts all services healthy.

---

## Post-Roadmap — Streaming Modes (2026-05-31) ✅

**Goal:** Replace the silent batch-response UX with live, progressively revealed agent output across five visibility tiers — from completely silent (legacy) to full process trace with debug prompts.

**Architecture decision:** Bidirectional WebSocket streaming over the existing agent→Core WebSocket. The agent emits structured events during its ReAct loop; Core fans them out to Board WebSockets. External channels (Telegram/WhatsApp) continue to receive only the final text. Debug prompts are isolated to Redis + admin REST, never broadcast.

| Task | Effort | Deliverable |
|------|--------|-------------|
| Agent SDK streaming hooks | 1 day | `_emit_stream_event()`, `_stream_text()`, `_drain_outgoing_queue()` in `runner.py`; 10 event types instrumented across `_execute_session_message` and `_execute_task` |
| Core bidirectional WS | 0.5 day | `agent_ws()` parses `agent:stream_event`, appends to Redis draft, stores debug events in Redis trace list, fans out everything else as `session:stream_event` |
| Core REST endpoints | 0.5 day | `GET /v1/sessions/{id}/draft`, `GET /v1/sessions/{id}/debug-trace` (admin-only); `SessionReplyIn` accepts `metadata` for per-session override |
| Agent config validation | 0.3 day | Pydantic validators for `streaming_mode`, `stream_chunk_size`, `stream_delay_ms` in `agents.py`; `AgentOut.streaming_mode` computed field |
| DB migration | 0.2 day | `session_metadata` JSONB column on `sessions`; Alembic migration `20260531_d5e8f2a1b3c9` |
| Board UI streaming components | 1 day | `StreamingMessageBubble.tsx` (monospace + cursor), `ToolCallCard.tsx`/`ToolCallBar.tsx` (spinner→checkmark), `ProcessTracePane.tsx` (collapsible timeline), `useSessionStream.ts` hook |
| Board UI integration | 0.5 day | `ConversationsPage.tsx` streaming state + rendering; `BoardSocketContext.tsx` extended with `session:stream_event`; `App.tsx` handler |
| Agent detail streaming selector | 0.3 day | `AgentDetailPage.tsx` Model Strategy card: streaming mode `<Select>` with 5 options, dirty detection, save handler |
| Docker rebuild + restart | 0.5 day | Rebuild `core`, `agent-runner`, `board`; apply migration; verify healthy stack |
| Docs update | 0.2 day | Update `04-agents.md`, `01-architecture.md`, `05-kanban.md`, `07-channels.md`, `10-roadmap.md`, `README.md` |

**Exit criteria:**
- Agent with `streaming_mode: "text"` emits `token_delta` events; Board shows text appearing word-by-word.
- Agent with `streaming_mode: "tools"` shows `ToolCallBar` cards (`file_read`, `summarize_text`, etc.) with spinner→checkmark transitions.
- Agent with `streaming_mode: "trace"` renders a `ProcessTracePane` with `phase_start`, `turn_start`, `tool_call`, `cost_report` timeline.
- Agent with `streaming_mode: "debug"` stores prompt/response previews in Redis; admin fetches via REST; these events are **never** broadcast over WebSocket.
- Per-session override works: `POST /v1/sessions/{id}/message` with `metadata: {streaming_mode: "debug"}` overrides agent default for one session.
- Streaming failures (e.g., Redis unavailable) are swallowed by broad `try/except`; agent responses are never delayed or crashed.
- All containers healthy after `docker compose build --no-cache board` and `docker compose up -d --force-recreate`.

---

## Post-Roadmap — Prompt Management (2026-05-31) ✅

**Goal:** Allow administrators to edit the shared `prompts.yaml` file directly from the Board UI, with structured editors, raw YAML mode, optimistic locking, and automatic Keeper cache reload.

| Task | Effort | Deliverable |
|------|--------|-------------|
| Core prompts router | 0.5 day | `isli-core/src/isli_core/routers/prompts.py` — `GET/PUT /v1/prompts`; mtime-based optimistic locking; merge-on-write preserving unknown keys; best-effort Keeper reload via `POST /admin/reload-prompts`; audit log |
| Core cache clear | 0.1 day | `clear_prompts_cache()` in `isli-core/src/isli_core/prompts_loader.py` |
| Keeper cache clear | 0.1 day | `clear_prompts_cache()` in `isli-keeper/src/isli_keeper/prompts_loader.py` |
| Keeper reload endpoint | 0.1 day | `POST /admin/reload-prompts` in `isli-keeper/src/isli_keeper/main.py` |
| Board UI Prompts page | 1 day | `PromptsPage.tsx` — tabbed structured editor (Keeper/Agent/Core), per-tab raw YAML toggle with `js-yaml` validation, agent-restart banner, 409 conflict modal, Keeper reload warning toast |
| Board UI hooks | 0.2 day | `usePrompts.ts` — TanStack Query query + mutation |
| Board UI types | 0.1 day | `PromptsOut`, `PromptsUpdate` in `types/index.ts` |
| Board UI wiring | 0.2 day | Route `/settings/prompts` in `App.tsx`; "Prompts" card in `SettingsPage.tsx` |
| Board dependency | 0.1 day | `js-yaml` + `@types/js-yaml` in `package.json` |
| Docker rebuild + restart | 0.3 day | Rebuild `core`, `keeper`, `board`; verify healthy stack |
| Docs update | 0.2 day | Update `01-architecture.md`, `02-keeper.md`, `09-tech-stack.md`, `10-roadmap.md`, `README.md` |

**Exit criteria:**
- Board → Settings → Prompts loads the current `prompts.yaml` content in structured mode.
- Editing a Keeper prompt and clicking Save writes to disk, clears Core cache, and triggers Keeper reload.
- Two tabs editing simultaneously: first save succeeds, second gets `409 Conflict` with a refresh prompt.
- Unknown keys manually added to `prompts.yaml` are preserved across saves from the UI.
- Raw YAML mode allows bulk edits; invalid YAML blocks the toggle back to structured mode.
- Agent restart banner is visible and links to `/agents`.
- All containers healthy after `docker compose up --build`.

---

## Post-Roadmap — Model Routing (2026-05-31) ✅

**Goal:** Enable per-agent dynamic model selection so that trivial tasks run on cheap models and complex tasks run on premium models, cutting operational costs without sacrificing quality.

**Architecture decision:** Hybrid A+B routing. Core runs a fast zero-cost heuristic scorer in parallel with a Keeper LLM call. The scorer filters the candidate list by cost tier; the Keeper picks the best model from the filtered list. Both results are gathered concurrently so routing adds no wall-clock latency to the critical path.

| Task | Effort | Deliverable |
|------|--------|-------------|
| Core DB schema + migration | 0.5 day | `model_routing_enabled`, `secondary_models` on `Agent`; `complexity_score`, `complexity_tier`, `routed_model_provider`, `routed_model_id`, `routed_model_reason` on `Task` and `Session`; Alembic migration `20260531_b2283715c21f` |
| Core heuristic scorer | 0.5 day | `TaskComplexityScorer.score_task_input()` with keyword + length heuristics; `filter_models_by_tier()` with fail-open behavior |
| Core context injector wiring | 0.5 day | Parallel `asyncio.gather(context_future, routing_future)` in `ContextInjectorWorker` and `SessionContextInjectorWorker`; store routed fields on task/session; include in event payload |
| Session routing lock | 0.3 day | `already_routed` guard in `SessionContextInjectorWorker`: skip routing call entirely if `sess.routed_model_id` is already set |
| Keeper `/model/route` endpoint | 0.5 day | `ModelRouteRequest`/`ModelRouteResponse` Pydantic schemas; `_format_model_list()` prose formatter; JSON block extraction; validation against `secondary_models`; fail-open fallback |
| Keeper client method | 0.2 day | `KeeperClient.get_model_routing()` with `X-Internal-Auth` JWT and telemetry events |
| Agent SDK model resolution | 0.3 day | `_resolve_model(config, routed)` helper; `_model_with_fallback()` with explicit three-tier fallback (routed → default → halt); startup guard requiring `model_provider` and `model_id` |
| Agent SDK task/session wiring | 0.3 day | `_execute_task()` uses `task.context_summary` directly (no redundant HTTP call); `_execute_session_message()` extracts `routed_model` from payload |
| Core routers (agents, tasks, sessions) | 0.3 day | Extend `AgentCreate`, `AgentUpdate`, `AgentOut`, `TaskOut`, `SessionOut` with routed fields; `_safe_json` guard |
| Board UI Model Strategy card | 0.5 day | Toggle switch for `model_routing_enabled`; JSON textarea for `secondary_models`; updated `buildForm`, `modelDirty`, `saveModel`, `resetModel` |
| Prompts YAML | 0.2 day | `keeper:model_router` prompt template with `{task_description}`, `{complexity_score}`, `{complexity_tier}`, `{model_list}`, `{default_model}` |
| Docker rebuild & restart | 0.5 day | Rebuild `core`, `keeper`, `board`, `agent-runner`; apply migration; verify healthy stack |
| Docs update | 0.3 day | Update `04-agents.md`, `02-keeper.md`, `01-architecture.md`, `08-failure-modes.md`, `09-tech-stack.md`, `10-roadmap.md`, `README.md` |

**Exit criteria:**
- Agent with `model_routing_enabled=true` and 3 secondary models receives a task; Core scores it, calls Keeper, and stores a routed model on the task record.
- Agent runner uses the routed model for its LLM call.
- If the routed model fails, the runner falls back to the agent's default model and logs the fallback.
- If both fail, the runner halts with `RuntimeError` (no silent degradation).
- Session routes once on first message; all follow-up messages reuse the same `routed_model_id`.
- Board UI shows the Model Routing toggle and secondary models editor, and saves correctly.
- All containers healthy after `docker compose build --no-cache board` and `docker compose up -d --force-recreate`.

---

## Post-Roadmap — Browser Automation (Beta) (2026-06-01) ✅

**Goal:** Add Hermes-style browser automation so agents can navigate websites, fill forms, click buttons, and extract data using persistent Playwright sessions with accessibility-tree snapshots.

**Architecture decision:** State-in-Playwright, TTL-in-Redis. BrowserContext/Page objects cannot be serialized, so sessions live in an in-memory dict on the `isli-skills` service. Redis is used only for TTL heartbeats. This limits browser sessions to a single `isli-skills` instance — acceptable for the Beta.

| Task | Effort | Deliverable |
|------|--------|-------------|
| Browser module scaffold | 0.5 day | `isli-skills/src/isli_skills/browser/` package: `exceptions.py`, `accessibility_tree.py`, `session_manager.py`, `router.py` |
| Accessibility tree snapshot | 0.5 day | `get_snapshot()` — Playwright `page.accessibility.snapshot()` walker; assigns `@eN` ref IDs to interactive elements; `full=false` default (compact); node-boundary truncation at 8K chars |
| Session manager | 0.5 day | `BrowserSessionManager` — `launch_persistent_context()` per agent_id; Redis TTL heartbeat; background cleanup loop; `max_concurrent=5` guard with `503 + Retry-After: 30` |
| Router endpoints | 0.5 day | 10 `/browse/*` endpoints: `navigate`, `snapshot`, `click`, `type`, `press`, `scroll`, `back`, `console`, `vision`, `images`; all with `require_internal_auth` |
| Ref invalidation on navigate | 0.1 day | `session.clear_refs()` called **before** `page.goto()` and `page.go_back()` to prevent stale clicks on the new page |
| Console log delta | 0.1 day | `page.on("console", ...)` listener; `POST /browse/console` returns delta since last call with `next_cursor`; resets on navigate |
| Core skill registry | 0.2 day | 10 `web-browse-*` entries in `SKILL_REGISTRY`, `SKILL_METADATA`, and `HEAVY_SKILLS` |
| Agent SDK tools | 0.3 day | 10 browser tool functions + OpenAI `DEF` schemas in `isli_agent/tools/web.py`; registration in `SKILL_TOOL_REGISTRY` and `SKILL_CATEGORY_MAP` |
| Config + docker-compose | 0.2 day | `browser_headless`, `browser_session_ttl`, `browser_session_dir`, `browser_max_snapshot_chars`, `browser_max_concurrent_sessions` in `config.py`; `BROWSER_*` env vars on `skills` and `core`; `browser-sessions` volume; memory bump to `1G` |
| Tests | 0.3 day | `test_browser.py` with mocked Playwright; tests for navigate, snapshot, click, ref-not-found, pool-exhausted |
| Rebuild + restart | 0.2 day | `docker compose build core skills agent-runner`; verify healthy; `GET /v1/skills` returns all 10 browser skills |
| Docs update | 0.2 day | `Docs/06-skills.md` — registry table + Browser Automation section; `Docs/04-agents.md` — sample `agent.yaml` + Browser Automation subsection; `Docs/10-roadmap.md` — this section |

**Exit criteria:**
- Agent with `web-browse-navigate` and `web-browse-snapshot` in `skills` auto-registers tools on startup.
- Agent navigates to `example.com`, snapshots, sees `@e1`, `@e2` refs, clicks `@e1`, and receives success.
- Snapshot over 8K chars truncates at a node boundary (not mid-line) with `... N more nodes omitted ...`.
- Calling `browser_click` with a stale `@ref` returns `400` with "re-run snapshot" guidance.
- 6th concurrent browser session returns `503` with `Retry-After: 30`.
- Old `POST /browse` and `POST /fetch` endpoints in `isli-skills` still work (backward compatible).
- All containers healthy after rebuild.

---

## Post-Roadmap — Unified Notification System (2026-06-01) ✅

**Goal:** Deliver a complete notification infrastructure that alerts users to critical system events, agent activity, and task state changes across in-app inbox and Telegram, with preference-aware routing, quiet hours, digest batching, and SDK integration.

**Architecture decision:** Unified Redis listener. The existing `redis_listener` in `ws.py` dispatches events to both the Board WebSocket fan-out and the `NotificationEngine` via `asyncio.gather(..., return_exceptions=True)`. No second Redis consumer is needed.

| Task | Effort | Deliverable |
|------|--------|-------------|
| DB schema + migration | 0.5 day | `Notification` model (id, user_id, event_type, category, title, body, payload, read_at, dismissed_at, created_at, agent_id, task_id, session_id, channels, dedup_key); `NotificationPreference` model (user_id PK, global_enabled, quiet_hours_enabled, quiet_hours_start/end, timezone, quiet_hours_exceptions, categories); Alembic migration `20260601_006_notifications.py` |
| Core NotificationEngine | 1 day | `notification_engine.py` — `EVENT_MAP` mapping events to categories/templates/recipients/channels; `on_event()` → `_resolve_recipients()` → `_notify_user()` pipeline; preference resolution with Redis cache (1h TTL); quiet hours logic with `zoneinfo.ZoneInfo`; low-priority routing to `accumulate_digest()` |
| In-app delivery handler | 0.5 day | `delivery.py` — `deliver_in_app()` inserts `Notification` row, emits `notification:new` WS event, warms Redis unread cache with anti-drift (`EXISTS` check before `INCR`) |
| External delivery handler | 0.5 day | `delivery_external.py` — `deliver_external()` with presence suppression, Markdown formatting (`🔔 *title*`), posts to `isli-channels/send` with `parse_mode="Markdown"` |
| Digest worker | 0.5 day | `digest.py` — `DigestWorker` with `LRANGE` + `LTRIM` idempotency; `_collapse_items()` summary lines; `accumulate_digest()` pushes to `notif:batch:{user_id}:low` with TTL |
| REST endpoints | 0.5 day | `routers/notifications.py` — `GET /v1/notifications`, `GET /v1/notifications/unread-count`, `POST /v1/notifications/{id}/read`, `POST /v1/notifications/read-all`, `DELETE /v1/notifications/{id}`, `GET /v1/notifications/preferences`, `PATCH /v1/notifications/preferences` (with `ZoneInfo` validation), `POST /v1/notifications/send` (agent-facing with rate limiting) |
| WS integration | 0.2 day | Modify `ws.py` `redis_listener()` to dispatch to `NotificationEngine.on_event()` alongside existing board broadcast |
| Lifespan wiring | 0.2 day | Register `deliver_in_app` and `deliver_external` outbox handlers in `startup/notifications.py`; add `DigestWorker` to `startup/workers.py` `_WORKER_SPECS` |
| System:alert emitters | 0.3 day | Emit `system:alert` from 5 critical locations: `CheckpointRecoveryWorker` E-Stop, `BudgetAlerter` threshold, `ContextInjectorWorker` max retries, `SessionContextInjectorWorker` max retries, `ProcessManager` crash paths |
| Telegram adapter update | 0.2 day | `send_message()` accepts `parse_mode` kwarg and passes it to `bot.send_message()` |
| Board UI types + hooks | 0.3 day | `NotificationItem`, `NotificationListResponse`, `NotificationPreferences` in `types/index.ts`; `useNotifications`, `useUnreadCount`, `useMarkRead`, `useMarkAllRead`, `useDismissNotification` in `hooks/useNotifications.ts` |
| Board UI components | 1 day | `NotificationBell.tsx` (bell + badge), `NotificationDrawer.tsx` (slide-out inbox with all/unread/read filters + Inbox/Digest tabs), `NotificationItem.tsx` (category-colored icons, hover actions), `NotificationPreferences.tsx` (global toggle, quiet hours, timezone, per-category) |
| Board UI wiring | 0.3 day | `Header.tsx` adds `<NotificationBell />`; `App.tsx` adds `/settings/notifications` route + WS consumers for `notification:new/notification:read/notification:read_all`; `BoardSocketContext.tsx` extends `BoardMessage` union; `SettingsPage.tsx` enables Notifications card |
| Board UI digest page | 0.3 day | `DigestPage.tsx` standalone `/digests` route; sidebar "Digests" nav item; `useDigestNotifications` hook filtering by `event_type=system:digest` |
| Agent SDK tool | 0.3 day | `isli-agent-sdk/src/isli_agent/tools/notifications.py` — `notify_user()` with `POST /v1/notifications/send`; `NOTIFY_USER_DEF` with priority enum; typed `NotificationRateLimitError` / `NotificationDeliveryError`; register in `SKILL_TOOL_REGISTRY` and `SKILL_CATEGORY_MAP`; `AgentRunner.add_notification_tools()` convenience method |
| Docker rebuild + restart | 0.3 day | `docker compose build --no-cache board agent-runner`; `docker compose up -d --force-recreate core board channels` |
| Docs update | 0.3 day | Update `01-architecture.md`, `04-agents.md`, `07-channels.md`, `08-failure-modes.md`, `10-roadmap.md`, `README.md` |

**Exit criteria:**
- `agent:crash` event creates a critical notification visible in Board UI inbox with red icon.
- User opens `/settings/notifications`, enables quiet hours, saves; subsequent non-critical notifications during quiet hours are suppressed.
- Agent calls `notify_user(user_id, title, message, priority="high")` via SDK; notification appears in Board UI with 1s latency.
- Agent calls `notify_user` 21 times in one hour to same user; 21st call raises `NotificationRateLimitError` (429).
- `DigestWorker` collapses 5 low-priority events into a single digest notification.
- `GET /v1/notifications/unread-count` returns correct count even if Redis cache is flushed.
- All containers healthy after rebuild.

---

## Post-Roadmap — TTS Audio Delivery to Channels & Board (2026-06-01) ✅

**Goal:** Enable agents to send TTS-generated audio back to users through Telegram, WhatsApp, and the Board web UI session conversation. This includes both explicit agent-initiated voice messages (Phase 1) and a session-level "Voice Mode" toggle that auto-synthesizes every agent reply (Phase 2).

**Architecture decision:** Audio flows through the workspace service for persistence and audit. Core decodes base64 from `isli-audio`, uploads raw WAV bytes to `isli-workspace` under `_attachments/audio/{session_id}/{uuid}.wav`, appends an `audio_url` to the message dict, and forwards `audio_b64` to channel gateways. Board UI renders an inline `<audio controls>` player. Telegram receives WAV → Opus/OGG via ffmpeg. WhatsApp receives base64 → temp file → Baileys `ptt: true`.

| Task | Effort | Deliverable |
|------|--------|-------------|
| Core audio router | 0.3 day | `isli-core/src/isli_core/routers/audio.py` — `GET /v1/audio/{session_id}/{filename}`; session auth; proxies workspace download as `StreamingResponse(media_type="audio/wav")` |
| Core session reply TTS integration | 0.5 day | `reply_to_session` in `sessions.py` — auto-calls TTS when `voice_mode_enabled` in session metadata; uploads audio to workspace; appends `audio_url`; forwards `audio_b64` to channels; try/except with warning log on failure |
| Core send-message skill handler | 0.3 day | `skills.py` inline `send-message` handler validates `audio_b64` length ≤ 6.7M; uploads to workspace; appends `audio_url`; forwards to channels |
| Core workspace upload helper | 0.2 day | `upload_bytes_to_workspace()` in `workspaces.py` — reusable helper for raw byte uploads |
| Core audio cleanup worker | 0.2 day | `isli-core/src/isli_core/jobs/audio_cleanup.py` — `AudioCleanupWorker` runs every 24h; lists `_attachments/audio/*`; deletes files older than 7 days |
| Core lifespan wiring | 0.1 day | Import `audio` router in `main.py`; add `AudioCleanupWorker` to `startup/workers.py` `_WORKER_SPECS` |
| Core schemas update | 0.1 day | `session:message` WS event schema adds `audio_url` property; `SessionReplyIn` adds `audio_b64`, `audio_voice`, `voice_mode_enabled` |
| Core models update | 0.1 day | `ChannelMessage` adds `attachments: Mapped[list[dict[str, Any]]]` JSON column |
| Channels Dockerfile | 0.1 day | `apt-get install -y curl ffmpeg` |
| Channels attachment converter | 0.2 day | `convert_wav_to_opus_ogg(wav_bytes)` in `attachments.py` — ffmpeg subprocess with libopus, 24k bitrate |
| Telegram adapter voice delivery | 0.3 day | `send_message`: text sent first via `bot.send_message()`, then voice via `bot.send_voice()` if `audio_b64` present; caption limited to 1024 chars |
| WhatsApp adapter voice delivery | 0.2 day | `send_message`: text chunks sent first, then audio forwarded to sidecar as `{"type": "audio", audio_b64, caption}` |
| WhatsApp sidecar audio handler | 0.2 day | `/send` handler extended: if `type === "audio"`, decodes `audio_b64` to temp file, calls `sock.sendMessage(jid, {audio: {url: tmpPath}, ptt: true, caption})`, cleans up temp file in `finally` |
| Board UI audio playback | 0.3 day | `Message` interface adds `audio_url?: string`; `SessionsPage.tsx` and `ConversationsPage.tsx` render `<audio controls>` below assistant bubbles |
| Board UI Voice Mode toggle | 0.3 day | `ChatInput.tsx` adds Voice Mode toggle button (`Volume2`/`VolumeX`) next to auto-send; passes `voiceModeEnabled` to `onSend` callback; `useSessions.ts` and `useChats.ts` include `voice_mode_enabled` in POST payload |
| Agent SDK send_voice_message | 0.3 day | `isli-agent-sdk/src/isli_agent/tools/audio.py` — `send_voice_message()` convenience wrapper; `SEND_VOICE_MESSAGE_DEF`; registered in `SKILL_TOOL_REGISTRY` and `SKILL_CATEGORY_MAP` |
| Agent SDK send_message schema | 0.1 day | `send_message` adds optional `audio_b64` param; `SEND_MESSAGE_DEF` updated |
| Docker rebuild + restart | 0.5 day | Rebuild `channels`, `whatsapp-sidecar`, `board`, `agent-runner`; restart `core`; verify healthy |
| Docs update | 0.2 day | Update `06-skills.md`, `07-channels.md`, `10-roadmap.md` |

**Exit criteria:**
- Agent calls `send_voice_message(channel="telegram", ...)` → user receives text message followed by a Telegram voice message.
- User enables Voice Mode in Board UI → every subsequent agent reply includes an inline audio player alongside text.
- Voice Mode works even when TTS is temporarily unavailable — text is always delivered; audio is best-effort.
- WhatsApp voice replies use the original `remote_jid` (including `.lid` suffix) and arrive as push-to-talk messages.
- Audio files older than 7 days are automatically purged from the workspace.
- `docker compose up --build` starts all services healthy.

---

## Post-Roadmap — Recurring Tasks & Full Scheduler (2026-06-02) ✅

**Goal:** Implement a robust recurring task system allowing users to schedule agent workflows using cron expressions, with transactional cloning and execution history.

| Task | Effort | Deliverable |
|------|--------|-------------|
| Backend cron support | 1 day | `cron_expression`, `last_triggered_at` columns on `Task` model; `croniter` dependency; Pydantic validation for 5-min minimum interval |
| Atomic SchedulerWorker | 1 day | `SchedulerWorker.run_once` refactored for transactional cloning; parent-child linking via `parent_task_id`; idempotency guards |
| Frontend Cron Builder | 1 day | `CronBuilder.tsx` component with common presets (Daily, Weekly, etc.) and real-time regex validation |
| Board UI integration | 1 day | "Upcoming" date filter in `KanbanHeader.tsx`; "Repeat" icon and cron summary in `TaskCard.tsx`; Execution History list in `TaskDetailModal.tsx` |
| Docker rebuild + restart | 0.5 day | Rebuild `core`, `board`; apply migration; verify healthy stack |

**Exit criteria:**
- User creates a recurring task (e.g., `0 9 * * 1` for Monday at 9 AM).
- Worker clones the task at the scheduled time, parent reschedules for next week.
- Child task (clone) is linked to parent; parent shows child in "Execution History".
- Board UI shows "Upcoming" filter working correctly for scheduled tasks.
- All containers healthy after rebuild.

---

## Post-Roadmap — Context Safety (Hard Output Caps) (2026-06-07) ✅

**Goal:** Prevent silent context window exhaustion by capping the size of data returned by high-volume skills (file-read, db-query, git-log).

| Task | Effort | Deliverable |
|------|--------|-------------|
| file-read character cap | 0.5 day | 16k default, 64k max char cap in `isli-workspace`; server-side clamping; line-range slicing logic; enriched truncation notice with pagination hints |
| db-query row/cell cap | 0.5 day | 50 row default; 500 char cell cap in `isli-skills`; max_rows+1 fetch optimization for `has_more` flag; original byte count hints in truncated cells |
| git-log character cap | 0.3 day | 12k char cap in `isli-workspace` to protect against large diffs; explicit `truncated` status |
| Structured observability | 0.2 day | Always return explicit `truncated: true/false` boolean across all three skills for system-wide tracking |
| Agent SDK integration | 0.3 day | Update `file_read`, `db_query`, and `git_log` SDK tools to expose new parameters and defaults |
| Documentation update | 0.2 day | Update `Docs/06-skills.md`, `Docs/10-roadmap.md`, and SDK README |

**Exit criteria:**
- Agent reading 1MB file receives 16KB + pagination notice + `truncated: true`.
- Agent querying large DB table receives 50 rows + `has_more: true`.
- Agent running `git log --patch` on large diff is capped by 12KB char limit.
- All containers healthy after rebuild.
