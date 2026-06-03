"""Background worker for scheduled ChromaDB backup, verification, and retention."""

import asyncio
import hashlib
import os
import tarfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

import structlog
from sqlalchemy import select, delete

import isli_core.db as db_module
from isli_core.redis_client import get_redis
from isli_core.dynamic_config import get_setting
from isli_core.models import ChromaDbBackup

logger = structlog.get_logger()

CRON_LOCK_KEY = "cron:chromadb_backup"
CRON_LOCK_TTL_SECONDS = 1800  # 30 min
DEFAULT_INTERVAL_SECONDS = 21600  # 6 hours
DEFAULT_RETENTION_DAYS = 7
CHROMA_DATA_DIR = os.getenv("CHROMA_DATA_DIR", "/data/vectors")
BACKUP_DIR = os.getenv("CHROMA_BACKUP_DIR", "/backups/chromadb")


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _create_tarball(data_dir: str, output: Path) -> None:
    src = Path(data_dir)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(output, "w:gz") as tar:
        tar.add(src, arcname="chroma_data")


def _run_backup(data_dir: str, archive_path: Path) -> tuple[str, bool]:
    """Create tarball, compute checksum, write sidecar, verify integrity.

    Returns (checksum, verified).
    """
    if not Path(data_dir).exists():
        raise FileNotFoundError(f"Data directory not found: {data_dir}")

    _create_tarball(data_dir, archive_path)
    checksum = _sha256_file(archive_path)
    sidecar = archive_path.with_suffix(archive_path.suffix + ".sha256")
    sidecar.write_text(f"{checksum}  {archive_path.name}\n")

    # Verify integrity by re-computing checksum
    re_checksum = _sha256_file(archive_path)
    verified = re_checksum == checksum
    if not verified:
        raise RuntimeError(f"Integrity check failed! Expected {checksum}, got {re_checksum}")

    return checksum, verified


class ChromaBackupWorker:
    """Run ChromaDB backup on a schedule with integrity verification and retention."""

    @staticmethod
    async def run_once() -> None:
        redis = await get_redis()
        acquired = await redis.set(CRON_LOCK_KEY, "1", nx=True, ex=CRON_LOCK_TTL_SECONDS)
        if not acquired:
            logger.debug("chromadb_backup.lock_not_acquired")
            return

        try:
            if db_module.async_session is None:
                logger.warning("chromadb_backup.db_not_ready")
                return

            async with db_module.async_session() as session:
                interval = await get_setting(
                    session, "chromadb_backup_interval_seconds", scope="general", default=DEFAULT_INTERVAL_SECONDS
                )
                retention_days = await get_setting(
                    session, "chromadb_backup_retention_days", scope="general", default=DEFAULT_RETENTION_DAYS
                )
                await session.commit()

            # Run backup in thread so tar doesn't block the event loop
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            archive_name = f"chroma_{timestamp}.tar.gz"
            archive_path = Path(BACKUP_DIR) / archive_name
            archive_path.parent.mkdir(parents=True, exist_ok=True)

            logger.info("chromadb_backup.starting", archive=str(archive_path))

            loop = asyncio.get_event_loop()
            checksum, verified = await loop.run_in_executor(
                None,
                _run_backup,
                CHROMA_DATA_DIR,
                archive_path,
            )

            if not verified:
                logger.error("chromadb_backup.verify_failed", archive=str(archive_path))
                return

            if not archive_path.exists():
                logger.error("chromadb_backup.archive_missing", path=str(archive_path))
                return

            size_bytes = archive_path.stat().st_size

            async with db_module.async_session() as session:
                backup = ChromaDbBackup(
                    archive_path=str(archive_path),
                    checksum_sha256=checksum,
                    size_bytes=size_bytes,
                    status="verified",
                    verified_at=datetime.now(timezone.utc),
                )
                session.add(backup)

                # Enforce retention
                cutoff = datetime.now(timezone.utc) - timedelta(days=int(retention_days))
                result = await session.execute(
                    select(ChromaDbBackup).where(
                        ChromaDbBackup.created_at < cutoff
                    )
                )
                old_backups = result.scalars().all()
                deleted_count = 0
                for old in old_backups:
                    try:
                        p = Path(old.archive_path)
                        if p.exists():
                            p.unlink()
                            sidecar = p.with_suffix(p.suffix + ".sha256")
                            if sidecar.exists():
                                sidecar.unlink()
                        await session.delete(old)
                        deleted_count += 1
                    except Exception as exc:
                        logger.warning("chromadb_backup.retention_delete_failed", path=old.archive_path, error=str(exc))

                await session.commit()
                logger.info(
                    "chromadb_backup.completed",
                    archive=str(archive_path),
                    checksum=checksum,
                    size_bytes=size_bytes,
                    retention_deleted=deleted_count,
                )

        except Exception as exc:
            logger.error("chromadb_backup.error", error=str(exc))
        finally:
            await redis.delete(CRON_LOCK_KEY)

    @staticmethod
    async def loop() -> None:
        logger.info("chromadb_backup.loop_started", interval_seconds=DEFAULT_INTERVAL_SECONDS)
        while True:
            try:
                await ChromaBackupWorker.run_once()
            except Exception as exc:
                logger.error("chromadb_backup.loop_error", error=str(exc))
            await asyncio.sleep(DEFAULT_INTERVAL_SECONDS)
