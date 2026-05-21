import logging
from datetime import datetime, timedelta
from isli_core.db import db
from isli_core.models import Agent

logger = logging.getLogger(__name__)

class CheckAgentStalenessWorker:
    """
    Background worker that marks agents as 'unresponsive' if they haven't sent a heartbeat 
    in over 5 minutes.
    """
    HEARTBEAT_STALE_THRESHOLD_MINUTES = 5

    async def run(self):
        logger.info("worker.agent_staleness_watcher.start")
        try:
            threshold = datetime.utcnow() - timedelta(minutes=self.HEARTBEAT_STALE_THRESHOLD_MINUTES)
            
            # Find agents that are online but haven't heartbeated recently
            stale_agents = db.query(Agent).filter(
                Agent.deleted_at.is_(None),
                Agent.status == "online",
                Agent.last_heartbeat_at < threshold
            ).all()

            for agent in stale_agents:
                agent.status = "unresponsive"
                logger.warning(
                    "worker.agent_staleness_watcher.mark_unresponsive",
                    agent_id=agent.id,
                    last_heartbeat=agent.last_heartbeat_at
                )
            
            db.commit()
            logger.info("worker.agent_staleness_watcher.complete", count=len(stale_agents))
        except Exception as e:
            logger.error("worker.agent_staleness_watcher.error", error=str(e))
            db.rollback()
