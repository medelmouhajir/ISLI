# Plan: Agent File Attachments in Channel Replies

## Goal
Allow agents to return files from their own workspace **and** shared workspaces as attachments in responses delivered to users over **web**, **Telegram**, and **WhatsApp**. The feature also extends the `ui-components` skill so structured outputs can include downloadable/viewable file cards with modal previews.

## High-level approach
- Agents **stage** attachments during a turn via a new SDK tool (`stage_reply_attachment`).
- The runner collects staged attachments and includes them in the final `reply_to_session` call, alongside any text/components/audio.
- Core generates **short-lived signed download URLs** (internal JWT scoped to a single file) and forwards lightweight metadata to the `isli-channels` service.
- Channels adapters fetch the bytes from the signed URL and send them via each platform's native media API:
  - Telegram: `send_document`, `send_photo`, `send_audio`, `send_video`.
  - WhatsApp sidecar: new `/send` payload types for `document`, `image`, `audio`, `video`.
  - Web UI: Board renders attachment pills/cards with view/download modals.
- Core persists attachment metadata in the session message record and promotes any blob tokens to workspace disk through the existing Outbox worker, exactly like audio/browser blobs.

## Why signed URLs instead of base64 passthrough
- Base64 inflates payload size and forces Core to hold large byte arrays in memory.
- Signed URLs let each channel service stream bytes directly from the workspace service.
- They are short-lived, single-file, and scoped, limiting blast radius if a URL leaks.

## Components touched
1. `isli-agent-sdk` — new tool + runner state.
2. `isli-core` — signed-URL endpoint, session reply schema, channel forwarding, outbox promotion, tests.
3. `isli-workspace` — tiny endpoint to expose file metadata (size, mime) for validation before download.
4. `isli-channels` — Telegram and WhatsApp adapters fetch + send media.
5. `isli-whatsapp-sidecar` — new media-sending branch in `/send`.
6. `isli-board` — message attachment rendering, view/download modals, updated UI component schemas.
7. `prompts.yaml` (repo root) — update tool description hints so agents know how/when to stage files.

---

## 1. SDK: `stage_reply_attachment` tool

### New file: `isli-agent-sdk/src/isli_agent/tools/attachments.py`
```python
async def stage_reply_attachment(
    agent_id: str,
    path: str,
    core_client: CoreClient,
    workspace_id: str | None = None,
    caption: str | None = None,
) -> dict[str, Any]:
    """Stage a file from agent workspace (or shared workspace) for the next reply."""
    # workspace_id present => shared-file-read metadata call to validate existence
    # otherwise validate agent workspace path via file-read or a new head/metadata skill
    return {"status": "staged", "path": path, "workspace_id": workspace_id, "caption": caption}
```
Tool definition:
- `path`: relative file path.
- `workspace_id`: optional; if omitted, file is taken from the agent's own workspace.
- `caption`: optional short text used as Telegram/WhatsApp caption.

### Runner changes (`isli-agent-sdk/src/isli_agent/runner.py`)
- Add `self._pending_attachments: dict[str, list[dict[str, Any]]] = {}` keyed by `session_id`.
- Register the new tool.
- In the ReAct loop, when `stage_reply_attachment` is called, append to `self._pending_attachments[session_id]`.
- In `reply_to_session`, pass `attachments=self._pending_attachments.pop(session_id, None)`.
- If the agent tries to stage the same path twice in one turn, deduplicate.

### Client changes (`isli-agent-sdk/src/isli_agent/client.py`)
```python
async def reply_to_session(
    self, session_id, text, ..., attachments: list[dict] | None = None
):
    payload = {"text": text, ...}
    if attachments:
        payload["attachments"] = attachments
    ...
```

---

## 2. Core: signed-URL generation and reply handling

### 2.1 New endpoint: `POST /v1/workspaces/{agent_id}/file-url`
In `isli-core/src/isli_core/routers/workspaces.py`:
- Accepts `path`, optional `workspace_id`, `scope` (`agent` or `shared`), `scope_id`, and `expires_minutes` (default 5, max 30).
- Validates the path and verifies access:
  - `agent` scope: caller must be that agent or admin.
  - `shared` scope: caller must be a member/owner of the workspace.
- Generates an internal JWT with scopes `["workspace:download"]` and a claim `file_path`, `scope`, `scope_id`, `agent_id`.
- Returns `{"download_url": "/v1/internal/files/download?token=...", "expires_at": "...", "filename": "...", "mime_type": "...", "size_bytes": ...}`.
- Core will need to ask Workspace for file metadata (size + mime) to return in this response. Workspace gets a new `/metadata` endpoint (see section 3).

