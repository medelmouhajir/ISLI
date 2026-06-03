# Project Memory - ISLI

## Task History

### 2026-05-21: Local Web Search Implementation (SearXNG)
- **Problem:** `web-search` skill was documented but not implemented.
- **Solution:** Integrated SearXNG as a local, self-hosted web search provider.
- **Key Changes:**
  - Added `searxng` service to `docker-compose.yml` (version: `2024.5.15-089760f38`).
  - Created `infra/searxng/settings.yml` with JSON API enabled.
  - Implemented `/search` endpoint in `isli-skills` microservice.
  - Registered `web-search` skill in `isli-core` registry and metadata.
  - Updated `GEMINI.md` to include `web-search` in the project overview.
- **Technical Note:** SearXNG requires `search.formats: [json]` in `settings.yml` for API compatibility.

### 2026-06-01: Web Push Notification Implementation
- **Problem:** Users only received notifications when the Board UI was active via WebSockets. No cross-platform push support existed.
- **Solution:** Implemented Web Push API using the existing PWA foundation, allowing notifications even when the browser is closed.
- **Key Changes:**
  - **Backend:** Added `WebPushSubscription` model (multi-device support) and `delivery_webpush.py` delivery module.
  - **VAPID:** Generated VAPID keys (SECP256R1) and implemented public key fetching and subscription endpoints.
  - **Outbox:** Integrated `notification:web_push` as a first-class channel in the Outbox worker.
  - **Frontend:** Switched `isli-board` to `injectManifest` strategy and created `sw.ts` with push/notificationclick listeners.
  - **UX:** Added a toggle in Notification Preferences with iOS "Add to Home Screen" safeguards and instructions.
  - **PWA:** Fixed `vite.config.ts` manifest properties (`display: standalone`, `start_url`) to ensure Android/iOS installability.
- **Technical Note:** Requires `VAPID_PRIVATE_KEY` and `VAPID_PUBLIC_KEY` in `.env`. Prunes stale subscriptions automatically on 410/404 errors.

### 2026-05-28: WhatsApp Critical Security & Reliability Fixes
- **Problem:** 10 critical issues found in WhatsApp channel audit: unauthenticated webhooks, broken idempotency, no send retry, silent message loss, fire-and-forget sidecar endpoints, useless health checks, unauthenticated sidecar API, no message chunking, dropped attachments, and no graceful shutdown.
- **Solution:** Applied fixes across sidecar, adapter, idempotency, docker-compose, and tests.
- **Key Changes:**
  - **Auth:** `X-Sidecar-Secret` on webhooks + `Authorization: Bearer` on REST calls.
  - **Idempotency:** Fixed `extract_id` to read `payload.key.id`.
  - **Retry:** 4 attempts with capped exponential backoff in `send_message`.
  - **Chunking:** `MessageChunker.chunk(text, "whatsapp")` splits >1600 char responses.
  - **Attachments:** Extracts image/video/audio/document metadata and forwards to Core.
  - **Health checks:** Real `GET /health` on sidecar; adapter calls it with 3s timeout.
  - **Sidecar hardening:** Awaited `startSession`, awaited `forwardEvent`, try/catch auto-start loop, skip hidden dirs, body size limit, graceful shutdown on SIGTERM/SIGINT.
  - **Redis TTL:** Session keys now expire after 30 days.
- **Technical Note:** Secrets must be set in `.env`: `SIDECAR_WEBHOOK_SECRET` and `SIDECAR_API_TOKEN`.

### 2026-05-24: WhatsApp Node.js Sidecar Migration
- **Problem:** Python `pyaileys` library failed protocol handshake (Protobuf DecodeError) and caused "stuck QR spinner" on phones.
- **Solution:** Migrated connection logic to a Node.js sidecar using `@whiskeysockets/baileys`.
- **Key Changes:**
  - Created `isli-whatsapp-sidecar` (Node.js/Express).
  - Implemented proxy-webhook architecture in `isli-channels`.
  - Added session isolation (per-agent folders) and webhook retry logic.
  - Updated `docker-compose.yml` and project documentation.
- **Technical Note:** Baileys requires a standard browser string (e.g., Ubuntu/Chrome) to avoid being flagged by WhatsApp servers.

### 2026-05-24: Dynamic Agent Skill Reloading
- **Problem:** Agents required a manual restart to recognize new skills assigned via the Board UI.
- **Solution:** Implemented real-time config syncing over WebSockets.
- **Key Changes:**
  - Updated `isli-core` WebSocket router to forward `agent:config_updated` events.
  - Enhanced `isli-agent-sdk` with `_sync_config()` logic to dynamically reload tools and re-assemble system prompts.
  - Fixed `prompts.yaml` packaging in Docker image to ensure agents can load system prompt templates reliably.
- **Technical Note:** The agent runner now clears its tool registry and re-fetches configuration from Core API whenever a config update event is received, ensuring zero-downtime updates.
