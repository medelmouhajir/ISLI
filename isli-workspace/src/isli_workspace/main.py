import json
import os
import shutil
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import httpx
import structlog
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .auth import require_internal_auth
from .config import settings
from .sandbox import (
    check_quota,
    create_dir,
    delete_file,
    list_dir,
    move_file,
    read_file,
    resolve_path,
    search_workspace,
    write_file,
    write_file_bytes,
)
from .git_ops import (
    git_clone,
    git_status,
    git_commit,
    git_push,
    git_pull,
    git_branch_list,
    git_branch_create,
    git_checkout,
    git_log,
    GitNotRepoError,
    GitAuthError,
    GitConflictError,
    GitRemoteError,
    GitInvalidOperationError,
)
from .package_ops import (
    pip_install,
    pip_list,
    PackageInstallError,
    PackageInvalidError,
    PackageTimeoutError,
)

SERVICE_NAME = "isli-workspace"
logger = structlog.get_logger()

ScopeType = Literal["agent", "attachment", "shared"]

class BaseWorkspaceRequest(BaseModel):
    agent_id: str
    scope: ScopeType = "agent"
    scope_id: str | None = None  # If None, defaults to agent_id

    @property
    def effective_scope_id(self) -> str:
        return self.scope_id or self.agent_id


class ReadRequest(BaseWorkspaceRequest):
    path: str
    max_chars: int = 16000
    line_start: int = 1
    line_end: int | None = None


class WriteRequest(BaseWorkspaceRequest):
    path: str
    content: str


class ListRequest(BaseWorkspaceRequest):
    path: str = ""


class DeleteRequest(BaseWorkspaceRequest):
    path: str


class MkdirRequest(BaseWorkspaceRequest):
    path: str


class AttachRequest(BaseModel):
    agent_id: str
    task_id: str
    source_path: str
    target_path: str


class PullRequest(BaseModel):
    agent_id: str
    task_id: str
    source_path: str
    target_path: str


class PromoteRequest(BaseModel):
    agent_id: str
    source_scope: ScopeType
    source_scope_id: str
    source_path: str
    target_workspace_id: str
    target_path: str
    delete_source: bool = False
    quota_bytes: int | None = None


class MoveRequest(BaseModel):
    agent_id: str
    source_workspace_id: str
    source_path: str
    target_workspace_id: str | None = None
    target_path: str


class SearchRequest(BaseModel):
    agent_id: str
    workspace_id: str
    query: str
    path: str = ""
    search_names: bool = True
    search_content: bool = False
    case_sensitive: bool = False
    max_results: int = 50


class GitCloneRequest(BaseWorkspaceRequest):
    path: str
    url: str
    branch: str | None = None


class GitStatusRequest(BaseWorkspaceRequest):
    path: str


class GitCommitRequest(BaseWorkspaceRequest):
    path: str
    message: str
    files: list[str] | None = None


class GitPushRequest(BaseWorkspaceRequest):
    path: str
    remote: str = "origin"
    branch: str | None = None


class GitPullRequest(BaseWorkspaceRequest):
    path: str
    remote: str = "origin"
    branch: str | None = None


class GitBranchListRequest(BaseWorkspaceRequest):
    path: str


class GitBranchCreateRequest(BaseWorkspaceRequest):
    path: str
    branch_name: str
    checkout: bool = False


class GitCheckoutRequest(BaseWorkspaceRequest):
    path: str
    branch_name: str


class GitLogRequest(BaseWorkspaceRequest):
    path: str
    max_count: int = 30
    max_chars: int = 12000


class PipInstallRequest(BaseWorkspaceRequest):
    packages: list[str]
    upgrade: bool = False


class PipListRequest(BaseWorkspaceRequest):
    pass