### 2.2 New endpoint: `GET /v1/internal/files/download`
In `isli-core/src/isli_core/routers/internal.py`:
- Accepts `token` query param.
- Verifies internal JWT, scopes, and `file_path` claim.
- Streams the file from Workspace service using the same `download` proxy pattern already in `workspaces.py`.
- Sets correct `Content-Type` and `Content-Disposition`.
- This endpoint is intentionally reachable from the public internet (for Telegram/WhatsApp servers) but fully signed and time-boxed.

### 2.3 Session reply schema update
In `isli-core/src/isli_core/routers/sessions.py`:
```python
class AttachmentIn(BaseModel):
    path: str
    workspace_id: str | None = None
    caption: str | None = None

class SessionReplyIn(BaseModel):
    ...
    attachments: list[AttachmentIn] = []
```

### 2.4 Reply flow changes (`reply_to_session`)
For each attachment in `payload.attachments`:
1. Resolve scope/scope_id:
   - `scope = "shared"`, `scope_id = attachment.workspace_id` if provided.
   - Else `scope = "agent"`, `scope_id = sess.agent_id`.
2. Call the new signed-URL helper.
3. Build an attachment metadata dict:
   ```json
   {
     "filename": "report.pdf",
     "mime_type": "application/pdf",
     "size_bytes": 12345,
     "download_url": "/v1/internal/files/download?token=eyJ...",
     "expires_at": "...",
     "caption": "...",
     "scope": "agent",
     "scope_id": "...",
     "path": "report.pdf"
   }
   ```
4. Append to `msg["attachments"]`.
5. Persist the message via Outbox as usual (Outbox promotion only rewrites blob tokens; it leaves attachment metadata untouched).
6. When forwarding to external channels, include `attachments` in the `/send` payload.

### 2.5 Web response rewrite
The immediate API response for the Board UI rewrites signed download URLs to fully-qualified Core URLs:
```python
api_response_msg["attachments"] = [
    {**a, "download_url": f"{settings.core_api_url}{a['download_url']}"}
    for a in attachments
]
```

### 2.6 Channel forward payload
In `isli-core/src/isli_core/routers/sessions.py`, the `_send_to_channels` payload becomes:
```python
payload_channels = {
    "channel": sess.channel,
    "channel_user_id": sess.user_id,
    "text": channel_text,
    "agent_id": sess.agent_id,
    "attachments": [
        {
            "download_url": f"{settings.core_api_url}{a['download_url']}",
            "filename": a["filename"],
            "mime_type": a["mime_type"],
            "size_bytes": a["size_bytes"],
            "caption": a.get("caption"),
        }
        for a in attachments
    ],
}
if audio_ref:
    payload_channels["audio_ref"] = audio_ref
```

### 2.7 Size limits
Re-use `isli_channels.attachments.PLATFORM_FORMATS` from Core side:
- Validate each attachment against the target channel's max size and allowed media type before forwarding.
- If an attachment is too large or wrong type, log a warning and send the text reply without that attachment (never fail the whole reply).

### 2.8 Audit
Update `ChannelMessage` creation in `reply_to_session` to store attachment metadata in `raw_payload`.

---

## 3. Workspace: file metadata endpoint

### 3.1 New endpoint: `POST /metadata`
In `isli-workspace/src/isli_workspace/main.py`:
```python
class MetadataRequest(BaseWorkspaceRequest):
    path: str

@app.post("/metadata")
async def metadata(body: MetadataRequest, auth=Depends(require_internal_auth)):
    await check_access(...)
    file_path = resolve_path(...)
    if not file_path.exists():
        raise HTTPException(404)
    stat = file_path.stat()
    mime_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    return {
        "status": "ok",
        "path": body.path,
        "size_bytes": stat.st_size,
        "mime_type": mime_type,
        "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat(),
    }
```
Add `import mimetypes` at the top. No new dependencies required.

---

## 4. Channels service

### 4.1 Telegram adapter (`isli-channels/src/isli_channels/adapters/telegram.py`)
Update `send_message` signature to accept `attachments: list[dict] | None = None`.

For each attachment:
1. Validate via `validate_for_channel(mime_type, size_bytes, "telegram")`.
2. Fetch bytes from `download_url` using `httpx.AsyncClient` with a timeout (e.g. 30s).
3. Determine Telegram media type from `mime_type` using `isli_channels.attachments.mime_to_media_type`.
4. Use the appropriate `python-telegram-bot` method:
   - `image` → `bot.send_photo`
   - `video` → `bot.send_video`
   - `audio` → `bot.send_audio`
   - `document` (default) → `bot.send_document`
