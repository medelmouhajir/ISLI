# Plan: Configurable Channel-Message Notifications in Board PWA

## Current state
- The notification system already supports per-category delivery channels on the backend:
  - `isli-core/src/isli_core/notification/notification_engine.py` defines `DEFAULT_CATEGORIES` with `channels` arrays, e.g. `session_message: ["in_app", "web_push"]`.
  - The engine stages separate Outbox entries for `notification:in_app`, `notification:external`, and `notification:web_push` based on the user's category preferences.
  - `deliver_external.py` can forward notifications to Telegram/WhatsApp via `isli-channels`.
  - `deliver_webpush.py` sends browser push notifications to registered PWA endpoints.
- The Board UI settings page (`NotificationPreferences.tsx`) only exposes:
  - Web push master toggle (subscribe/unsubscribe).
  - Global notifications toggle.
  - Quiet hours.
  - A per-category **enabled** toggle and priority display.
- It does **not** expose the `channels` array, so users cannot choose, for example, that new channel messages should notify via web push but not in-app, or via Telegram but not web push.
- All `session:message` events (web chat, Telegram, WhatsApp, email) are currently mapped to the single `session_message` category, so external channel messages cannot be configured separately from web chat.

## Goal
Make notifications for new channel messages configurable from the Board PWA notifications settings page, with clear control over which delivery surfaces (in-app badge, web push, Telegram, WhatsApp, email) are used.

## Design decisions
- Add a dedicated `channel_message` category for **inbound messages from external channels** (Telegram, WhatsApp, email), separate from `session_message` (web chat / Council).
- Keep `session_message` for web chat and Council activity, so Board users who already see the UI can turn its notifications off independently.
- Expose per-category channel toggles in `NotificationPreferences.tsx`: a compact row of checkboxes/toggles for each available channel (`in_app`, `web_push`, `telegram`, `whatsapp`, `email`).
- Use the existing preference patch endpoint (`PATCH /v1/notifications/preferences`) — the backend already persists `categories` as JSON, so no schema migration is required.
- Ensure channel toggles respect the global switch, quiet hours, and per-category enabled state.
- Enhance the service worker deep-link so a web-push notification for a channel message opens the correct session/conversation.

## Implementation steps

### 1. Backend — split external channel messages into their own category
File: `isli-core/src/isli_core/notification/notification_engine.py`
- Add a new entry to `DEFAULT_CATEGORIES`:
  ```python
  "channel_message": {
      "enabled": True,
      "channels": ["in_app", "web_push"],
      "priority": "high",
      "in_app_style": "badge_only",
  }
  ```
- Update `_event_category_key` to route `session:message` events based on `payload.get("channel")`:
  - If `channel` is `web` or `None` → `session_message`.
  - If `channel` is `telegram`, `whatsapp`, or `email` → `channel_message`.
- Update the `EVENT_MAP["session:message"]` mapping so title/body rendering includes the source channel name, e.g. "New message on Telegram".

### 2. Backend — validate and document preference channels
File: `isli-core/src/isli_core/routers/notifications.py`
- In `UpdatePreferencesIn`, optionally add a field validator for `categories.*.channels` to reject unknown channel names.
- Ensure the `NotificationPreferencesOut` response returns `categories` exactly as stored, so the UI can render the channel list.
- No migration needed: existing rows without `channel_message` will fall back to `DEFAULT_CATEGORIES` on first read.

### 3. Frontend — expose per-category channel toggles
File: `isli-board/src/components/NotificationPreferences.tsx`
- Replace the simple category list with an expandable card per category.
- Each card shows:
  - Category name + description.
  - Master enabled toggle.
  - Priority badge.
  - A "Delivery channels" row with toggles/checkboxes for every channel present in the category's `channels` array.
- When a channel toggle changes, update `localPrefs.categories[key].channels` and persist via the existing mutation.
- Show a subtle hint when web push is selected but the user is not subscribed (reuse `useWebPush` state).

### 4. Frontend — type-safe category channel schema
File: `isli-board/src/types/index.ts`
- Add a typed shape for notification category preferences:
  ```ts
  export interface NotificationCategoryPreference {
    enabled: boolean
    channels: string[]
    priority: string
    in_app_style?: string
    digest_window_minutes?: number
  }
  ```
- Update `NotificationPreferences.categories` from `Record<string, unknown>` to `Record<string, NotificationCategoryPreference>`.

### 5. Frontend — service worker deep-link for channel messages
File: `isli-board/src/sw.ts`
- Update the `notificationclick` handler to use `notificationData.session_id` when present:
  - Priority: `task_id` → `/kanban?task=...`, `session_id` → `/chats?session=...` (or `/sessions?session=...`), `agent_id` → `/?agent=...`, otherwise `/`.
- Verify that `data.session_id` is already included in web-push payloads from `delivery_webpush.py`.

### 6. Frontend — notification preferences hook refinements
File: `isli-board/src/hooks/useNotificationPreferences.ts`
- No major change required, but confirm the patch invalidates the preferences query and the UI re-renders from server-state after save.
- Consider adding optimistic update if toggles feel sluggish.

### 7. Testing / verification
- Unit/backend:
  - Add a test in `isli-core/tests/` that emits `session:message` with `channel=telegram` and asserts the staged Outbox entries use `channel_message` category.
  - Add a test that patching `categories.channel_message.channels` to `["in_app"]` suppresses web-push staging.
- Frontend:
  - Run `npm run typecheck` and `npm run lint` in `isli-board`.
  - Manual PWA verification: subscribe to web push, send a Telegram message, confirm the notification appears and click opens the conversation.

## Files touched
- `isli-core/src/isli_core/notification/notification_engine.py`
- `isli-core/src/isli_core/routers/notifications.py`
- `isli-board/src/components/NotificationPreferences.tsx`
- `isli-board/src/types/index.ts`
- `isli-board/src/sw.ts`
- `isli-board/src/hooks/useNotificationPreferences.ts` (minor)
- `isli-core/tests/notification/test_notification_engine.py` (new or updated)

## Risks / mitigations
- **Existing users with stored `session_message` preferences**: when we introduce `channel_message`, existing stored preferences won't contain it. Mitigation: backend falls back to `DEFAULT_CATEGORIES`, so new users and existing users both get the default `channel_message` entry.
- **Web push payload size**: adding channel name to title does not materially increase payload.
- **Channel toggle UI clutter**: mitigate by keeping toggles compact (icon-only with tooltips) and only showing channels that are actually available in the category defaults.
- **PWA service worker stale after deploy**: the `PWAReloadPrompt` component already prompts users to reload; after this change, users must reload once for the updated `sw.ts` to take effect.
- **Board already open**: presence-based suppression in `deliver_external.py` already skips non-critical external pushes when the user is active on the Board; this stays unchanged and respects the new category.

## Scope excluded (future work)
- Per-agent or per-contact notification rules.
- Snooze or thread-level muting.
- Rich push actions beyond "Open Board".
- Digest bundling for channel messages.
