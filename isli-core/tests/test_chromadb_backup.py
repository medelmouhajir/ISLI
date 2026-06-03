"""Tests for ChromaDB backup worker and admin router."""

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from isli_core.models import ChromaDbBackup
from isli_core.jobs.chromadb_backup_worker import ChromaBackupWorker, _sha256_file, _run_backup


# ---------------------------------------------------------------------------
# Worker tests
# ---------------------------------------------------------------------------

class TestChromaBackupWorker:
    @pytest.mark.asyncio
    async def test_run_once_creates_backup_and_record(self, db_session):
        # Ensure backup dir exists inside test environment
        backup_dir = Path("/tmp/test_chromadb_backups")
        backup_dir.mkdir(parents=True, exist_ok=True)

        mock_redis = AsyncMock()
        mock_redis.set.return_value = True  # lock acquired
        mock_redis.delete.return_value = True

        with patch("isli_core.jobs.chromadb_backup_worker.get_redis", return_value=mock_redis):
            with patch("isli_core.jobs.chromadb_backup_worker.BACKUP_DIR", str(backup_dir)):
                with patch("isli_core.jobs.chromadb_backup_worker.CHROMA_DATA_DIR", "/tmp/test_chromadb_data"):
                    # Create fake chroma data dir
                    chroma_dir = Path("/tmp/test_chromadb_data")
                    chroma_dir.mkdir(parents=True, exist_ok=True)
                    (chroma_dir / "chroma.sqlite3").write_text("fake db")

                    await ChromaBackupWorker.run_once()

        # Verify DB record was created
        result = await db_session.execute(
            select(ChromaDbBackup).order_by(ChromaDbBackup.created_at.desc())
        )
        backup = result.scalar_one_or_none()
        assert backup is not None
        assert backup.status == "verified"
        assert backup.checksum_sha256 is not None
        assert backup.size_bytes > 0
        assert Path(backup.archive_path).exists()

        # Cleanup
        Path(backup.archive_path).unlink(missing_ok=True)
        Path(backup.archive_path + ".sha256").unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_run_once_skips_when_lock_not_acquired(self, db_session):
        mock_redis = AsyncMock()
        mock_redis.set.return_value = None  # lock not acquired

        with patch("isli_core.jobs.chromadb_backup_worker.get_redis", return_value=mock_redis):
            await ChromaBackupWorker.run_once()

        mock_redis.set.assert_awaited_once()
        mock_redis.delete.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_run_once_skips_when_db_not_ready(self):
        mock_redis = AsyncMock()
        mock_redis.set.return_value = True

        with patch("isli_core.jobs.chromadb_backup_worker.get_redis", return_value=mock_redis):
            with patch("isli_core.jobs.chromadb_backup_worker.db_module.async_session", None):
                await ChromaBackupWorker.run_once()

        mock_redis.delete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_run_once_enforces_retention(self, db_session):
        # Insert an old backup record
        old_backup = ChromaDbBackup(
            archive_path="/tmp/test_chromadb_backups/chroma_old.tar.gz",
            checksum_sha256="a" * 64,
            size_bytes=100,
            status="verified",
            created_at=datetime.now(timezone.utc) - timedelta(days=30),
            verified_at=datetime.now(timezone.utc) - timedelta(days=30),
        )
        db_session.add(old_backup)
        await db_session.commit()

        # Create the fake archive file so retention tries to delete it
        old_path = Path(old_backup.archive_path)
        old_path.parent.mkdir(parents=True, exist_ok=True)
        old_path.write_text("old backup")
        sidecar = old_path.with_suffix(old_path.suffix + ".sha256")
        sidecar.write_text("checksum")

        mock_redis = AsyncMock()
        mock_redis.set.return_value = True
        mock_redis.delete.return_value = True

        backup_dir = Path("/tmp/test_chromadb_backups_retention")
        backup_dir.mkdir(parents=True, exist_ok=True)
        chroma_dir = Path("/tmp/test_chromadb_data_retention")
        chroma_dir.mkdir(parents=True, exist_ok=True)
        (chroma_dir / "chroma.sqlite3").write_text("fake db")

        with patch("isli_core.jobs.chromadb_backup_worker.get_redis", return_value=mock_redis):
            with patch("isli_core.jobs.chromadb_backup_worker.BACKUP_DIR", str(backup_dir)):
                with patch("isli_core.jobs.chromadb_backup_worker.CHROMA_DATA_DIR", str(chroma_dir)):
                    await ChromaBackupWorker.run_once()

        # Verify old backup was deleted from DB
        result = await db_session.execute(
            select(ChromaDbBackup).where(ChromaDbBackup.id == old_backup.id)
        )
        assert result.scalar_one_or_none() is None
        assert not old_path.exists()

    def test_sha256_file(self, tmp_path):
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello world")
        checksum = _sha256_file(test_file)
        assert len(checksum) == 64
        assert checksum == "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"

    def test_run_backup_creates_archive(self, tmp_path):
        data_dir = tmp_path / "chroma_data"
        data_dir.mkdir()
        (data_dir / "db.sqlite3").write_text("fake")
        archive = tmp_path / "backup.tar.gz"

        checksum, verified = _run_backup(str(data_dir), archive)
        assert archive.exists()
        assert verified is True
        assert len(checksum) == 64
        sidecar = archive.with_suffix(archive.suffix + ".sha256")
        assert sidecar.exists()

    def test_run_backup_raises_when_data_dir_missing(self, tmp_path):
        archive = tmp_path / "backup.tar.gz"
        with pytest.raises(FileNotFoundError):
            _run_backup("/nonexistent/path", archive)


