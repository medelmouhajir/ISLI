from sqlalchemy import select, func
from isli_core.models import Session
from datetime import datetime, timezone

async def get_active_sessions_count(session: "AsyncSession") -> int:
    """Returns count of sessions where status is not 'archived' or 'ready'."""
    # Assuming 'active' sessions are those not in 'ready' or 'archived' state,
    # or perhaps checking activity within a certain window.
    # Given the status field in the Session model:
    stmt = select(func.count()).select_from(Session).where(
        Session.status.notin_(["ready", "archived", "closed"])
    )
    result = await session.execute(stmt)
    return result.scalar() or 0
