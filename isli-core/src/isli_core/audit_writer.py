"""Write tamper-evident audit log rows with chain hashing."""

import hashlib
import json
import structlog
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from isli_core.models import AuditLog

logger = structlog.get_logger()


class AuditWriter:
    """Insert audit rows with SHA-256 chain hashes for tamper detection."""

    @staticmethod
    async def write(
        session: AsyncSession,
        actor_type: str,
        actor_id: str,
        action: str,
        target_type: str,
        target_id: str,
        payload: dict[str, Any] | None = None,
    ) -> AuditLog:
        # Fetch the previous chain hash (globally latest)
        result = await session.execute(
            select(AuditLog.chain_hash)
            .order_by(AuditLog.created_at.desc())
            .limit(1)
        )
        previous_hash = result.scalar_one_or_none()

        row_data = {
            "actor_type": actor_type,
            "actor_id": actor_id,
            "action": action,
            "target_type": target_type,
            "target_id": target_id,
            "payload": json.dumps(payload, sort_keys=True, default=str) if payload else "",
            "previous_hash": previous_hash or "genesis",
        }
        raw = json.dumps(row_data, sort_keys=True)
        chain_hash = hashlib.sha256(raw.encode()).hexdigest()

        log = AuditLog(
            actor_type=actor_type,
            actor_id=actor_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            payload=payload,
            chain_hash=chain_hash,
        )
        session.add(log)
        await session.flush()
        logger.info("audit.written", actor=actor_id, action=action, target=target_id)
        return log
