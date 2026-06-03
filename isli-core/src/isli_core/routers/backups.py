"""Admin-only backup management router for ChromaDB."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from isli_core.auth import require_admin_auth
from isli_core.db import get_db
from isli_core.models import ChromaDbBackup
from isli_core.jobs.chromadb_backup_worker import ChromaBackupWorker

logger = structlog.get_logger()
router = APIRouter(prefix="/admin/backups", tags=["backups"])


class TriggerBackupOut(BaseModel):
    archive_path: str
    checksum: str
    status: str


class BackupListOut(BaseModel):
    backups: list[dict[str, Any]]


class RestoreRequest(BaseModel):
    backup_id: str


class RestoreOut(BaseModel):
    status: str
    runbook_url: str
    warning: str


@router.post("/chromadb/trigger", response_model=TriggerBackupOut)
async def trigger_backup(
    _admin: str = Depends(require_admin_auth),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Trigger an on-demand ChromaDB backup."""
    logger.info("backups.trigger_requested")
    await ChromaBackupWorker.run_once()

    # Return the most recent backup
    result = await db.execute(
        select(ChromaDbBackup).order_by(ChromaDbBackup.created_at.desc()).limit(1)
    )
    backup = result.scalar_one_or_none()
    if not backup:
        raise HTTPException(status_code=500, detail="Backup worker ran but no backup record was created.")

    return {
        "archive_path": backup.archive_path,
        "checksum": backup.checksum_sha256,
        "status": backup.status,
    }


@router.get("/chromadb", response_model=BackupListOut)
async def list_backups(
    limit: int = 20,
    _admin: str = Depends(require_admin_auth),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """List ChromaDB backup history."""
    result = await db.execute(
        select(ChromaDbBackup).order_by(ChromaDbBackup.created_at.desc()).limit(limit)
    )
    backups = result.scalars().all()
    return {
        "backups": [
            {
                "id": b.id,
                "archive_path": b.archive_path,
                "checksum_sha256": b.checksum_sha256,
                "size_bytes": b.size_bytes,
                "status": b.status,
                "created_at": b.created_at.isoformat() if b.created_at else None,
                "verified_at": b.verified_at.isoformat() if b.verified_at else None,
            }
            for b in backups
        ]
    }


@router.post("/chromadb/restore", response_model=RestoreOut)
async def restore_backup(
    request: RestoreRequest,
    _admin: str = Depends(require_admin_auth),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Queue a restore operation. Returns a runbook URL — the actual volume swap is manual."""
    result = await db.execute(
        select(ChromaDbBackup).where(ChromaDbBackup.id == request.backup_id)
    )
    backup = result.scalar_one_or_none()
    if not backup:
        raise HTTPException(status_code=404, detail=f"Backup '{request.backup_id}' not found.")

    logger.info("backups.restore_requested", backup_id=request.backup_id, path=backup.archive_path)
    return {
        "status": "queued",
        "runbook_url": "/docs/runbooks/backup-restore.md#chromadb-restore",
        "warning": (
            "Restore requires a manual volume swap. "
            "Stop Core and Keeper, replace /data/vectors with the archive contents, "
            "verify the checksum, then restart services."
        ),
    }
