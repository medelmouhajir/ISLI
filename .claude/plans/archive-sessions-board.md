# Plan: Archive Sessions Page in Board UI

## Goal

Add a dedicated **Archive** page in the Board Web UI for **Sessions** only, reachable at `/archive/sessions`. It lists sessions that are either:
- `status = "closed"` (closed from the Sessions page), or
- `deleted_at is not None` (soft-deleted by lifecycle, `/new`, or expiry).

From the archive page an operator can **view** (read-only history), **restore** (re-open: `status = "ready"`, `deleted_at = None`), or **permanently delete** a session.

---

## Scope Decisions (from user)

| Question | Decision |
|---|---|
| Entities | Sessions only (first iteration) |
| Page structure | Separate route: `/archive/sessions` |
| Actions per item | View, Restore, Delete |
| Archive contents | Both `closed` and soft-deleted sessions |
| Restore behavior | Re-open session (`status = "ready"`, `deleted_at = None`) |

---

## Backend Changes

### File: `isli-core/src/isli_core/routers/sessions.py`

1. **Archive listing** — extend `GET /v1/sessions` with an `archived` query flag.
   - When `archived=True`, return sessions where `status == "closed"` **or** `deleted_at.is_not(None)`.
   - Ignore the `include_closed` filter in archive mode.
   - Keep existing `agent_id`, `channel`, `user_id`, `limit` filters.

2. **Restore endpoint** — add `POST /v1/sessions/{session_id}/restore`.
   - Find session by `id` only (do **not** filter out closed/deleted rows).
   - Verify the owning agent still exists and is not soft-deleted; otherwise return `400`.
   - Set `status = "ready"`, `deleted_at = None`.
   - Commit and emit `session:updated` event.

3. **Permanent delete** — modify `DELETE /v1/sessions/{session_id}`.
   - Remove the `deleted_at.is_(None)` filter so it can permanently delete already-soft-deleted sessions.
   - Keep the existing hard-delete behavior (`ChannelMessage` cascade + `session.delete()`).

4. **View history for archived sessions** — modify `GET /v1/sessions/{session_id}/history`.
   - Remove the `deleted_at.is_(None)` filter so the archive page can display read-only history for soft-deleted sessions.
   - Keep the `id` lookup only.

---

## Frontend Changes

### File: `isli-board/src/types/index.ts`

- Add `deleted_at?: string | null` to the `Session` interface so archive rows can show how/when a session was removed.

### File: `isli-board/src/hooks/useSessions.ts`

Add three new hooks:
- `useArchivedSessions(agentId?: string)` — `GET /v1/sessions?archived=true` (with optional `agent_id`).
- `useRestoreSession()` — `POST /v1/sessions/{id}/restore`, invalidates `['sessions']` and `['archived-sessions']`.
- `useArchivedSessionHistory(sessionId: string | null)` — `GET /v1/sessions/{id}/history`, used for the read-only view modal.

### New File: `isli-board/src/components/ArchivedSessionsPage.tsx`

A list page in the same monospaced “Neural Command Center” aesthetic as `SessionsPage`.

Layout:
- Header: `ARCHIVE_LOG` + agent filter `Select` + live count badge.
- Table/card list of archived sessions with columns:
  - Agent name + avatar
  - User / Channel
  - State badge (`closed` vs `deleted`)
  - Deleted/closed timestamp
  - Last activity
  - Message count
  - Actions: View (eye), Restore (rotate-ccw), Delete (trash)
- Empty state: `NO_ARCHIVED_SESSIONS_FOUND`.

Interactions:
- **View**: opens a read-only Modal/slideover showing the session history (reusing the message rendering style from `SessionsPage` or `ConversationsPage`). No input box.
- **Restore**: calls `useRestoreSession`, then shows a toast/inline success and refetches.
- **Delete**: uses the existing `ConfirmationModal` with a strong warning (`Permanently delete session and all messages?`), then calls `useDeleteSession`.

### File: `isli-board/src/App.tsx`

Add route inside `<Routes>`:
```tsx
<Route path="/archive/sessions" element={<ArchivedSessionsPage />} />
```

### File: `isli-board/src/components/Sidebar.tsx`

Add a navigation entry under Sessions:
- Label: `Archive`
- Icon: `Archive` (lucide-react)
- Path: `/archive/sessions`

---

## Tests

### File: `isli-core/tests/test_api_sessions.py`

Add a new test class `TestSessionArchiveAPI`:
1. `test_list_archived_sessions_includes_closed_and_deleted` — create one active, one closed, one soft-deleted session; assert only the archived two are returned.
2. `test_restore_closed_session` — close a session, call restore, assert `status == "ready"` and `deleted_at is None`.
3. `test_restore_soft_deleted_session` — soft-delete a session, call restore, assert `status == "ready"` and `deleted_at is None`.
4. `test_restore_fails_when_agent_deleted` — soft-delete session and its agent; restore returns `400`.
5. `test_delete_permanently_removes_soft_deleted_session` — soft-delete a session, call `DELETE`, assert `404` on subsequent fetch.
6. `test_history_returns_deleted_session_messages` — create a soft-deleted session with messages, call history endpoint, assert messages present.

---

## Files to Modify / Create

| File | Action |
|---|---|
| `isli-core/src/isli_core/routers/sessions.py` | Modify list, delete, history, add restore endpoint |
| `isli-core/tests/test_api_sessions.py` | Add `TestSessionArchiveAPI` |
| `isli-board/src/types/index.ts` | Add `deleted_at` to `Session` |
| `isli-board/src/hooks/useSessions.ts` | Add archive + restore + history hooks |
| `isli-board/src/components/ArchivedSessionsPage.tsx` | Create page component |
| `isli-board/src/App.tsx` | Add `/archive/sessions` route |
| `isli-board/src/components/Sidebar.tsx` | Add Archive nav item |

---

## Estimated Effort

Small/medium — roughly:
- Backend: ~45 minutes (endpoint changes + tests)
- Frontend: ~90 minutes (new page + hooks + routing + nav)

Total ~2–2.5 hours.

---

## Future Extensions (out of scope for this plan)

- `/archive/tasks`, `/archive/agents`, `/archive/shared-workspaces` tabs/pages once the pattern is validated.
- Batch restore / batch delete from archive.
- Pagination for large archives.
- Retention-based auto-purge UI.
