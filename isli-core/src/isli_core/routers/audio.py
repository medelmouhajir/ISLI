import base64
import structlog
from pathlib import PurePosixPath
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
import httpx

from isli_core.auth import create_internal_token
from isli_core.config import get_settings
from isli_core.db import get_db
from isli_core.models import Session
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()
router = APIRouter(prefix="/audio", tags=["audio"])


@router.get("/{session_id}/{filename}")
async def download_session_audio(
    session_id: str,
    filename: str,
    db: AsyncSession = Depends(get_db),
):
    """Stream an audio file stored in the workspace for a given session.

    Validates that the caller's session exists and the audio path is well-formed.
    Proxies the workspace service /download endpoint with internal auth.
    """
    # Validate filename (must be a UUID-like safe name, no path traversal)
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    # Validate session exists
    result = await db.execute(
        select(Session).where(Session.id == session_id, Session.deleted_at.is_(None))
    )
    sess = result.scalar_one_or_none()
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")

    # Build the workspace path for the audio file
    # Stored at: _attachments/audio/{session_id}/{filename}
    workspace_path = f"_attachments/audio/{session_id}/{filename}"

    settings = get_settings()
    url = f"{settings.workspace_url}/download"
    token = create_internal_token("core-api", scopes=["workspace"], expires_minutes=1)

    async def stream_file():
        async with httpx.AsyncClient(timeout=60.0) as client:
            params = {
                "agent_id": sess.agent_id,
                "path": workspace_path,
                "scope": "attachment",
                "scope_id": session_id,
            }
            async with client.stream(
                "GET",
                url,
                params=params,
                headers={"X-Internal-Auth": f"Bearer {token}"},
            ) as resp:
                resp.raise_for_status()
                async for chunk in resp.aiter_bytes():
                    yield chunk

    return StreamingResponse(
        stream_file(),
        media_type="audio/wav",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )
