from pathlib import PurePosixPath
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from isli_core.auth import create_internal_token, require_admin_auth
from isli_core.config import get_settings

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


class MkdirRequest(BaseModel):
    path: str


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
    _admin: str = Depends(require_admin_auth)
):
    valid_path = _validate_path(path)
    return await _proxy_request("POST", "list", {"agent_id": agent_id, "path": valid_path})


@router.get("/{agent_id}/read")
async def read_workspace_file(
    agent_id: str,
    path: str,
    _admin: str = Depends(require_admin_auth)
):
    valid_path = _validate_path(path)
    if not valid_path:
        raise HTTPException(status_code=400, detail="Path is required for read")
    return await _proxy_request("POST", "read", {"agent_id": agent_id, "path": valid_path})


@router.post("/{agent_id}/write")
async def write_workspace_file(
    agent_id: str,
    payload: WriteFileRequest,
    _admin: str = Depends(require_admin_auth)
):
    valid_path = _validate_path(payload.path)
    if not valid_path:
        raise HTTPException(status_code=400, detail="Path is required for write")
    return await _proxy_request("POST", "write", {
        "agent_id": agent_id,
        "path": valid_path,
        "content": payload.content
    })


@router.delete("/{agent_id}/delete")
async def delete_workspace_file(
    agent_id: str,
    path: str,
    _admin: str = Depends(require_admin_auth)
):
    valid_path = _validate_path(path)
    if not valid_path:
        raise HTTPException(status_code=400, detail="Path is required for delete")
    return await _proxy_request("POST", "delete", {"agent_id": agent_id, "path": valid_path})


@router.post("/{agent_id}/upload")
async def upload_workspace_file(
    agent_id: str,
    path: str,
    file: UploadFile = File(...),
    _admin: str = Depends(require_admin_auth)
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
            data = {"agent_id": agent_id, "path": valid_path}
            resp = await client.post(url, data=data, files=files, headers={"X-Internal-Auth": token})
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
    _admin: str = Depends(require_admin_auth)
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
            async with client.stream("GET", url, params={"agent_id": agent_id, "path": valid_path}, headers={"X-Internal-Auth": token}) as resp:
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
    _admin: str = Depends(require_admin_auth)
):
    valid_path = _validate_path(payload.path)
    if not valid_path:
        raise HTTPException(status_code=400, detail="Path is required for mkdir")
    return await _proxy_request("POST", "mkdir", {"agent_id": agent_id, "path": valid_path})

