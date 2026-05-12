import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from isli_core.models import ChannelMessage

logger = structlog.get_logger()


class MessageOrdering:
    """Monotonic sequence_number per session for message ordering guarantees."""

    @staticmethod
    async def next_sequence(session: AsyncSession, session_id: str) -> int:
        from sqlalchemy import func

        result = await session.execute(
            select(func.coalesce(func.max(ChannelMessage.sequence_number), 0)).where(
                ChannelMessage.session_id == session_id
            )
        )
        seq = result.scalar_one()
        return seq + 1

    @staticmethod
    async def record_inbound(
        session: AsyncSession,
        session_id: str,
        channel: str,
        content: str,
        raw_payload: dict | None = None,
    ) -> ChannelMessage:
        seq = await MessageOrdering.next_sequence(session, session_id)
        msg = ChannelMessage(
            session_id=session_id,
            sequence_number=seq,
            channel=channel,
            direction="inbound",
            content=content,
            raw_payload=raw_payload,
        )
        session.add(msg)
        await session.flush()
        logger.info("ordering.inbound", session_id=session_id, seq=seq, channel=channel)
        return msg

    @staticmethod
    async def record_outbound(
        session: AsyncSession,
        session_id: str,
        channel: str,
        content: str,
        raw_payload: dict | None = None,
    ) -> ChannelMessage:
        seq = await MessageOrdering.next_sequence(session, session_id)
        msg = ChannelMessage(
            session_id=session_id,
            sequence_number=seq,
            channel=channel,
            direction="outbound",
            content=content,
            raw_payload=raw_payload,
        )
        session.add(msg)
        await session.flush()
        logger.info("ordering.outbound", session_id=session_id, seq=seq, channel=channel)
        return msg

    @staticmethod
    async def get_ordered_messages(
        session: AsyncSession, session_id: str, after_seq: int = 0
    ) -> list[ChannelMessage]:
        result = await session.execute(
            select(ChannelMessage)
            .where(
                ChannelMessage.session_id == session_id,
                ChannelMessage.sequence_number > after_seq,
            )
            .order_by(ChannelMessage.sequence_number.asc())
        )
        return list(result.scalars().all())