5. Send with the text as caption on the first attachment if the text is ≤ 1024 chars, otherwise send text first and attachments after.
6. Respect per-agent token via `_resolve_token`.

### 4.2 WhatsApp adapter (`isli-channels/src/isli_channels/adapters/whatsapp.py`)
Update `send_message` to accept `attachments`.

For each attachment:
1. Validate via `validate_for_channel(..., "whatsapp")`.
2. Fetch bytes from `download_url`.
3. Determine media category (`image`, `video`, `audio`, `document`).
4. POST to the sidecar `/send` with:
   ```json
   {
     "type": "document",
     "agentId": "...",
     "jid": "...",
     "media_b64": "base64...",
     "mimetype": "application/pdf",
     "filename": "report.pdf",
     "caption": "..."
   }
   ```
   For `image`/`video`/`audio`, use `type` accordingly and omit `filename` where not applicable.

### 4.3 `isli-channels/src/isli_channels/main.py`
Update `SendMessageRequest` schema:
```python
class AttachmentRequest(BaseModel):
    download_url: str
    filename: str
    mime_type: str
    size_bytes: int
    caption: str | None = None

class SendMessageRequest(BaseModel):
    ...
    attachments: list[AttachmentRequest] = []
```
Forward `attachments` to `adapter.send_message(...)`.

---

## 5. WhatsApp sidecar (`isli-whatsapp-sidecar/index.js`)

Extend the `/send` handler to support document, image, video, and audio messages from base64 data.

```javascript
app.post('/send', requireAuth, async (req, res) => {
    const { type, agentId, jid, text, audio_b64, caption, media_b64, mimetype, filename } = req.body;
    const sock = sessions.get(agentId);
    if (!sock) return res.status(404).json({ error: 'Session not found' });

    try {
        if (type === 'audio' && audio_b64) {
            // existing PTT path
        } else if (['document', 'image', 'video', 'audio'].includes(type) && media_b64) {
            const tmpPath = path.join('/tmp', `isli_${type}_${Date.now()}_${Math.random().toString(36).slice(2)}`);
            try {
                fs.writeFileSync(tmpPath, Buffer.from(media_b64, 'base64'));
                let messageContent;
                if (type === 'document') messageContent = { document: { url: tmpPath }, mimetype, fileName: filename, caption };
                else if (type === 'image') messageContent = { image: { url: tmpPath }, caption };
                else if (type === 'video') messageContent = { video: { url: tmpPath }, caption };
                else if (type === 'audio') messageContent = { audio: { url: tmpPath }, mimetype, ptt: false };
                const sentMsg = await sock.sendMessage(jid, messageContent);
                res.json({ success: true, messageId: sentMsg.key.id });
            } finally {
                try { fs.unlinkSync(tmpPath); } catch (e) {}
            }
        } else {
            // existing text path
        }
    } catch (error) {
        logger.error(...);
        res.status(500).json({ error: error.message });
    }
});
```

Also update the Dockerfile to ensure `curl` is installed (already required per CLAUDE.md gotchas, but verify).

---

## 6. Board UI

### 6.1 Message type update (`isli-board/src/types/index.ts`)
```typescript
export interface Attachment {
  filename: string
  mime_type: string
  size_bytes: number
  download_url: string
  caption?: string
}

export interface Message {
  ...
  attachments?: Attachment[]
}
```

### 6.2 Message rendering (`isli-board/src/components/ConversationsPage.tsx`)
Below each assistant message, render an `AttachmentList` component when `msg.attachments?.length > 0`.

### 6.3 New component: `isli-board/src/components/AttachmentList.tsx`
- Render attachment cards/pills showing filename, mime type, and human-readable size.
- "Download" button opens `download_url`.
- "View" button opens a modal:
  - Images: `<img src={download_url} />`.
  - PDFs/video/audio: `<iframe>` or `<object>` / `<video controls>` / `<audio controls>`.
  - Text/code files: fetch via the signed URL and render in a monospace preview.
  - Unknown types: show metadata and download button.
- Use the existing `Modal` component from `@/components/ui/Modal`.

### 6.4 ui-components skill: new `file_card` component
Update `isli-agent-sdk/src/isli_agent/tools/ui_renderer.py`:
- Add `file_card` to `COMPONENT_TYPES`.
- Document props schema:
  ```json
  {
    "filename": "report.pdf",
    "mime_type": "application/pdf",
    "size_bytes": 12345,
    "download_url": "...",
    "view_url": "...",
    "caption": "Optional description"
  }
  ```

