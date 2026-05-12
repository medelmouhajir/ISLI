from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from isli_core.models import Agent


class BudgetExceededError(HTTPException):
    def __init__(self, agent_id: str, budget: int, used: int):
        super().__init__(
            status_code=429,
            detail=f"Agent {agent_id} token budget exceeded: {used}/{budget}",
        )


async def check_budget(session: AsyncSession, agent_id: str, input_tokens: int, output_tokens: int) -> None:
    result = await session.execute(
        select(Agent).where(Agent.id == agent_id, Agent.deleted_at.is_(None))
    )
    agent = result.scalar_one_or_none()
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")

    if agent.token_budget is None:
        return

    total = agent.token_used + input_tokens + output_tokens
    if total > agent.token_budget:
        await session.execute(
            update(Agent)
            .where(Agent.id == agent_id)
            .values(status="paused", status_reason=f"Budget exceeded: {total}/{agent.token_budget}")
        )
        await session.commit()
        raise BudgetExceededError(agent_id, agent.token_budget, total)


async def charge_tokens(session: AsyncSession, agent_id: str, input_tokens: int, output_tokens: int) -> None:
    await session.execute(
        update(Agent)
        .where(Agent.id == agent_id)
        .values(token_used=Agent.token_used + input_tokens + output_tokens)
    )
