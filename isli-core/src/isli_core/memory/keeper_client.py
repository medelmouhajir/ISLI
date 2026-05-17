import httpx
import structlog
from typing import Any
from ..config import get_settings
from isli_core.auth import create_internal_token

logger = structlog.get_logger()

class KeeperClient:
    """Client for calling ISLI Keeper services."""
    
    @staticmethod
    async def get_context_injection(agent_id: str, task_description: str | None = None, session_id: str | None = None) -> str | None:
        settings = get_settings()
        url = f"{settings.keeper_url}/context/inject"
        
        payload = {
            "agent_id": agent_id,
            "task_description": task_description,
            "session_id": session_id
        }
        
        try:
            token = create_internal_token("core-api", scopes=["keeper:context"], expires_minutes=1)
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json=payload, headers={"X-Internal-Auth": token})
                resp.raise_for_status()
                data = resp.json()
                return data.get("context_summary")
        except Exception as exc:
            logger.error("keeper.context_inject_failed", agent_id=agent_id, error=str(exc))
            return None

    @staticmethod
    async def validate_heartbeat(agent_id: str, heartbeat_at: str) -> bool:
        settings = get_settings()
        url = f"{settings.keeper_url}/heartbeat/validate"
        try:
            token = create_internal_token("core-api", scopes=["keeper:heartbeat"], expires_minutes=1)
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(
                    url, 
                    json={"agent_id": agent_id, "heartbeat_at": heartbeat_at},
                    headers={"X-Internal-Auth": token}
                )
                resp.raise_for_status()
                return resp.json().get("is_valid", True)
        except Exception as exc:
            logger.error("keeper.heartbeat_validate_failed", agent_id=agent_id, error=str(exc))
            return True

    @staticmethod
    async def scrub_pii(text: str) -> dict[str, Any]:
        settings = get_settings()
        url = f"{settings.keeper_url}/pii/scrub"
        try:
            token = create_internal_token("core-api", scopes=["keeper:scrub"], expires_minutes=1)
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json={"text": text}, headers={"X-Internal-Auth": token})
                resp.raise_for_status()
                return resp.json()
        except Exception as exc:
            logger.error("keeper.pii_scrub_failed", error=str(exc))
            return {"scrubbed_text": text, "mapping": {}}

    @staticmethod
    async def unscrub_pii(text: str, mapping: dict[str, str]) -> str:
        settings = get_settings()
        url = f"{settings.keeper_url}/pii/unscrub"
        try:
            token = create_internal_token("core-api", scopes=["keeper:scrub"], expires_minutes=1)
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(url, json={"text": text, "mapping": mapping}, headers={"X-Internal-Auth": token})
                resp.raise_for_status()
                return resp.json().get("text", text)
        except Exception as exc:
            logger.error("keeper.pii_unscrub_failed", error=str(exc))
            return text

    @staticmethod
    async def clean_skill_output(raw_data: str, goal: str) -> str:
        settings = get_settings()
        url = f"{settings.keeper_url}/skill/clean"
        try:
            token = create_internal_token("core-api", scopes=["keeper:clean"], expires_minutes=1)
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    url, 
                    json={"raw_data": raw_data, "extraction_goal": goal},
                    headers={"X-Internal-Auth": token}
                )
                resp.raise_for_status()
                return resp.json().get("cleaned_data", raw_data)
        except Exception as exc:
            logger.error("keeper.skill_clean_failed", error=str(exc))
            return raw_data

    @staticmethod
    async def update_journal(session_id: str, old_journal: str | None, recent_messages: list[dict[str, Any]]) -> str | None:
        settings = get_settings()
        url = f"{settings.keeper_url}/journal/update"
        
        payload = {
            "session_id": session_id,
            "old_journal": old_journal,
            "recent_messages": recent_messages
        }
        
        try:
            token = create_internal_token("core-api", scopes=["keeper:journal"], expires_minutes=1)
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(url, json=payload, headers={"X-Internal-Auth": token})
                resp.raise_for_status()
                data = resp.json()
                return data.get("journal")
        except Exception as exc:
            logger.error("keeper.journal_update_failed", session_id=session_id, error=str(exc))
            return None

    @staticmethod
    async def verify_logic(text: str, context: str | None = None) -> dict[str, Any]:
        settings = get_settings()
        url = f"{settings.keeper_url}/verify/logic"
        try:
            token = create_internal_token("core-api", scopes=["keeper:verify"], expires_minutes=1)
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    url, 
                    json={"text": text, "context": context},
                    headers={"X-Internal-Auth": token}
                )
                resp.raise_for_status()
                return resp.json()
        except Exception as exc:
            logger.error("keeper.verify_logic_failed", error=str(exc))
            return {"is_valid": True, "reason": "Judge unavailable"}
