import time
import json
from typing import Any

import httpx
import structlog

from isli_core.auth import create_internal_token
from isli_core.event_manager import EventManager

from ..config import get_settings

logger = structlog.get_logger()


class KeeperClient:
    """Client for calling ISLI Keeper services."""

    @staticmethod
    async def get_context_injection(
        agent_id: str,
        task_description: str | None = None,
        session_id: str | None = None,
        agent_name: str | None = None,
        agent_description: str | None = None,
        agent_persona: str | None = None,
        memory_similarity_threshold: float = 0.4,
    ) -> str | None:
        settings = get_settings()
        url = f"{settings.keeper_url}/context/inject"

        payload = {
            "agent_id": agent_id,
            "task_description": task_description,
            "session_id": session_id,
            "agent_name": agent_name,
            "agent_description": agent_description,
            "agent_persona": agent_persona,
            "memory_similarity_threshold": memory_similarity_threshold,
        }

        start = time.monotonic()
        try:
            token = create_internal_token("core-api", scopes=["keeper:context"], expires_minutes=1)
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(url, json=payload, headers={"X-Internal-Auth": token, "X-Agent-ID": agent_id})
                resp.raise_for_status()
                data = resp.json()
            latency = (time.monotonic() - start) * 1000
            await EventManager.emit("keeper:inference", {
                "agent_id": agent_id,
                "endpoint": "context/inject",
                "latency_ms": round(latency, 2),
                "status": "success",
                "prompt": task_description or "Injection request",
                "completion": data.get("context_summary"),
                "prompt_preview": (task_description or "Injection request")[:80],
                "completion_preview": (data.get("context_summary") or "")[:80],
            })
            return data.get("context_summary")
        except Exception as exc:
            latency = (time.monotonic() - start) * 1000
            await EventManager.emit("keeper:inference", {
                "agent_id": agent_id,
                "endpoint": "context/inject",
                "latency_ms": round(latency, 2),
                "status": "error",
                "error": str(exc),
                "prompt": task_description or "Injection request",
                "prompt_preview": (task_description or "Injection request")[:80],
            })
            logger.error(
                "keeper.context_inject_failed",
                agent_id=agent_id,
                error=str(exc),
                error_type=type(exc).__name__,
                exc_info=True,
            )
            return None

    @staticmethod
    async def embed(text: str, model: str = "nomic-embed-text", *, agent_id: str | None = None) -> list[float] | None:
        settings = get_settings()
        url = f"{settings.keeper_url}/embed"
        headers = {"X-Agent-ID": agent_id} if agent_id else {}
        start = time.monotonic()
        try:
            token = create_internal_token("core-api", scopes=["keeper:embed"], expires_minutes=1)
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(url, json={"input": text, "model": model, "agent_id": agent_id}, headers={"X-Internal-Auth": token, **headers})
                resp.raise_for_status()
                data = resp.json()
            latency = (time.monotonic() - start) * 1000
            await EventManager.emit("keeper:inference", {
                "agent_id": agent_id or "system",
                "endpoint": "embed",
                "latency_ms": round(latency, 2),
                "status": "success",
                "prompt": text,
                "prompt_preview": text[:80],
            })
            return data.get("embedding")
        except Exception as exc:
            latency = (time.monotonic() - start) * 1000
            await EventManager.emit("keeper:inference", {
                "agent_id": agent_id or "system",
                "endpoint": "embed",
                "latency_ms": round(latency, 2),
                "status": "error",
                "error": str(exc),
                "prompt": text,
                "prompt_preview": text[:80],
            })
            logger.error("keeper.embed_failed", error=str(exc), error_type=type(exc).__name__)
            return None

    @staticmethod
    async def validate_heartbeat(agent_id: str, heartbeat_at: str) -> bool:
        settings = get_settings()
        url = f"{settings.keeper_url}/heartbeat/validate"
        start = time.monotonic()
        try:
            token = create_internal_token("core-api", scopes=["keeper:heartbeat"], expires_minutes=1)
            async with httpx.AsyncClient(timeout=180.0) as client:
                resp = await client.post(
                    url,
                    json={"agent_id": agent_id, "heartbeat_at": heartbeat_at},
                    headers={"X-Internal-Auth": token, "X-Agent-ID": agent_id}
                )
                data = resp.json()
            latency = (time.monotonic() - start) * 1000
            await EventManager.emit("keeper:inference", {
                "agent_id": agent_id,
                "endpoint": "heartbeat/validate",
                "latency_ms": round(latency, 2),
                "status": "success",
                "prompt": f"Heartbeat at {heartbeat_at}",
                "completion": json.dumps(data),
                "prompt_preview": f"Heartbeat at {heartbeat_at}"[:80],
                "completion_preview": json.dumps(data)[:80],
            })
            return data.get("is_valid", True)
        except Exception as exc:
            latency = (time.monotonic() - start) * 1000
            await EventManager.emit("keeper:inference", {
                "agent_id": agent_id,
                "endpoint": "heartbeat/validate",
                "latency_ms": round(latency, 2),
                "status": "error",
                "error": str(exc),
                "prompt": f"Heartbeat at {heartbeat_at}",
                "prompt_preview": f"Heartbeat at {heartbeat_at}"[:80],
            })
            logger.error(
                "keeper.heartbeat_validate_failed",
                agent_id=agent_id,
                error=str(exc),
                error_type=type(exc).__name__,
                exc_info=True,
            )
            return True

    @staticmethod
    async def scrub_pii(text: str, *, agent_id: str | None = None) -> dict[str, Any]:
        settings = get_settings()
        url = f"{settings.keeper_url}/pii/scrub"
        headers = {"X-Agent-ID": agent_id} if agent_id else {}
        start = time.monotonic()
        try:
            token = create_internal_token("core-api", scopes=["keeper:scrub"], expires_minutes=1)
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json={"text": text, "agent_id": agent_id}, headers={"X-Internal-Auth": token, **headers})
                resp.raise_for_status()
                data = resp.json()
            latency = (time.monotonic() - start) * 1000
            await EventManager.emit("keeper:inference", {
                "agent_id": agent_id or "system",
                "endpoint": "pii/scrub",
                "latency_ms": round(latency, 2),
                "status": "success",
                "prompt": text,
                "completion": data.get("scrubbed_text"),
                "prompt_preview": text[:80],
                "completion_preview": (data.get("scrubbed_text") or "")[:80],
            })
            return data
        except Exception as exc:
            latency = (time.monotonic() - start) * 1000
            await EventManager.emit("keeper:inference", {
                "agent_id": agent_id or "system",
                "endpoint": "pii/scrub",
                "latency_ms": round(latency, 2),
                "status": "error",
                "error": str(exc),
                "prompt": text,
                "prompt_preview": text[:80],
            })
            logger.error(
                "keeper.pii_scrub_failed",
                error=str(exc),
                error_type=type(exc).__name__,
                exc_info=True,
            )
            return {"scrubbed_text": text, "mapping": {}}

    @staticmethod
    async def unscrub_pii(text: str, mapping: dict[str, str], *, agent_id: str | None = None) -> str:
        settings = get_settings()
        url = f"{settings.keeper_url}/pii/unscrub"
        headers = {"X-Agent-ID": agent_id} if agent_id else {}
        start = time.monotonic()
        try:
            token = create_internal_token("core-api", scopes=["keeper:scrub"], expires_minutes=1)
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(url, json={"text": text, "mapping": mapping, "agent_id": agent_id}, headers={"X-Internal-Auth": token, **headers})
                resp.raise_for_status()
                data = resp.json()
            latency = (time.monotonic() - start) * 1000
            await EventManager.emit("keeper:inference", {
                "agent_id": agent_id or "system",
                "endpoint": "pii/unscrub",
                "latency_ms": round(latency, 2),
                "status": "success",
                "prompt": text,
                "completion": data.get("text"),
                "prompt_preview": text[:80],
                "completion_preview": (data.get("text") or "")[:80],
            })
            return data.get("text", text)
        except Exception as exc:
            latency = (time.monotonic() - start) * 1000
            await EventManager.emit("keeper:inference", {
                "agent_id": agent_id or "system",
                "endpoint": "pii/unscrub",
                "latency_ms": round(latency, 2),
                "status": "error",
                "error": str(exc),
                "prompt": text,
                "prompt_preview": text[:80],
            })
            logger.error(
                "keeper.pii_unscrub_failed",
                error=str(exc),
                error_type=type(exc).__name__,
                exc_info=True,
            )
            return text

    @staticmethod
    async def clean_skill_output(raw_data: str, goal: str, *, agent_id: str | None = None) -> str:
        settings = get_settings()
        url = f"{settings.keeper_url}/skill/clean"
        headers = {"X-Agent-ID": agent_id} if agent_id else {}
        start = time.monotonic()
        try:
            token = create_internal_token("core-api", scopes=["keeper:clean"], expires_minutes=1)
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    url,
                    json={"raw_data": raw_data, "extraction_goal": goal, "agent_id": agent_id},
                    headers={"X-Internal-Auth": token, **headers}
                )
                resp.raise_for_status()
                data = resp.json()
            latency = (time.monotonic() - start) * 1000
            await EventManager.emit("keeper:inference", {
                "agent_id": agent_id or "system",
                "endpoint": "skill/clean",
                "latency_ms": round(latency, 2),
                "status": "success",
                "prompt": f"Goal: {goal}\nData: {raw_data}",
                "completion": data.get("cleaned_data"),
                "prompt_preview": f"Goal: {goal}\nData: {raw_data}"[:80],
                "completion_preview": (data.get("cleaned_data") or "")[:80],
            })
            return data.get("cleaned_data", raw_data)
        except Exception as exc:
            latency = (time.monotonic() - start) * 1000
            await EventManager.emit("keeper:inference", {
                "agent_id": agent_id or "system",
                "endpoint": "skill/clean",
                "latency_ms": round(latency, 2),
                "status": "error",
                "error": str(exc),
                "prompt": f"Goal: {goal}\nData: {raw_data}",
                "prompt_preview": f"Goal: {goal}\nData: {raw_data}"[:80],
            })
            logger.error(
                "keeper.skill_clean_failed",
                error=str(exc),
                error_type=type(exc).__name__,
                exc_info=True,
            )
            return raw_data

    @staticmethod
    async def update_journal(session_id: str, old_journal: str | None, recent_messages: list[dict[str, Any]], *, agent_id: str | None = None) -> str | None:
        settings = get_settings()
        url = f"{settings.keeper_url}/journal/update"
        headers = {"X-Agent-ID": agent_id} if agent_id else {}
        start = time.monotonic()
        try:
            token = create_internal_token("core-api", scopes=["keeper:journal"], expires_minutes=1)
            async with httpx.AsyncClient(timeout=180.0) as client:
                resp = await client.post(url, json={
                    "session_id": session_id,
                    "old_journal": old_journal,
                    "recent_messages": recent_messages,
                    "agent_id": agent_id
                }, headers={"X-Internal-Auth": token, **headers})
                resp.raise_for_status()
                data = resp.json()
            latency = (time.monotonic() - start) * 1000
            await EventManager.emit("keeper:inference", {
                "agent_id": agent_id or "system",
                "endpoint": "journal/update",
                "latency_ms": round(latency, 2),
                "status": "success",
                "prompt": json.dumps(recent_messages),
                "completion": data.get("journal"),
                "prompt_preview": json.dumps(recent_messages)[:80],
                "completion_preview": (data.get("journal") or "")[:80],
            })
            return data.get("journal")
        except Exception as exc:
            latency = (time.monotonic() - start) * 1000
            await EventManager.emit("keeper:inference", {
                "agent_id": agent_id or "system",
                "endpoint": "journal/update",
                "latency_ms": round(latency, 2),
                "status": "error",
                "error": str(exc),
                "prompt": json.dumps(recent_messages),
                "prompt_preview": json.dumps(recent_messages)[:80],
            })
            logger.error(
                "keeper.journal_update_failed",
                session_id=session_id,
                error=str(exc),
                error_type=type(exc).__name__,
                exc_info=True,
            )
            return None

    @staticmethod
    async def verify_logic(text: str, context: str | None = None, *, agent_id: str | None = None) -> dict[str, Any]:
        settings = get_settings()
        url = f"{settings.keeper_url}/verify/logic"
        headers = {"X-Agent-ID": agent_id} if agent_id else {}
        start = time.monotonic()
        try:
            token = create_internal_token("core-api", scopes=["keeper:verify"], expires_minutes=1)
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    url,
                    json={"text": text, "context": context, "agent_id": agent_id},
                    headers={"X-Internal-Auth": token, **headers}
                )
                resp.raise_for_status()
                data = resp.json()
            latency = (time.monotonic() - start) * 1000
            await EventManager.emit("keeper:inference", {
                "agent_id": agent_id or "system",
                "endpoint": "verify/logic",
                "latency_ms": round(latency, 2),
                "status": "success",
                "prompt": f"Context: {context}\nText: {text}",
                "completion": json.dumps(data),
                "prompt_preview": f"Context: {context}\nText: {text}"[:80],
                "completion_preview": json.dumps(data)[:80],
            })
            return data
        except Exception as exc:
            latency = (time.monotonic() - start) * 1000
            await EventManager.emit("keeper:inference", {
                "agent_id": agent_id or "system",
                "endpoint": "verify/logic",
                "latency_ms": round(latency, 2),
                "status": "error",
                "error": str(exc),
                "prompt": f"Context: {context}\nText: {text}",
                "prompt_preview": f"Context: {context}\nText: {text}"[:80],
            })
            logger.error(
                "keeper.verify_logic_failed",
                error=str(exc),
                error_type=type(exc).__name__,
                exc_info=True,
            )
            return {"is_valid": True, "reason": "Judge unavailable"}
