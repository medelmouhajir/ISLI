from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from isli_core.models import Task

MAX_DEPTH = 3
APPROVAL_DEPTH = 2


class DepthLimitError(HTTPException):
    def __init__(self, depth: int):
        super().__init__(
            status_code=403,
            detail=f"Delegation depth limit ({MAX_DEPTH}) exceeded at depth {depth}. Human approval required.",
        )


class CycleDetectedError(HTTPException):
    def __init__(self, chain: list[str]):
        super().__init__(
            status_code=400,
            detail=f"Delegation cycle detected: {' -> '.join(chain)}",
        )


async def get_task_chain(session: AsyncSession, parent_task_id: str | None) -> list[str]:
    chain = []
    current_id = parent_task_id
    visited = set()
    while current_id is not None and current_id not in visited:
        visited.add(current_id)
        chain.append(current_id)
        result = await session.execute(
            select(Task.parent_task_id).where(Task.id == current_id, Task.deleted_at.is_(None))
        )
        row = result.scalar_one_or_none()
        current_id = row
    return chain


async def validate_delegation(
    session: AsyncSession, parent_task_id: str | None, proposed_agent_id: str | None
) -> int:
    chain = await get_task_chain(session, parent_task_id)
    depth = len(chain)

    if depth >= MAX_DEPTH:
        raise DepthLimitError(depth)

    # Cycle detection: check if any ancestor has the same agent assignment
    if proposed_agent_id is not None and parent_task_id is not None:
        result = await session.execute(
            select(Task.agent_id).where(Task.id == parent_task_id, Task.deleted_at.is_(None))
        )
        parent_agent = result.scalar_one_or_none()
        # Detect A -> B -> A delegation loops by checking agent_id recurrence
        ancestor_agents = set()
        current_id = parent_task_id
        while current_id is not None:
            result = await session.execute(
                select(Task.agent_id, Task.parent_task_id)
                .where(Task.id == current_id, Task.deleted_at.is_(None))
            )
            row = result.one_or_none()
            if row is None:
                break
            agent_id, next_parent = row
            if agent_id == proposed_agent_id and agent_id is not None:
                raise CycleDetectedError([agent_id, proposed_agent_id])
            ancestor_agents.add(agent_id)
            current_id = next_parent

    return depth


async def needs_human_approval(depth: int) -> bool:
    return depth >= APPROVAL_DEPTH
