"""Agent process manager initialization and state reconciliation on startup."""

import os

import structlog
from fastapi import FastAPI
from sqlalchemy import select, update

from isli_core.config import get_settings
from isli_core.db import get_db_session_manual
from isli_core.models import Agent
from isli_core.services.process_manager import AgentProcessManager

logger = structlog.get_logger()


async def initialize_process_manager(app: FastAPI):
    settings = get_settings()
    sdk_path = os.getenv("AGENT_SDK_PATH", "../isli-agent-sdk")
    app.state.process_manager = AgentProcessManager(
        sdk_path=sdk_path,
        core_url=settings.core_api_url,
    )

    # Reset stuck "starting" agents to "stopped"
    async with get_db_session_manual() as session:
        result = await session.execute(
            update(Agent)
            .where(Agent.status == "starting", Agent.deleted_at.is_(None))
            .values(status="stopped")
            .returning(Agent.id)
        )
        reset_ids = [row[0] for row in result.all()]
        await session.commit()
        if reset_ids:
            logger.info("startup.reset_stuck_starting_agents", agent_ids=reset_ids)

    # Reconcile with any Docker containers that survived a Core restart
    await app.state.process_manager.reconcile()

    # Restart any agents that were online before Core went down
    async with get_db_session_manual() as session:
        result = await session.execute(
            select(Agent).where(Agent.status == "online", Agent.deleted_at.is_(None))
        )
        online_agents = result.scalars().all()
        for agent in online_agents:
            if not app.state.process_manager.is_running(agent.id):
                logger.info("core.startup.restart_agent", agent_id=agent.id)
                try:
                    await app.state.process_manager.spawn(agent.id)
                except Exception as exc:
                    logger.error("core.startup.restart_failed", agent_id=agent.id, error=str(exc))
