import structlog
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()


class TablePartitioning:
    """Monthly PostgreSQL partitioning for audit_logs and old tasks."""

    @staticmethod
    async def ensure_partitioned(session: AsyncSession, table: str = "audit_logs") -> None:
        """Create monthly partitions if they don't exist."""
        now = datetime.now(timezone.utc)
        year_month = now.strftime("%Y_%m")
        partition_name = f"{table}_{year_month}"
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if now.month == 12:
            end = start.replace(year=start.year + 1, month=1)
        else:
            end = start.replace(month=start.month + 1)

        # Check if partition exists
        check = await session.execute(
            text(
                "SELECT 1 FROM pg_class WHERE relname = :name"
            ),
            {"name": partition_name},
        )
        if check.scalar():
            logger.info("partition.exists", table=table, partition=partition_name)
            return

        await session.execute(
            text(
                f"CREATE TABLE {partition_name} PARTITION OF {table} "
                f"FOR VALUES FROM (:start) TO (:end)"
            ),
            {"start": start.isoformat(), "end": end.isoformat()},
        )
        logger.info("partition.created", table=table, partition=partition_name, start=start.isoformat())

    @staticmethod
    async def list_partitions(session: AsyncSession, table: str = "audit_logs") -> list[str]:
        result = await session.execute(
            text(
                "SELECT relname FROM pg_class WHERE relname LIKE :pattern ORDER BY relname"
            ),
            {"pattern": f"{table}_%"},
        )
        return [row[0] for row in result.all()]

    @staticmethod
    async def detach_old_partitions(
        session: AsyncSession, table: str = "audit_logs", older_than_months: int = 12
    ) -> list[str]:
        now = datetime.now(timezone.utc)
        cutoff = now.replace(year=now.year - (older_than_months // 12), month=((now.month - older_than_months % 12) % 12) or 12)
        partitions = await TablePartitioning.list_partitions(session, table)
        detached = []
        for part in partitions:
            # Parse year_month from partition name: audit_logs_2025_01
            try:
                _, year, month = part.rsplit("_", 2)
                part_date = datetime(int(year), int(month), 1, tzinfo=timezone.utc)
                if part_date < cutoff:
                    await session.execute(
                        text(f"ALTER TABLE {table} DETACH PARTITION {part}")
                    )
                    detached.append(part)
                    logger.info("partition.detached", partition=part)
            except ValueError:
                continue
        return detached
