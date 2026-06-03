"""Shared secret vault operations for Core."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from structlog import get_logger

from isli_core.models import Secret
from isli_core.compliance.encryption import PIIEncryption

logger = get_logger()


async def create_or_update_secret(
    session: AsyncSession,
    agent_id: str,
    name: str,
    value: str,
    description: str | None = None,
) -> Secret:
    """Create or overwrite a secret for an agent."""
    encrypted = PIIEncryption.encrypt_field(value, context=f"secret:{agent_id}:{name}")

    result = await session.execute(
        select(Secret).where(Secret.agent_id == agent_id, Secret.name == name)
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.value_encrypted = encrypted
        existing.description = description
        await session.flush()
        logger.info("secret.updated", agent_id=agent_id, name=name)
        return existing

    secret = Secret(
        agent_id=agent_id,
        name=name,
        value_encrypted=encrypted,
        description=description,
    )
    session.add(secret)
    await session.flush()
    logger.info("secret.created", agent_id=agent_id, name=name)
    return secret


async def get_secret_value(
    session: AsyncSession,
    agent_id: str,
    name: str,
) -> str | None:
    """Retrieve decrypted secret value. Returns None if not found."""
    result = await session.execute(
        select(Secret).where(Secret.agent_id == agent_id, Secret.name == name)
    )
    secret = result.scalar_one_or_none()
    if not secret:
        return None
    return PIIEncryption.decrypt_field(secret.value_encrypted)


async def list_secrets(
    session: AsyncSession,
    agent_id: str,
) -> list[dict[str, Any]]:
    """List secret names and metadata for an agent (values never exposed)."""
    result = await session.execute(
        select(Secret).where(Secret.agent_id == agent_id).order_by(Secret.name)
    )
    secrets = result.scalars().all()
    return [
        {
            "name": s.name,
            "description": s.description,
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "updated_at": s.updated_at.isoformat() if s.updated_at else None,
        }
        for s in secrets
    ]


async def delete_secret(
    session: AsyncSession,
    agent_id: str,
    name: str,
) -> bool:
    """Delete a secret. Returns True if deleted, False if not found."""
    result = await session.execute(
        select(Secret).where(Secret.agent_id == agent_id, Secret.name == name)
    )
    secret = result.scalar_one_or_none()
    if not secret:
        return False
    await session.delete(secret)
    await session.flush()
    logger.info("secret.deleted", agent_id=agent_id, name=name)
    return True
