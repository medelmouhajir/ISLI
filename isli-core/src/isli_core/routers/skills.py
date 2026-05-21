import json
import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
import httpx
import structlog

from isli_core.auth import create_internal_token, SkillProxyAuth
from isli_core.security.content_scanner import ContentScanner
from isli_core.security.policy_engine import PolicyEngine
from isli_core.db import get_db
from isli_core.memory.keeper_client import KeeperClient
from isli_core.memory.chroma_client import ChromaMemoryClient
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import uuid4

logger = structlog.get_logger()
router = APIRouter(prefix="/skills", tags=["skills"])

SKILL_REGISTRY = {
    "web-fetch": os.getenv("SKILL_WEB_FETCH_URL", "http://localhost:8100"),
    "summarize": os.getenv("SKILL_SUMMARIZE_URL", "http://localhost:8100"),
    "translate": os.getenv("SKILL_TRANSLATE_URL", "http://localhost:8100"),
    "shell-exec": os.getenv("SKILL_SHELL_EXEC_URL", "http://localhost:8100"),
    "file-read": os.getenv("SKILL_FILE_READ_URL", "http://localhost:8300"),
    "file-write": os.getenv("SKILL_FILE_WRITE_URL", "http://localhost:8300"),
    "file-list": os.getenv("SKILL_FILE_LIST_URL", "http://localhost:8300"),
    "file-delete": os.getenv("SKILL_FILE_DELETE_URL", "http://localhost:8300"),
    "summarize-text": os.getenv("SKILL_SUMMARIZE_TEXT_URL", "http://localhost:8100"),
    "embed-text": os.getenv("SKILL_EMBED_TEXT_URL", "http://localhost:8100"),
    "memory-save": "inline",
    "memory-delete": "inline",
    "memory-search": "inline",
    "send-message": "inline",
}

# Metadata exposed via GET /v1/skills for dynamic skill discovery.
SKILL_METADATA: dict[str, dict[str, Any]] = {
    "web-fetch": {
        "description": "Fetch content from a URL and return structured data.",
        "type": "external",
    },
    "summarize": {
        "description": "Summarize long text into a concise summary.",
        "type": "external",
    },
    "translate": {
        "description": "Translate text between languages.",
        "type": "external",
    },
    "shell-exec": {
        "description": "Execute a shell command safely.",
        "type": "external",
    },
    "web-search": {
        "description": "Search the web using local SearXNG instance.",
        "type": "external",
    },
    "file-read": {
        "description": "Read a file from the agent workspace.",
        "type": "external",
    },
    "file-write": {
        "description": "Write or overwrite a file in the agent workspace.",
        "type": "external",
    },
    "file-list": {
        "description": "List files and directories in the agent workspace.",
        "type": "external",
    },
    "file-delete": {
        "description": "Delete a file from the agent workspace.",
        "type": "external",
    },
    "summarize-text": {
        "description": "Summarize text using the Keeper sidecar.",
        "type": "external",
    },
    "embed-text": {
        "description": "Generate text embeddings using the Keeper sidecar.",
        "type": "external",
    },
    "memory-save": {
        "description": "Save a fact to the agent's semantic memory.",
        "type": "inline",
    },
    "memory-delete": {
        "description": "Delete a fact from the agent's semantic memory.",
        "type": "inline",
    },
    "memory-search": {
        "description": "Search the agent's semantic memory for relevant facts.",
        "type": "inline",
    },
    "send-message": {
        "description": "Send a message to a user via their channel.",
        "type": "inline",
    },
}

chroma = ChromaMemoryClient()


class SkillRequest(BaseModel):
    action: str
    payload: dict[str, Any]


class SkillMetadataOut(BaseModel):
    name: str
    description: str
    type: str
    url: str | None = None


@router.get("", response_model=list[SkillMetadataOut])
async def list_skills():
    """Return metadata for all registered skills.

    Used by agents at startup for dynamic skill discovery and tool auto-registration.
    """
    skills = []
    for name, base_url in SKILL_REGISTRY.items():
        meta = SKILL_METADATA.get(name, {})
        skills.append(
            SkillMetadataOut(
                name=name,
                description=meta.get("description", ""),
                type=meta.get("type", "external"),
                url=base_url if base_url != "inline" else None,
            )
        )
    return skills