# ---------------------------------------------------------------------------
# Router tests
# ---------------------------------------------------------------------------

class TestBackupsRouter:
    @pytest.mark.asyncio
    async def test_trigger_backup(self, client: AsyncClient, db_session):
        with patch.object(ChromaBackupWorker, "run_once", return_value=None):
            # Seed a fake backup record so trigger can find it
            fake_backup = ChromaDbBackup(
                archive_path="/tmp/test_chromadb_backups/chroma_trigger.tar.gz",
                checksum_sha256="b" * 64,
                size_bytes=200,
                status="verified",
            )
            db_session.add(fake_backup)
            await db_session.commit()

            resp = await client.post("/v1/admin/backups/chromadb/trigger")
            assert resp.status_code == 200
            data = resp.json()
            assert data["archive_path"] == fake_backup.archive_path
            assert data["checksum"] == fake_backup.checksum_sha256
            assert data["status"] == "verified"

    @pytest.mark.asyncio
    async def test_trigger_backup_no_record(self, client: AsyncClient, db_session):
        # Ensure no backup records exist
        from sqlalchemy import delete
        await db_session.execute(delete(ChromaDbBackup))
        await db_session.commit()

        with patch.object(ChromaBackupWorker, "run_once", return_value=None):
            resp = await client.post("/v1/admin/backups/chromadb/trigger")
            assert resp.status_code == 500
            assert "no backup record" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_list_backups(self, client: AsyncClient, db_session):
        fake_backup = ChromaDbBackup(
            archive_path="/tmp/test_chromadb_backups/chroma_list.tar.gz",
            checksum_sha256="c" * 64,
            size_bytes=300,
            status="verified",
        )
        db_session.add(fake_backup)
        await db_session.commit()

        resp = await client.get("/v1/admin/backups/chromadb")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["backups"]) >= 1
        assert data["backups"][0]["archive_path"] == fake_backup.archive_path

    @pytest.mark.asyncio
    async def test_restore_backup(self, client: AsyncClient, db_session):
        fake_backup = ChromaDbBackup(
            archive_path="/tmp/test_chromadb_backups/chroma_restore.tar.gz",
            checksum_sha256="d" * 64,
            size_bytes=400,
            status="verified",
        )
        db_session.add(fake_backup)
        await db_session.commit()

        resp = await client.post("/v1/admin/backups/chromadb/restore", json={"backup_id": fake_backup.id})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "queued"
        assert "runbook_url" in data
        assert "manual" in data["warning"].lower()

    @pytest.mark.asyncio
    async def test_restore_backup_not_found(self, client: AsyncClient):
        resp = await client.post("/v1/admin/backups/chromadb/restore", json={"backup_id": "nonexistent-id"})
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()