Update `isli-board/src/components/ui/registry/UiComponentRegistry.tsx`:
- Add `file_card: FileCard` to registry.

Create `isli-board/src/components/ui/registry/FileCard.tsx`:
- Shows file name, icon based on mime type, size, caption.
- Download and View buttons.
- View button opens the same modal preview used in `AttachmentList`.

---

## 7. Outbox promotion compatibility

The existing `handle_session_persist` in `isli-core/src/isli_core/startup/outbox.py` rewrites `blob:audio:*` and `blob:browser:*` tokens to workspace disk. It must ignore attachment URLs because they are already workspace-backed signed URLs. No change needed, but add a comment/log line clarifying that `blob:*` tokens are promoted while `download_url` fields are left as-is.

---

## 8. Database migration

No new table is required because `Session.messages` and `ChannelMessage.raw_payload` are JSON columns. However, add an Alembic migration to document the schema expectation:

`isli-core/alembic/versions/20260616_add_session_message_attachments.py`
- No-op migration (or add a comment column if desired).
- Marks the point where assistant message objects may contain an `attachments` array.

Alternatively, if we want a dedicated index for files, add `session_attachments` table. Recommendation: **no dedicated table** for the first iteration to keep the change minimal.

---

## 9. Security

- Signed URLs use Core's `jwt_secret`, scoped to a single file path, with short expiry (5 min default, max 30 min).
- The `/v1/internal/files/download` endpoint validates scope and path claims; it never accepts arbitrary paths.
- File access is still gated by Workspace's `check_access`, which calls Core `/v1/internal/verify-access` for shared scopes.
- Agents can only stage files from their own workspace or shared workspaces they are members of.
- Content scan / policy engine: attachments are not scanned by Core; they originate from the agent's own sandbox. If later needed, add a virus-scan hook; out of scope for this iteration.

---

## 10. Tests

### 10.1 Core tests
- `isli-core/tests/test_api_file_sharing.py`: add cases for:
  - `POST /v1/workspaces/{agent_id}/file-url` returns a valid signed URL.
  - `GET /v1/internal/files/download` with a valid token streams the file.
  - `GET /v1/internal/files/download` with a missing/invalid token returns 401/403.
  - Session reply with attachments produces `attachments` in the response message and forwards them to channels.

### 10.2 Channels tests
- `isli-channels/tests/test_api.py`: add cases for `/send` with attachments:
  - Telegram adapter mocks `bot.send_document`/`send_photo`.
  - WhatsApp adapter forwards correct payload to sidecar.
  - Oversize or unsupported mime is dropped with a warning.

### 10.3 Workspace tests
- `isli-workspace/tests/test_api.py`: add `/metadata` success and 404 cases.

### 10.4 SDK tests
- `isli-agent-sdk/tests/test_runner_sync.py` or a new `test_attachments.py`: verify `stage_reply_attachment` populates pending state and is included in `reply_to_session` payload.

### 10.5 Board tests
- Type-check the new `Attachment` interface and `FileCard` component.
- Existing tests should still pass; no breaking changes to current message shape (attachments optional).

---

## 11. Deployment / rebuild notes

Per project memory: **rebuild from source is the only acceptable deployment pattern** ([[docker-build-vs-cp]]). The following images must be rebuilt:
- `isli-core`
- `isli-workspace`
- `isli-channels`
- `isli-whatsapp-sidecar`
- `isli-board`
- Any agent-runner image that uses the updated SDK.

No new Python dependencies are required (`mimetypes` is stdlib). No new Node dependencies are required.

---

## 12. Phased implementation order

1. **Workspace metadata endpoint** — smallest, unblocks Core.
2. **Core signed-URL endpoints + reply schema + forward to channels** — no UI yet; test with curl.
3. **Channels Telegram adapter** — verify end-to-end with a PDF from agent workspace.
4. **WhatsApp sidecar + adapter** — verify document/image send.
5. **SDK tool + runner wiring** — agents can now stage files naturally.
6. **Board UI attachment list + view modal** — web users can download/view.
7. **ui-components `file_card` enhancement** — agents can render file cards inline.
8. **Tests + migration + prompts.yaml update** — polish and document.

---

## Open questions resolved
- **Normal replies or only proactive?** → Normal replies via `stage_reply_attachment`; proactive `send_message` skill can be extended in a follow-up.
- **Base64 vs signed URL** → Signed URLs (option B).
- **Need dedicated attachment table?** → No, use JSON message field for the first iteration.
- **WhatsApp media base64 size limits?** → Respect `PLATFORM_FORMATS["whatsapp"]["max_size_mb"]` = 16 MB; drop oversize attachments rather than failing the reply.