@router.post("/{skill_name}/{action}")
async def skill_proxy(
    skill_name: str,
    action: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    base_url = SKILL_REGISTRY.get(skill_name)
    if not base_url:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not registered")

    # Verify internal auth header from caller
    try:
        SkillProxyAuth.verify(request)
    except HTTPException:
        # In dev mode, allow unauthenticated if no header is present
        if request.headers.get("X-Internal-Auth") is None:
            logger.warning("skills.dev_mode_unauthenticated", skill=skill_name)
        else:
            raise

    body_bytes = await request.body()

    # Inline handlers for memory skills (executed directly in Core, no external proxy)
    if base_url == "inline":
        try:
            body_json = json.loads(body_bytes.decode("utf-8", errors="ignore")) if body_bytes else {}
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid JSON body")

        agent_id = body_json.get("agent_id")
        if not agent_id:
            raise HTTPException(status_code=400, detail="Missing agent_id in request body")
        collection_name = f"agent_{agent_id}"

        if skill_name == "memory-save" and action == "save":
            content = body_json.get("content")
            if not content:
                raise HTTPException(status_code=400, detail="Missing content in request body")
            fact_id = str(uuid4())
            try:
                await chroma.save_fact(
                    collection_name=collection_name,
                    fact_id=fact_id,
                    content=content,
                    metadata=body_json.get("metadata"),
                    embedding=body_json.get("embedding"),
                )
                return {"id": fact_id, "collection": collection_name, "status": "saved"}
            except Exception as exc:
                logger.error("skills.memory_save_failed", agent_id=agent_id, error=str(exc))
                raise HTTPException(status_code=500, detail=f"Failed to save memory: {exc}")

        if skill_name == "memory-delete" and action == "delete":
            fact_id = body_json.get("fact_id")
            if not fact_id:
                raise HTTPException(status_code=400, detail="Missing fact_id in request body")
            try:
                await chroma.delete_fact(collection_name=collection_name, fact_id=fact_id)
                return {"status": "deleted", "fact_id": fact_id}
            except Exception as exc:
                logger.error("skills.memory_delete_failed", agent_id=agent_id, fact_id=fact_id, error=str(exc))
                raise HTTPException(status_code=500, detail=f"Failed to delete memory: {exc}")

        if skill_name == "memory-search" and action == "search":
            query_text = body_json.get("query_text")
            if not query_text:
                raise HTTPException(status_code=400, detail="Missing query_text in request body")
            try:
                results = await chroma.search_facts(
                    collection_name=collection_name,
                    query_text=query_text,
                    query_embedding=body_json.get("query_embedding"),
                    limit=body_json.get("limit", 5),
                    metadata_filter=body_json.get("metadata_filter"),
                )
                return results
            except Exception as exc:
                logger.error("skills.memory_search_failed", agent_id=agent_id, query=query_text, error=str(exc))
                raise HTTPException(status_code=500, detail="Failed to search memory")

        if skill_name == "send-message" and action == "send":
            agent_id = body_json.get("agent_id")
            channel = body_json.get("channel")
            channel_user_id = body_json.get("channel_user_id")
            text = body_json.get("text")
            if not all([agent_id, channel, channel_user_id, text]):
                raise HTTPException(status_code=400, detail="Missing required fields: agent_id, channel, channel_user_id, text")

            from sqlalchemy import select
            from isli_core.models import Agent, Session, ChannelMessage
            from isli_core.config import get_settings
            from isli_core.retry import exponential_backoff
            from datetime import datetime, timezone, timedelta

            # 1. Verify agent exists and channel is assigned
            result = await db.execute(select(Agent).where(Agent.id == agent_id, Agent.deleted_at.is_(None)))
            agent = result.scalar_one_or_none()
            if not agent:
                raise HTTPException(status_code=404, detail="Agent not found")
            if channel not in (agent.channels or []):
                raise HTTPException(status_code=403, detail="Channel not assigned to agent")

            # 2. Find or create canonical session (same convention as channels.py webhook)
            session_id = f"sess_{channel}_{agent_id}_{channel_user_id}"
            now = datetime.now(timezone.utc)
            result = await db.execute(select(Session).where(Session.id == session_id, Session.deleted_at.is_(None)))
            sess = result.scalar_one_or_none()

            if not sess:
                soft_deleted_result = await db.execute(select(Session).where(Session.id == session_id))
                soft_deleted = soft_deleted_result.scalar_one_or_none()
                if soft_deleted:
                    soft_deleted.deleted_at = None
                    soft_deleted.status = "ready"
                    soft_deleted.expires_at = now + timedelta(hours=24)
                    soft_deleted.last_activity_at = now
                    sess = soft_deleted
                else:
                    sess = Session(
                        id=session_id,
                        agent_id=agent_id,
                        user_id=channel_user_id,
                        channel=channel,
                        messages=[],
                        consent_given=True,
                        consent_at=now,
                        expires_at=now + timedelta(hours=24),
                        status="ready",
                    )
                    db.add(sess)
            else:
                sess.expires_at = now + timedelta(hours=24)
                sess.last_activity_at = now

            sess.messages = (sess.messages or []) + [
                {"role": "assistant", "content": text, "timestamp": now.isoformat()}
            ]
            sess.last_message_at = now
            await db.commit()
            await db.refresh(sess)

            # 3. Audit outbound message
            msg = ChannelMessage(
                session_id=session_id,
                sequence_number=len(sess.messages),
                channel=channel,
                direction="outbound",
                content=text,
                raw_payload={"source": "send_message_skill", "agent_id": agent_id},
            )
            db.add(msg)
            await db.commit()

            # 4. Forward to channels service (only for external channels)
            if channel != "web":
                settings = get_settings()

                async def _send_to_channels():
                    async with httpx.AsyncClient() as client:
                        resp = await client.post(
                            f"{settings.channels_url}/send",
                            json={"channel": channel, "channel_user_id": channel_user_id, "text": text, "agent_id": agent_id},
                            timeout=10.0,
                        )
                        resp.raise_for_status()

                try:
                    await exponential_backoff(_send_to_channels, max_retries=3, base_delay=1.0, max_delay=10.0)
                except Exception as exc:
                    logger.error("skills.send_message_failed", agent_id=agent_id, channel=channel, error=str(exc))
            else:
                logger.debug(
                    "skills.send_message.skip_external_forward",
                    agent_id=agent_id,
                    channel=channel
                )

            return {"status": "sent", "session_id": session_id}

        raise HTTPException(status_code=404, detail=f"Action '{action}' not found for skill '{skill_name}'")

    body = body_bytes

    # Content scan on the raw body text
    body_text = body.decode("utf-8", errors="ignore") if body else ""
    scan = ContentScanner.scan(body_text)
    if scan.blocked:
        raise HTTPException(status_code=403, detail=f"Content safety block: {scan.reason}")

    # Policy evaluation for skill invocation
    decision = await PolicyEngine.evaluate(
        db,
        user_id="anonymous",
        input_text=body_text,
        agent_id=None,
        skill_name=skill_name,
        model_id=None,
        budget_exceeded=False,
        estop_active=False,
    )
    if not decision.allow:
        detail: dict[str, Any] = {
            "detail": f"Policy block: {decision.reason}",
            "policy_decision": {
                "allow": decision.allow,
                "reason": decision.reason,
                "risk_score": decision.risk_score,
                "overrideable": decision.overrideable,
                "rule": decision.rule,
                "context_hash": decision.context_hash,
            },
        }
        if decision.overrideable:
            detail["override_request_url"] = "/v1/security/override-request"
        raise HTTPException(status_code=403, detail=detail)
    token = create_internal_token("core-api", scopes=["skill:proxy"], expires_minutes=5)
    headers = {
        "X-Internal-Auth": token,
        "Content-Type": request.headers.get("Content-Type", "application/json"),
    }

    from isli_core.verification.grounding import GroundingVerifier
    from isli_core.telemetry import get_verification_failure_counter

    url = f"{base_url}/{action}"

    async def _call_skill() -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, headers=headers, content=body)
            resp.raise_for_status()
            return resp.json()

    try:
        raw, result = await GroundingVerifier.verify_with_retry(
            skill_name, _call_skill, max_retries=3
        )

        # Phase 2: Local Skill Cleaning (Signal Harvesting)
        HEAVY_SKILLS = {"web-fetch", "shell-exec"}
        if result.is_valid and skill_name in HEAVY_SKILLS:
            logger.info("skills.harvesting.cleaning", skill=skill_name)
            # Use the action or a generic goal for cleaning
            cleaned = await KeeperClient.clean_skill_output(
                str(raw),
                goal=f"Extract relevant data for action '{action}'"
            )
            return {"status": "ok", "skill": skill_name, "action": action, "result": cleaned}

    except Exception as exc:
        logger.error("skills.proxy_unexpected_error", skill=skill_name, error=str(exc))
        raise HTTPException(status_code=500, detail=f"Unexpected skill proxy error: {exc}") from exc

    if not result.is_valid:
        from isli_core.telemetry import get_skill_invocation_error_counter
        reason_lower = result.reason.lower() if result.reason else ""
        if "httpx" in reason_lower and "status" in reason_lower:
            get_skill_invocation_error_counter().add(
                1, {"skill": skill_name, "reason": "http_error"}
            )
        elif "unreachable" in reason_lower or "connect" in reason_lower or "timeout" in reason_lower:
            get_skill_invocation_error_counter().add(
                1, {"skill": skill_name, "reason": "unreachable"}
            )
        get_verification_failure_counter().add(
            1, {"skill": skill_name, "reason": result.reason}
        )
        logger.error("skills.verification_failed", skill=skill_name, reason=result.reason)
        raise HTTPException(
            status_code=502,
            detail={"success": False, "error": result.reason, "skill": skill_name},
        )

    return raw