async def check_access(agent_id: str, scope: ScopeType, scope_id: str):
    """
    Verify if the agent has access to the given scope.
    Calls isli-core for verification.
    """
    if scope == "agent":
        if agent_id != scope_id:
            logger.warning("workspace.access_denied", agent_id=agent_id, scope=scope, scope_id=scope_id)
            raise HTTPException(status_code=403, detail="Cannot access another agent's workspace directly")
        return

    # For shared and attachment scopes, we verify with isli-core
    # In a production environment, this would ideally be cached in Redis
    try:
        from .auth import create_internal_token
        token = create_internal_token("isli-workspace", scopes=["core"], expires_minutes=1)
        headers = {"Authorization": f"Bearer {token}"}

        core_url = os.getenv("CORE_API_INTERNAL_URL", "http://core:8000")

        async with httpx.AsyncClient() as client:
            endpoint = f"/v1/internal/verify-access?agent_id={agent_id}&scope={scope}&scope_id={scope_id}"
            resp = await client.get(f"{core_url}{endpoint}", headers=headers)
            if resp.status_code != 200:
                logger.warning("workspace.access_denied", agent_id=agent_id, scope=scope, scope_id=scope_id, status=resp.status_code)
                raise HTTPException(status_code=403, detail=f"Access denied to {scope} {scope_id}")
    except httpx.RequestError as exc:
        logger.error("workspace.core_connection_error", error=str(exc))
        # Fail closed for security
        raise HTTPException(status_code=503, detail="Cannot verify access rights")


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
async def read(body: ReadRequest, auth: dict = Depends(require_internal_auth)):
    await check_access(body.agent_id, body.scope, body.effective_scope_id)
    try:
        result = read_file(
            body.scope, body.effective_scope_id, settings.workspace_base_path, body.path,
            max_chars=body.max_chars, line_start=body.line_start, line_end=body.line_end
        )
        return {"status": "ok", **result}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except PermissionError as exc:
        logger.error("workspace.permission_denied", agent_id=body.agent_id, path=body.path, error=str(exc))
        raise HTTPException(status_code=403, detail=str(exc))
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/write")
async def write(body: WriteRequest, quota_bytes: int | None = None, auth: dict = Depends(require_internal_auth)):
    await check_access(body.agent_id, body.scope, body.effective_scope_id)
    try:
        result = write_file(body.scope, body.effective_scope_id, settings.workspace_base_path, body.path, body.content, quota_bytes)
        return {"status": "ok", **result}
    except PermissionError as exc:
        logger.error("workspace.permission_denied", agent_id=body.agent_id, path=body.path, error=str(exc))
        raise HTTPException(status_code=403, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=413, detail=str(exc))
    except OSError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/list")
