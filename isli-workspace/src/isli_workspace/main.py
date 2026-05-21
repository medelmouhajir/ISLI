import os
from contextlib import asynccontextmanager
from typing import Any

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Depends, UploadFile, File, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel
import structlog

from .config import settings
from .sandbox import read_file, write_file, list_dir, delete_file, write_file_bytes, create_dir, resolve_path
from .auth import require_internal_auth

SERVICE_NAME = "isli-workspace"
logger = structlog.get_logger()


class ReadRequest(BaseModel):
    agent_id: str
    path: str


class WriteRequest(BaseModel):
    agent_id: str
    path: str
    content: str


class ListRequest(BaseModel):
    agent_id: str
    path: str = ""


class DeleteRequest(BaseModel):
    agent_id: str
    path: str


class MkdirRequest(BaseModel):
    agent_id: str
    path: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    base = Path(settings.workspace_base_path)
    base.mkdir(parents=True, exist_ok=True)
    logger.info("workspace.startup", service=SERVICE_NAME, base_path=str(base))
    yield
    logger.info("workspace.shutdown", service=SERVICE_NAME)


app = FastAPI(
    title="ISLI Workspace",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health():
    return {"status": "ok", "service": SERVICE_NAME}


@app.get("/ready")
async def ready():
    base = Path(settings.workspace_base_path)
    return {"status": "ready", "service": SERVICE_NAME, "base_path": str(base), "writable": os.access(base, os.W_OK)}


@app.get("/live")
async def live():
    return {"status": "alive", "service": SERVICE_NAME}


@app.post("/read")
async def read(body: ReadRequest, _auth: dict = Depends(require_internal_auth)):
    try:
        result = read_file(body.agent_id, settings.workspace_base_path, body.path)
        return {"status": "ok", **result}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except PermissionError as exc:
        logger.error("workspace.permission_denied", agent_id=body.agent_id, path=body.path, error=str(exc))
        raise HTTPException(status_code=403, detail=str(exc))
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/write")
async def write(body: WriteRequest, _auth: dict = Depends(require_internal_auth)):
    try:
        result = write_file(body.agent_id, settings.workspace_base_path, body.path, body.content)
        return {"status": "ok", **result}
    except PermissionError as exc:
        logger.error("workspace.permission_denied", agent_id=body.agent_id, path=body.path, error=str(exc))
        raise HTTPException(status_code=403, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=413, detail=str(exc))
    except OSError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/list")
async def list_files(body: ListRequest, _auth: dict = Depends(require_internal_auth)):
    try:
        result = list_dir(body.agent_id, settings.workspace_base_path, body.path)
        return {"status": "ok", **result}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except PermissionError as exc:
        logger.error("workspace.permission_denied", agent_id=body.agent_id, path=body.path, error=str(exc))
        raise HTTPException(status_code=403, detail=str(exc))
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/delete")
async def delete(body: DeleteRequest, _auth: dict = Depends(require_internal_auth)):
    try:
        result = delete_file(body.agent_id, settings.workspace_base_path, body.path)
        return {"status": "ok", **result}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except PermissionError as exc:
        logger.error("workspace.permission_denied", agent_id=body.agent_id, path=body.path, error=str(exc))
        raise HTTPException(status_code=403, detail=str(exc))
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/upload")
async def upload(
    agent_id: str = Form(...),
    path: str = Form(...),
    file: UploadFile = File(...),
    _auth: dict = Depends(require_internal_auth)
):
    try:
        content = await file.read()
        result = write_file_bytes(agent_id, settings.workspace_base_path, path, content)
        return {"status": "ok", **result}
    except PermissionError as exc:
        logger.error("workspace.permission_denied", agent_id=agent_id, path=path, error=str(exc))
        raise HTTPException(status_code=403, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=413, detail=str(exc))
    except OSError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/download")
async def download(
    agent_id: str,
    path: str,
    _auth: dict = Depends(require_internal_auth)
):
    try:
        file_path = resolve_path(agent_id, settings.workspace_base_path, path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        if file_path.is_dir():
            raise HTTPException(status_code=400, detail="Cannot download a directory")
        
        return FileResponse(
            path=file_path,
            filename=file_path.name,
            media_type="application/octet-stream"
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except PermissionError as exc:
        logger.error("workspace.permission_denied", agent_id=agent_id, path=path, error=str(exc))
        raise HTTPException(status_code=403, detail=str(exc))
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/mkdir")
async def mkdir(body: MkdirRequest, _auth: dict = Depends(require_internal_auth)):
    try:
        result = create_dir(body.agent_id, settings.workspace_base_path, body.path)
        return {"status": "ok", **result}
    except PermissionError as exc:
        logger.error("workspace.permission_denied", agent_id=body.agent_id, path=body.path, error=str(exc))
        raise HTTPException(status_code=403, detail=str(exc))
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
