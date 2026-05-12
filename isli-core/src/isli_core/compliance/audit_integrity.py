"""Audit trail cryptographic integrity via Merkle/chain hash."""

import hashlib
import json
import structlog
from typing import Any

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from isli_core.models import AuditLog

logger = structlog.get_logger()


class AuditIntegrity:
    """Merkle-style chain hash for tamper detection on audit_logs."""

    @staticmethod
    def _hash_row(row: AuditLog, previous_hash: str | None = None) -> str:
        """Compute SHA-256 hash of audit row content + previous hash."""
        payload = {
            "actor_type": row.actor_type,
            "actor_id": row.actor_id,
            "action": row.action,
            "target_type": row.target_type,
            "target_id": row.target_id,
            "payload": json.dumps(row.payload, sort_keys=True, default=str) if row.payload else "",
            "previous_hash": previous_hash or "genesis",
        }
        raw = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode()).hexdigest()

    @staticmethod
    async def compute_chain_hash(session: AsyncSession, since: Any | None = None) -> dict[str, Any]:
        """Compute chain hashes for all audit rows ordered by created_at."""
        stmt = select(AuditLog).order_by(AuditLog.created_at.asc())
        if since:
            stmt = stmt.where(AuditLog.created_at >= since)

        result = await session.execute(stmt)
        rows = list(result.scalars().all())

        previous_hash = None
        row_hashes = {}
        for row in rows:
            h = AuditIntegrity._hash_row(row, previous_hash)
            row_hashes[row.id] = h
            previous_hash = h

        merkle_root = previous_hash if previous_hash else ""
        logger.info("audit.chain_computed", rows=len(rows), merkle_root=merkle_root[:16])
        return {
            "merkle_root": merkle_root,
            "row_count": len(rows),
            "row_hashes": row_hashes,
        }

    @staticmethod
    async def verify_chain(session: AsyncSession, since: Any | None = None) -> dict[str, Any]:
        """Verify the integrity of the audit chain. Returns any tampered rows."""
        stmt = select(AuditLog).order_by(AuditLog.created_at.asc())
        if since:
            stmt = stmt.where(AuditLog.created_at >= since)

        result = await session.execute(stmt)
        rows = list(result.scalars().all())

        previous_hash = None
        tampered_rows: list[str] = []
        for row in rows:
            computed_hash = AuditIntegrity._hash_row(row, previous_hash)
            if row.chain_hash and row.chain_hash != computed_hash:
                tampered_rows.append(row.id)
            previous_hash = row.chain_hash or computed_hash

        merkle_root = previous_hash if previous_hash else ""
        return {
            "verified": len(tampered_rows) == 0,
            "row_count": len(rows),
            "merkle_root": merkle_root,
            "tampered_rows": tampered_rows,
        }

    @staticmethod
    async def store_checkpoint(session: AsyncSession, merkle_root: str) -> None:
        """Store a periodic checkpoint of the Merkle root."""
        logger.info("audit.checkpoint_stored", merkle_root=merkle_root[:16])
        # In production, this would write to a separate tamper-proof store
