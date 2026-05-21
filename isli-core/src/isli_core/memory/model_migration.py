import structlog
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from isli_core.models import EpisodicMemory
from isli_core.memory.validation import MemoryValidator
from isli_core.memory.dimension_guard import VectorDimensionGuard

logger = structlog.get_logger()


class EmbeddingModelMigration:
    """Re-compute all embeddings when the embedding model changes."""

    @staticmethod
    async def run_migration(
        session: AsyncSession,
        old_model: str,
        new_model: str,
        client: Any | None = None,
    ) -> dict[str, Any]:
        from isli_keeper.ollama_client import OllamaClient

        logger.info("migration.start", old_model=old_model, new_model=new_model)
        new_dim = VectorDimensionGuard.get_dimension(new_model)

        result = await session.execute(
            select(EpisodicMemory).where(
                EpisodicMemory.embedding_model == old_model,
                EpisodicMemory.deleted_at.is_(None),
            )
        )
        memories = list(result.scalars().all())
        migrated = 0
        failed = 0

        if client is None:
            client = OllamaClient()

        for mem in memories:
            try:
                new_embedding = await client.embed(new_model, mem.summary)
                VectorDimensionGuard.assert_dimension(new_embedding, new_model)
                mem.embedding = new_embedding
                mem.embedding_model = new_model
                migrated += 1
                logger.info("migration.row", memory_id=mem.id, new_dim=len(new_embedding))
            except Exception as exc:
                failed += 1
                logger.error("migration.failed", memory_id=mem.id, error=str(exc))

        await session.flush()
        logger.info("migration.complete", migrated=migrated, failed=failed, total=len(memories))
        return {"migrated": migrated, "failed": failed, "total": len(memories)}
