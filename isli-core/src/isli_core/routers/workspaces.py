from datetime import UTC, datetime, timedelta
from pathlib import PurePosixPath
from typing import Any

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from isli_core.auth import create_internal_token, require_admin_auth, require_internal_auth
from isli_core.config import get_settings
from isli_core.db import get_db
from isli_core.models import SharedWorkspace

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


def _validate_path(path: str) -> str:
    if not path:
        return ""
    normalized = str(PurePosixPath(path))
    if ".." in normalized or normalized.startswith("/"):
        raise HTTPException(status_code=400, detail="Invalid path")
    return normalized


class WriteFileRequest(BaseModel):
    path: str
    content: str
    scope: str = "agent"
    scope_id: str | None = None


class MkdirRequest(BaseModel):
    path: str
    scope: str = "agent"
    scope_id: str | None = None


async def upload_bytes_to_workspace(
    agent_id: str,
    path: str,
    data: bytes,
    scope: str = "agent",
    scope_id: str | None = None,
) -> dict[str, Any]:
    """Upload raw bytes to the workspace service as a multipart file upload."""
    settings = get_settings()
    url = f"{settings.workspace_url}/upload"
    token = create_internal_token("core-api", scopes=["workspace"], expires_minutes=1)

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            filename = path.split("/")[-1] or "file"
            files = {"file": (filename, data, "application/octet-stream")}
            form_data = {
                "agent_id": agent_id,
                "path": path,
                "scope": scope,
                "scope_id": scope_id or agent_id,
            }
            resp = await client.post(
                url,
                data=form_data,
                files=files,
                headers={"X-Internal-Auth": token},
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.json().get("detail", str(exc))
            raise HTTPException(status_code=exc.response.status_code, detail=detail)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Workspace upload error: {str(exc)}")


async def _proxy_request(method: str, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    url = f"{settings.workspace_url}/{endpoint}"

    # Internal auth for workspace service
    token = create_internal_token("core-api", scopes=["workspace"], expires_minutes=1)

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.post(url, json=payload, headers={"X-Internal-Auth": token})
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.json().get("detail", str(exc))
            raise HTTPException(status_code=exc.response.status_code, detail=detail)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Workspace service error: {str(exc)}")


@router.get("/{agent_id}/list")
async def list_workspace_files(
    agent_id: str,
    path: str = "",
    scope: str = "agent",
    scope_id: str | None = None,
    admin: str = Depends(require_admin_auth)
):
    valid_path = _validate_path(path)
    return await _proxy_request("POST", "list", {
        "agent_id": agent_id,
        "path": valid_path,
        "scope": scope,
        "scope_id": scope_id or agent_id
    })


@router.get("/{agent_id}/read")
async def read_workspace_file(
    agent_id: str,
    path: str,
    scope: str = "agent",
    scope_id: str | None = None,
    admin: str = Depends(require_admin_auth)
):
    valid_path = _validate_path(path)
    if not valid_path:
        raise HTTPException(status_code=400, detail="Path is required for read")
    return await _proxy_request("POST", "read", {
        "agent_id": agent_id,
        "path": valid_path,
        "scope": scope,
        "scope_id": scope_id or agent_id
    })


@router.post("/{agent_id}/write")
async def write_workspace_file(
    agent_id: str,
    payload: WriteFileRequest,
    admin: str = Depends(require_admin_auth)
):
    valid_path = _validate_path(payload.path)
    if not valid_path:
        raise HTTPException(status_code=400, detail="Path is required for write")
    return await _proxy_request("POST", "write", {
        "agent_id": agent_id,
        "path": valid_path,
        "content": payload.content,
        "scope": payload.scope,
        "scope_id": payload.scope_id or agent_id
    })


@router.delete("/{agent_id}/delete")
async def delete_workspace_file(
    agent_id: str,
    path: str,
    scope: str = "agent",
    scope_id: str | None = None,
    admin: str = Depends(require_admin_auth)
):
    valid_path = _validate_path(path)
    if not valid_path:
        raise HTTPException(status_code=400, detail="Path is required for delete")
    return await _proxy_request("POST", "delete", {
        "agent_id": agent_id,
        "path": valid_path,
        "scope": scope,
        "scope_id": scope_id or agent_id
    })


@router.post("/{agent_id}/upload")
async def upload_workspace_file(
    agent_id: str,
    path: str,
    scope: str = "agent",
    scope_id: str | None = None,
    file: UploadFile = File(...),
    admin: str = Depends(require_admin_auth)
):
    valid_path = _validate_path(path)
    if not valid_path:
        raise HTTPException(status_code=400, detail="Path is required for upload")

    settings = get_settings()
    url = f"{settings.workspace_url}/upload"
    token = create_internal_token("core-api", scopes=["workspace"], expires_minutes=1)

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            files = {"file": (file.filename, await file.read(), file.content_type)}
            data = {
                "agent_id": agent_id,
                "path": valid_path,
                "scope": scope,
                "scope_id": scope_id or agent_id
            }
            resp = await client.post(
                url,
                data=data,
                files=files,
                headers={"X-Internal-Auth": token},
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.json().get("detail", str(exc))
            raise HTTPException(status_code=exc.response.status_code, detail=detail)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Workspace service error: {str(exc)}")


@router.get("/{agent_id}/download")
async def download_workspace_file(
    agent_id: str,
    path: str,
    scope: str = "agent",
    scope_id: str | None = None,
    admin: str = Depends(require_admin_auth)
):
    valid_path = _validate_path(path)
    if not valid_path:
        raise HTTPException(status_code=400, detail="Path is required for download")

    settings = get_settings()
    url = f"{settings.workspace_url}/download"
    token = create_internal_token("core-api", scopes=["workspace"], expires_minutes=1)

    # We use a streaming response to proxy the file download
    async def stream_file():
        async with httpx.AsyncClient(timeout=60.0) as client:
            params = {
                "agent_id": agent_id,
                "path": valid_path,
                "scope": scope,
                "scope_id": scope_id or agent_id
            }
            async with client.stream(
                "GET",
                url,
                params=params,
                headers={"X-Internal-Auth": token},
            ) as resp:
                resp.raise_for_status()
                async for chunk in resp.aiter_bytes():
                    yield chunk

    return StreamingResponse(
        stream_file(),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{valid_path.split("/")[-1]}"'}
    )


@router.post("/{agent_id}/mkdir")
async def create_workspace_dir(
    agent_id: str,
    payload: MkdirRequest,
    admin: str = Depends(require_admin_auth)
):
    valid_path = _validate_path(payload.path)
    if not valid_path:
        raise HTTPException(status_code=400, detail="Path is required for mkdir")
    return await _proxy_request("POST", "mkdir", {
        "agent_id": agent_id,
        "path": valid_path,
        "scope": payload.scope,
        "scope_id": payload.scope_id or agent_id
    })


async def fetch_file_metadata(
    agent_id: str,
    scope: str,
    scope_id: str,
    path: str,
) -> dict[str, Any]:
    """Fetch file metadata from the workspace service."""
    settings = get_settings()
    url = f"{settings.workspace_url}/metadata"
    token = create_internal_token("core-api", scopes=["workspace"], expires_minutes=1)
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            url,
            json={"agent_id": agent_id, "scope": scope, "scope_id": scope_id, "path": path},
            headers={"X-Internal-Auth": token},
        )
        if resp.status_code == 404:
            raise HTTPException(status_code=404, detail=f"File not found: {path}")
        if resp.status_code == 403:
            raise HTTPException(status_code=403, detail=f"Access denied to file: {path}")
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        return data


class FileMetadataIn(BaseModel):
    agent_id: str
    path: str
    scope: str = "agent"
    scope_id: str | None = None


@router.post("/file-metadata")
async def file_metadata(
    payload: FileMetadataIn,
    auth: dict[str, Any] = Depends(require_internal_auth),
) -> dict[str, Any]:
    """Allow an agent (or internal service) to validate a file path and get its metadata."""
    caller: str = auth.get("sub") or ""
    scope = payload.scope
    scope_id = payload.scope_id or caller

    if scope == "agent" and caller != payload.agent_id:
        raise HTTPException(
            status_code=403,
            detail="Cannot fetch metadata for another agent's workspace",
        )

    return await fetch_file_metadata(
        payload.agent_id,
        scope,
        scope_id,
        _validate_path(payload.path),
    )


class FileUrlRequest(BaseModel):
    path: str
    workspace_id: str | None = None
    caption: str | None = None
    expires_minutes: int = 10


def _create_file_download_token(
    agent_id: str,
    scope: str,
    scope_id: str,
    path: str,
    expires_minutes: int,
) -> str:
    """Create a short-lived signed token for a single file download."""
    return create_internal_token(
        "core-api",
        scopes=["workspace:download"],
        expires_minutes=min(expires_minutes, 30),
        extra_claims={
            "agent_id": agent_id,
            "scope": scope,
            "scope_id": scope_id,
            "file_path": path,
        },
    )


@router.post("/{agent_id}/file-url")
async def create_file_download_url(
    agent_id: str,
    payload: FileUrlRequest,
    auth: dict[str, Any] = Depends(require_internal_auth),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Generate a signed download URL for a file in agent or shared workspace."""
    caller = auth.get("sub")
    if payload.workspace_id:
        scope = "shared"
        scope_id = payload.workspace_id
        # Verify shared workspace membership
        result = await db.execute(
            select(SharedWorkspace).where(
                SharedWorkspace.id == scope_id,
                SharedWorkspace.deleted_at.is_(None),
            )
        )
        workspace = result.scalar_one_or_none()
        if not workspace:
            raise HTTPException(status_code=404, detail="Shared workspace not found")
        if caller != workspace.owner_id and caller not in (workspace.members or []):
            raise HTTPException(
                status_code=403,
                detail="Access denied to shared workspace",
            )
    else:
        scope = "agent"
        scope_id = agent_id
        if caller != agent_id:
            raise HTTPException(
                status_code=403,
                detail="Cannot create download URL for another agent's workspace",
            )

    valid_path = _validate_path(payload.path)
    if not valid_path:
        raise HTTPException(status_code=400, detail="Path is required")

    meta = await fetch_file_metadata(agent_id, scope, scope_id, valid_path)

    token = _create_file_download_token(
        agent_id=agent_id,
        scope=scope,
        scope_id=scope_id,
        path=valid_path,
        expires_minutes=payload.expires_minutes,
    )

    expires_at = datetime.now(UTC) + timedelta(minutes=min(payload.expires_minutes, 30))

    return {
        "status": "ok",
        "download_url": f"/v1/internal/files/download?token={token}",
        "expires_at": expires_at.isoformat(),
        "filename": meta["filename"],
        "mime_type": meta["mime_type"],
        "size_bytes": meta["size_bytes"],
        "caption": payload.caption,
        "scope": scope,
        "scope_id": scope_id,
        "path": valid_path,
    }