async def list_files(body: ListRequest, auth: dict = Depends(require_internal_auth)):
    await check_access(body.agent_id, body.scope, body.effective_scope_id)
    try:
        result = list_dir(body.scope, body.effective_scope_id, settings.workspace_base_path, body.path)
        return {"status": "ok", **result}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except PermissionError as exc:
        logger.error("workspace.permission_denied", agent_id=body.agent_id, path=body.path, error=str(exc))
        raise HTTPException(status_code=403, detail=str(exc))
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/delete")
async def delete(body: DeleteRequest, auth: dict = Depends(require_internal_auth)):
    await check_access(body.agent_id, body.scope, body.effective_scope_id)
    try:
        result = delete_file(body.scope, body.effective_scope_id, settings.workspace_base_path, body.path)
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
    scope: ScopeType = Form("agent"),
    scope_id: str | None = Form(None),
    path: str = Form(...),
    file: UploadFile = File(...),
    quota_bytes: int | None = Form(None),
    auth: dict = Depends(require_internal_auth)
):
    effective_scope_id = scope_id or agent_id
    await check_access(agent_id, scope, effective_scope_id)
    try:
        content = await file.read()
        result = write_file_bytes(scope, effective_scope_id, settings.workspace_base_path, path, content, quota_bytes)
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
    scope: ScopeType = "agent",
    scope_id: str | None = None,
    auth: dict = Depends(require_internal_auth)
):
    effective_scope_id = scope_id or agent_id
    await check_access(agent_id, scope, effective_scope_id)
    try:
        file_path = resolve_path(scope, effective_scope_id, settings.workspace_base_path, path)
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
async def mkdir(body: MkdirRequest, auth: dict = Depends(require_internal_auth)):
    await check_access(body.agent_id, body.scope, body.effective_scope_id)
    try:
        result = create_dir(body.scope, body.effective_scope_id, settings.workspace_base_path, body.path)
        return {"status": "ok", **result}
    except PermissionError as exc:
        logger.error("workspace.permission_denied", agent_id=body.agent_id, path=body.path, error=str(exc))
        raise HTTPException(status_code=403, detail=str(exc))
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/attachments/attach")
async def attach(body: AttachRequest, auth: dict = Depends(require_internal_auth)):
    """Copy a file from agent workspace to task attachment."""
    await check_access(body.agent_id, "attachment", body.task_id)
    try:
        src = resolve_path("agent", body.agent_id, settings.workspace_base_path, body.source_path)
        dst = resolve_path("attachment", body.task_id, settings.workspace_base_path, body.target_path)

        if not src.exists() or src.is_dir():
            raise HTTPException(status_code=400, detail="Invalid source file")

        dst.parent.mkdir(parents=True, exist_ok=True, mode=0o777)
        shutil.copy2(src, dst)

        stat = dst.stat()
        return {
            "status": "ok",
            "path": body.target_path,
            "size_bytes": stat.st_size,
            "attached_at": datetime.now(UTC).isoformat()
        }
    except Exception as exc:
        logger.error("workspace.attach_failed", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/attachments/pull")
async def pull(body: PullRequest, auth: dict = Depends(require_internal_auth)):
    """Pull an attachment from task to agent workspace, with metadata."""
    await check_access(body.agent_id, "attachment", body.task_id)
    try:
        src = resolve_path("attachment", body.task_id, settings.workspace_base_path, body.source_path)
        dst = resolve_path("agent", body.agent_id, settings.workspace_base_path, body.target_path)

        if not src.exists() or src.is_dir():
            raise HTTPException(status_code=400, detail="Invalid source attachment")

        dst.parent.mkdir(parents=True, exist_ok=True, mode=0o777)
        shutil.copy2(src, dst)

        # Write metadata sidecar
        meta_path = dst.with_suffix(dst.suffix + ".metadata.json")
        metadata = {
            "source_ref": {
                "task_id": body.task_id,
                "original_path": body.source_path
            },
            "pulled_at": datetime.now(UTC).isoformat(),
            "pulled_by": body.agent_id
        }
        meta_path.write_text(json.dumps(metadata, indent=2))

        return {"status": "ok", "path": body.target_path}
    except Exception as exc:
        logger.error("workspace.pull_failed", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/shared/promote")
async def promote(body: PromoteRequest, auth: dict = Depends(require_internal_auth)):
    """Promote a file from agent/task to shared workspace."""
    await check_access(body.agent_id, body.source_scope, body.source_scope_id)
    await check_access(body.agent_id, "shared", body.target_workspace_id)

    try:
        src = resolve_path(body.source_scope, body.source_scope_id, settings.workspace_base_path, body.source_path)
        dst = resolve_path("shared", body.target_workspace_id, settings.workspace_base_path, body.target_path)

        if not src.exists() or src.is_dir():
            raise HTTPException(status_code=400, detail="Invalid source file")

        # Check shared workspace quota before writing
        size = src.stat().st_size
        if not check_quota("shared", body.target_workspace_id, settings.workspace_base_path, size, body.quota_bytes):
            raise HTTPException(status_code=413, detail="Shared workspace quota exceeded")

        dst.parent.mkdir(parents=True, exist_ok=True, mode=0o777)

        if body.delete_source:
            shutil.move(src, dst)
        else:
            shutil.copy2(src, dst)

        return {"status": "ok", "path": body.target_path}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("workspace.promote_failed", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/shared/move")
async def shared_move(body: MoveRequest, auth: dict = Depends(require_internal_auth)):
    """Move or rename a file within (or between) shared workspaces."""
    target_workspace_id = body.target_workspace_id or body.source_workspace_id
    await check_access(body.agent_id, "shared", body.source_workspace_id)
    await check_access(body.agent_id, "shared", target_workspace_id)

    try:
        result = move_file(
            "shared", body.source_workspace_id, settings.workspace_base_path, body.source_path,
            "shared", target_workspace_id, settings.workspace_base_path, body.target_path,
        )
        return {
            "status": "moved",
            "source_path": body.source_path,
            "source_workspace_id": body.source_workspace_id,
            "target_path": result["path"],
            "target_workspace_id": target_workspace_id,
            **{k: v for k, v in result.items() if k not in {"status", "path"}},
        }
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except PermissionError as exc:
        logger.error("workspace.permission_denied", agent_id=body.agent_id, source_path=body.source_path, error=str(exc))
        raise HTTPException(status_code=403, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except (OSError,) as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/shared/search")
async def shared_search(body: SearchRequest, auth: dict = Depends(require_internal_auth)):
    """Search file names and/or contents across a shared workspace."""
    await check_access(body.agent_id, "shared", body.workspace_id)
    try:
        result = search_workspace(
            "shared", body.workspace_id, settings.workspace_base_path, body.query,
            relative_path=body.path,
            search_names=body.search_names,
            search_content=body.search_content,
            case_sensitive=body.case_sensitive,
            max_results=body.max_results,
        )
        return {"status": "ok", **result}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except PermissionError as exc:
        logger.error("workspace.permission_denied", agent_id=body.agent_id, path=body.path, error=str(exc))
        raise HTTPException(status_code=403, detail=str(exc))
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ─── Git endpoints ────────────────────────────────────────────────

@app.post("/git/clone")
async def git_clone_endpoint(body: GitCloneRequest, auth: dict = Depends(require_internal_auth)):
    await check_access(body.agent_id, body.scope, body.effective_scope_id)
    try:
        result = await git_clone(
            body.scope, body.effective_scope_id, settings.workspace_base_path,
            body.path, body.url, body.branch,
        )
        return result
    except GitInvalidOperationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except GitAuthError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except GitRemoteError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except Exception as exc:
        logger.error("workspace.git_clone_failed", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/git/status")
async def git_status_endpoint(body: GitStatusRequest, auth: dict = Depends(require_internal_auth)):
    await check_access(body.agent_id, body.scope, body.effective_scope_id)
    try:
        result = await git_status(
            body.scope, body.effective_scope_id, settings.workspace_base_path, body.path,
        )
        return result
    except GitNotRepoError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except GitRemoteError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except Exception as exc:
        logger.error("workspace.git_status_failed", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/git/commit")
async def git_commit_endpoint(body: GitCommitRequest, auth: dict = Depends(require_internal_auth)):
    await check_access(body.agent_id, body.scope, body.effective_scope_id)
    try:
        result = await git_commit(
            body.scope, body.effective_scope_id, settings.workspace_base_path,
            body.path, body.message, body.files,
        )
        return result
    except GitNotRepoError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except GitInvalidOperationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except Exception as exc:
        logger.error("workspace.git_commit_failed", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/git/push")
async def git_push_endpoint(body: GitPushRequest, auth: dict = Depends(require_internal_auth)):
    await check_access(body.agent_id, body.scope, body.effective_scope_id)
    try:
        result = await git_push(
            body.scope, body.effective_scope_id, settings.workspace_base_path,
            body.path, body.remote, body.branch,
        )
        return result
    except GitNotRepoError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except GitAuthError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except GitRemoteError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except Exception as exc:
        logger.error("workspace.git_push_failed", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/git/pull")
async def git_pull_endpoint(body: GitPullRequest, auth: dict = Depends(require_internal_auth)):
    await check_access(body.agent_id, body.scope, body.effective_scope_id)
    try:
        result = await git_pull(
            body.scope, body.effective_scope_id, settings.workspace_base_path,
            body.path, body.remote, body.branch,
        )
        return result
    except GitNotRepoError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except GitConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except GitAuthError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except GitRemoteError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except Exception as exc:
        logger.error("workspace.git_pull_failed", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/git/branch/list")
async def git_branch_list_endpoint(body: GitBranchListRequest, auth: dict = Depends(require_internal_auth)):
    await check_access(body.agent_id, body.scope, body.effective_scope_id)
    try:
        result = await git_branch_list(
            body.scope, body.effective_scope_id, settings.workspace_base_path, body.path,
        )
        return result
    except GitNotRepoError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except Exception as exc:
        logger.error("workspace.git_branch_list_failed", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/git/branch/create")
async def git_branch_create_endpoint(body: GitBranchCreateRequest, auth: dict = Depends(require_internal_auth)):
    await check_access(body.agent_id, body.scope, body.effective_scope_id)
    try:
        result = await git_branch_create(
            body.scope, body.effective_scope_id, settings.workspace_base_path,
            body.path, body.branch_name, body.checkout,
        )
        return result
    except GitNotRepoError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except GitInvalidOperationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except Exception as exc:
        logger.error("workspace.git_branch_create_failed", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/git/checkout")
async def git_checkout_endpoint(body: GitCheckoutRequest, auth: dict = Depends(require_internal_auth)):
    await check_access(body.agent_id, body.scope, body.effective_scope_id)
    try:
        result = await git_checkout(
            body.scope, body.effective_scope_id, settings.workspace_base_path,
            body.path, body.branch_name,
        )
        return result
    except GitNotRepoError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except GitInvalidOperationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except Exception as exc:
        logger.error("workspace.git_checkout_failed", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/git/log")
async def git_log_endpoint(body: GitLogRequest, auth: dict = Depends(require_internal_auth)):
    await check_access(body.agent_id, body.scope, body.effective_scope_id)
    try:
        result = await git_log(
            body.scope, body.effective_scope_id, settings.workspace_base_path,
            body.path, body.max_count, body.max_chars,
        )
        return result
    except GitNotRepoError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except Exception as exc:
        logger.error("workspace.git_log_failed", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


# ─── Package Manager endpoints ────────────────────────────────────

@app.post("/pip/install")
async def pip_install_endpoint(body: PipInstallRequest, auth: dict = Depends(require_internal_auth)):
    await check_access(body.agent_id, body.scope, body.effective_scope_id)
    try:
        result = await pip_install(
            body.scope, body.effective_scope_id, settings.workspace_base_path,
            body.packages, body.upgrade,
        )
        return result
    except PackageInvalidError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except PackageTimeoutError as exc:
        raise HTTPException(status_code=408, detail=str(exc))
    except PackageInstallError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except Exception as exc:
        logger.error("workspace.pip_install_failed", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/pip/list")
async def pip_list_endpoint(body: PipListRequest, auth: dict = Depends(require_internal_auth)):
    await check_access(body.agent_id, body.scope, body.effective_scope_id)
    try:
        result = await pip_list(
            body.scope, body.effective_scope_id, settings.workspace_base_path,
        )
        return result
    except PackageInstallError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except Exception as exc:
        logger.error("workspace.pip_list_failed", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))
