import asyncio
import base64
import json
import os
import subprocess
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
from isli_core.services.skill_manager import skill_manager
from isli_core.config import get_settings
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import uuid4

logger = structlog.get_logger()
router = APIRouter(prefix="/skills", tags=["skills"])

class SkillInstallRequest(BaseModel):
    skill_id: str
    git_url: str

# Consolidated upstream URLs — replaces ~25 SKILL_*_URL env vars.
# In Docker Compose: SKILLS_URL, WORKSPACE_URL, AUDIO_URL, KEEPER_URL, CHANNELS_URL.
_SKILLS_URL = os.getenv("SKILLS_URL", "http://localhost:8100")
_WORKSPACE_URL = os.getenv("WORKSPACE_URL", "http://localhost:8300")
_AUDIO_URL = os.getenv("AUDIO_URL", "http://localhost:8400")

SKILL_REGISTRY = {
    # skills microservice
    "web-fetch": _SKILLS_URL,
    "web-search": _SKILLS_URL,
    "summarize": _SKILLS_URL,
    "translate": _SKILLS_URL,
    "shell-exec": _SKILLS_URL,
    "summarize-text": _SKILLS_URL,
    "embed-text": _SKILLS_URL,
    "test-skill": _SKILLS_URL,
    "register-skill": _SKILLS_URL,
    "update-skill": _SKILLS_URL,
    "interactive-debugger": _SKILLS_URL,
    "db-query": _SKILLS_URL,
    # workspace service
    "file-read": _WORKSPACE_URL,
    "file-write": _WORKSPACE_URL,
    "file-list": _WORKSPACE_URL,
    "file-delete": _WORKSPACE_URL,
    "git-clone": _WORKSPACE_URL,
    "git-status": _WORKSPACE_URL,
    "git-commit": _WORKSPACE_URL,
    "git-push": _WORKSPACE_URL,
    "git-pull": _WORKSPACE_URL,
    "git-branch-list": _WORKSPACE_URL,
    "git-branch-create": _WORKSPACE_URL,
    "git-checkout": _WORKSPACE_URL,
    "git-log": _WORKSPACE_URL,
    "pip-install": _WORKSPACE_URL,
    "pip-list": _WORKSPACE_URL,
    # audio service
    "speech-to-text": f"{_AUDIO_URL}/stt",
    "text-to-speech": f"{_AUDIO_URL}/tts",
    # browser automation (hosted on skills service)
    "web-browse-navigate": f"{_SKILLS_URL}/browse",
    "web-browse-snapshot": f"{_SKILLS_URL}/browse",
    "web-browse-click": f"{_SKILLS_URL}/browse",
    "web-browse-type": f"{_SKILLS_URL}/browse",
    "web-browse-press": f"{_SKILLS_URL}/browse",
    "web-browse-scroll": f"{_SKILLS_URL}/browse",
    "web-browse-back": f"{_SKILLS_URL}/browse",
    "web-browse-console": f"{_SKILLS_URL}/browse",
    "web-browse-vision": f"{_SKILLS_URL}/browse",
    "web-browse-images": f"{_SKILLS_URL}/browse",
    # inline handlers (executed within Core)
    "get-secret": "inline",
    "memory-save": "inline",
    "memory-delete": "inline",
    "memory-search": "inline",
    "send-message": "inline",
    "create-kanban-task": "inline",
    "create-engineering-plan": "inline",
    "ui-components": "inline",
    "notify-user": "inline",
    "list-kanban-tasks": "inline",
    "update-kanban-task": "inline",
}

# Metadata exposed via GET /v1/skills for dynamic skill discovery.
SKILL_METADATA: dict[str, dict[str, Any]] = {
    "web-fetch": {
        "description": "Fetch content from a URL and return structured data.",
        "type": "external",
        "category": "web",
    },
    "summarize": {
        "description": "Summarize long text into a concise summary.",
        "type": "external",
        "category": "content",
    },
    "translate": {
        "description": "Translate text between languages.",
        "type": "external",
        "category": "content",
    },
    "shell-exec": {
        "description": "Execute a shell command safely.",
        "type": "external",
        "category": "system",
    },
    "web-search": {
        "description": "Search the web using local SearXNG instance.",
        "type": "external",
        "category": "web",
    },
    "web-browse-navigate": {
        "description": "Navigate a browser to a URL. Creates or reuses a persistent session per agent.",
        "type": "external",
        "category": "web",
    },
    "web-browse-snapshot": {
        "description": "Take an accessibility-tree snapshot of the current page. Returns compact text with @ref IDs for interactive elements.",
        "type": "external",
        "category": "web",
    },
    "web-browse-click": {
        "description": "Click an element by its @ref ID from the last snapshot.",
        "type": "external",
        "category": "web",
    },
    "web-browse-type": {
        "description": "Type text into an input field by its @ref ID.",
        "type": "external",
        "category": "web",
    },
    "web-browse-press": {
        "description": "Press a keyboard key (Enter, Tab, Escape, etc.).",
        "type": "external",
        "category": "web",
    },
    "web-browse-scroll": {
        "description": "Scroll the page up or down.",
        "type": "external",
        "category": "web",
    },
    "web-browse-back": {
        "description": "Navigate back in browser history.",
        "type": "external",
        "category": "web",
    },
    "web-browse-console": {
        "description": "Return browser console logs captured since the last call.",
        "type": "external",
        "category": "web",
    },
    "web-browse-vision": {
        "description": "Take a screenshot of the current page and return it as base64.",
        "type": "external",
        "category": "web",
    },
    "web-browse-images": {
        "description": "List all image elements on the current page with src and alt text.",
        "type": "external",
        "category": "web",
    },
    "file-read": {
        "description": "Read a file from the agent workspace.",
        "type": "external",
        "category": "workspace",
    },
    "file-write": {
        "description": "Write or overwrite a file in the agent workspace.",
        "type": "external",
        "category": "workspace",
    },
    "file-list": {
        "description": "List files and directories in the agent workspace.",
        "type": "external",
        "category": "workspace",
    },
    "file-delete": {
        "description": "Delete a file from the agent workspace.",
        "type": "external",
        "category": "workspace",
    },
    "summarize-text": {
        "description": "Summarize text using the Keeper sidecar.",
        "type": "external",
        "category": "content",
    },
    "embed-text": {
        "description": "Generate text embeddings using the Keeper sidecar.",
        "type": "external",
        "category": "content",
    },
    "test-skill": {
        "description": "Dry-run test dynamic skill code in a sandbox.",
        "type": "external",
        "category": "engineering",
    },
    "register-skill": {
        "description": "Register a new dynamic skill after successful testing.",
        "type": "external",
        "category": "engineering",
    },
    "update-skill": {
        "description": "Update metadata of an existing dynamic skill.",
        "type": "external",
        "category": "engineering",
    },
    "interactive-debugger": {
        "description": "Run code in an interactive debugger with breakpoints and variable inspection.",
        "type": "external",
        "category": "engineering",
    },
    "speech-to-text": {
        "description": "Transcribe audio to text using local Whisper STT.",
        "type": "external",
        "category": "audio",
    },
    "text-to-speech": {
        "description": "Synthesize speech from text using local Piper TTS.",
        "type": "external",
        "category": "audio",
    },
    "db-query": {
        "description": "Run a read-only SQL query against the ISLI database. Returns structured tabular results. Only SELECT statements on allowed schemas are permitted.",
        "type": "external",
        "category": "database",
    },
    "git-clone": {
        "description": "Clone a remote git repository into the agent's workspace. Supports optional branch selection.",
        "type": "external",
        "category": "git",
    },
    "git-status": {
        "description": "Show the working tree status of a git repository: modified, staged, and untracked files.",
        "type": "external",
        "category": "git",
    },
    "git-commit": {
        "description": "Stage files and commit changes in a git repository with a message.",
        "type": "external",
        "category": "git",
    },
    "git-push": {
        "description": "Push the current or specified branch to a remote repository.",
        "type": "external",
        "category": "git",
    },
    "git-pull": {
        "description": "Pull changes from a remote repository into the current branch.",
        "type": "external",
        "category": "git",
    },
    "git-branch-list": {
        "description": "List all branches in a git repository, indicating the current branch.",
        "type": "external",
        "category": "git",
    },
    "git-branch-create": {
        "description": "Create a new branch in a git repository, optionally checking it out.",
        "type": "external",
        "category": "git",
    },
    "git-checkout": {
        "description": "Checkout (switch to) an existing branch in a git repository.",
        "type": "external",
        "category": "git",
    },
    "git-log": {
        "description": "Show the commit history of a git repository.",
        "type": "external",
        "category": "git",
    },
    "pip-install": {
        "description": "Install Python packages from PyPI into the agent's workspace. Uses pip install --target so packages persist across restarts.",
        "type": "external",
        "category": "workspace",
    },
    "pip-list": {
        "description": "List Python packages installed in the agent's workspace via pip-install.",
        "type": "external",
        "category": "workspace",
    },
    "get-secret": {
        "description": "Retrieve a secret value from the agent's secure vault by name. Used to access API keys, database credentials, or tokens without hardcoding them.",
        "type": "inline",
        "category": "system",
    },
    "memory-save": {
        "description": "Save a fact to the agent's semantic memory.",
        "type": "inline",
        "category": "memory",
    },
    "memory-delete": {
        "description": "Delete a fact from the agent's semantic memory.",
        "type": "inline",
        "category": "memory",
    },
    "memory-search": {
        "description": "Search the agent's semantic memory for relevant facts.",
        "type": "inline",
        "category": "memory",
    },
    "send-message": {
        "description": "Send a message to a user via their channel.",
        "type": "inline",
        "category": "communication",
    },
    "create-kanban-task": {
        "description": "Create a task on the Kanban board (enables self-delegation).",
        "type": "inline",
        "category": "kanban",
    },
    "create-engineering-plan": {
        "description": "Generate a structured SE implementation plan (PLAN.md).",
        "type": "inline",
        "category": "engineering",
    },
    "ui-components": {
        "description": "Render interactive UI components (tables, cards, buttons) inline in chat.",
        "type": "inline",
        "category": "system",
    },
    "notify-user": {
        "description": "Send a notification to a user through the unified notification system. Respects user preferences, quiet hours, and rate limits (max 20/hour per user per agent).",
        "type": "inline",
        "category": "communication",
    },
    "list-kanban-tasks": {
        "description": "Query the Kanban board for tasks based on status, assignee, or tags.",
        "type": "inline",
        "category": "kanban",
    },
    "update-kanban-task": {
        "description": "Update an existing Kanban task's status, priority, or append a comment/handoff note.",
        "type": "inline",
        "category": "kanban",
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
    category: str = "uncategorized"
    url: str | None = None


@router.get("", response_model=list[SkillMetadataOut])
async def list_skills():
    """Return metadata for all registered skills.

    Used by agents at startup for dynamic skill discovery and tool auto-registration.
    """
    skills = []
    # Static skills
    for name, base_url in SKILL_REGISTRY.items():
        meta = SKILL_METADATA.get(name, {})
        skills.append(
            SkillMetadataOut(
                name=name,
                description=meta.get("description", ""),
                type=meta.get("type", "external"),
                category=meta.get("category", "uncategorized"),
                url=base_url if base_url != "inline" else None,
            )
        )
    
    # Dynamic skills
    dynamic_meta = skill_manager.get_skill_metadata()
    for skill_id, meta in dynamic_meta.items():
        skills.append(
            SkillMetadataOut(
                name=skill_id,
                description=meta.get("description", "Installed via Skills Store"),
                type="dynamic",
                category=meta.get("category", "custom"),
                url=None,
            )
        )

    return skills


@router.post("/install")
async def install_skill(
    request: SkillInstallRequest,
    db: AsyncSession = Depends(get_db),
):
    """Clones a skill from a git repository and registers it locally."""
    settings = get_settings()
    target_dir = os.path.join(settings.installed_skills_path, request.skill_id)

    if os.path.exists(target_dir):
        logger.info("skills.install_already_exists", skill_id=request.skill_id)
        # Optionally perform git pull here
        try:
            subprocess.run(["git", "-C", target_dir, "pull"], check=True)
        except subprocess.CalledProcessError as e:
            raise HTTPException(
                status_code=500, detail=f"Failed to update skill: {str(e)}"
            ) from e
    else:
        try:
            logger.info(
                "skills.install_cloning", skill_id=request.skill_id, url=request.git_url
            )
            subprocess.run(["git", "clone", request.git_url, target_dir], check=True)
        except subprocess.CalledProcessError as e:
            raise HTTPException(
                status_code=500, detail=f"Failed to clone skill repository: {str(e)}"
            ) from e

    # Refresh registry
    skill_manager.refresh_registry()

    return {"status": "success", "skill_id": request.skill_id, "path": target_dir}


@router.post("/{skill_name}/{action}")
async def skill_proxy(
    skill_name: str,
    action: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    base_url = SKILL_REGISTRY.get(skill_name)
    
    # Check if it's a dynamic skill if not in static registry
    is_dynamic = False
    if not base_url:
        if skill_name in skill_manager.get_skill_metadata():
            is_dynamic = True
        else:
            raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not registered")

    # Verify internal auth header from caller
    try:
        SkillProxyAuth.verify(request)
    except HTTPException:
        # In dev mode ONLY, allow unauthenticated if no header is present
        if get_settings().isli_env == "development" and request.headers.get("X-Internal-Auth") is None:
            logger.warning("skills.dev_mode_unauthenticated", skill=skill_name)
        else:
            raise

    body_bytes = await request.body()

    # Dynamic skill handler
    if is_dynamic:
        handler = skill_manager.get_handler(skill_name)
        if not handler:
            raise HTTPException(
                status_code=500,
                detail=f"Handler for dynamic skill '{skill_name}' could not be loaded",
            )

        try:
            body_json = (
                json.loads(body_bytes.decode("utf-8", errors="ignore"))
                if body_bytes
                else {}
            )
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=400, detail="Invalid JSON body") from e

        # Assume dynamic skills have a 'handle' function or similar
        if hasattr(handler, "handle"):
            try:
                # Dynamic skills can be async or sync
                if asyncio.iscoroutinefunction(handler.handle):
                    return await handler.handle(action, body_json, db)
                else:
                    return handler.handle(action, body_json, db)
            except Exception as e:
                logger.error(
                    "skills.dynamic_handler_failed",
                    skill=skill_name,
                    action=action,
                    error=str(e),
                )
                raise HTTPException(
                    status_code=500,
                    detail=f"Dynamic skill execution failed: {str(e)}",
                ) from e
        else:
            raise HTTPException(
                status_code=500,
                detail=f"Dynamic skill '{skill_name}' missing 'handle' function",
            )

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
            audio_b64 = body_json.get("audio_b64")
            if not all([agent_id, channel, channel_user_id, text]):
                raise HTTPException(status_code=400, detail="Missing required fields: agent_id, channel, channel_user_id, text")

            # Validate audio_b64 size at schema level (5 MB raw ~ 6.7 MB base64)
            if audio_b64 and len(audio_b64) > 6_700_000:
                raise HTTPException(status_code=413, detail="audio_b64 exceeds maximum size of 5 MB decoded")

            from sqlalchemy import select
            from isli_core.models import Agent, Session, ChannelMessage
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

            # --- Audio handling for send-message skill ---
            audio_url: str | None = None
            audio_b64_for_channels = audio_b64
            if audio_b64_for_channels:
                try:
                    MAX_AUDIO_BYTES = 5 * 1024 * 1024
                    audio_bytes = base64.b64decode(audio_b64_for_channels)
                    if len(audio_bytes) > MAX_AUDIO_BYTES:
                        logger.warning(
                            "skills.send_message_audio_too_large",
                            agent_id=agent_id,
                            size=len(audio_bytes),
                        )
                        audio_b64_for_channels = None
                    else:
                        from isli_core.routers.workspaces import upload_bytes_to_workspace
                        audio_filename = f"{uuid4()}.wav"
                        workspace_path = f"_attachments/audio/{session_id}/{audio_filename}"
                        await upload_bytes_to_workspace(
                            agent_id=agent_id,
                            path=workspace_path,
                            data=audio_bytes,
                            scope="attachment",
                            scope_id=session_id,
                        )
                        audio_url = f"/v1/sessions/{session_id}/audio/{audio_filename}"
                        logger.info(
                            "skills.send_message_audio_uploaded",
                            agent_id=agent_id,
                            filename=audio_filename,
                            size=len(audio_bytes),
                        )
                except Exception as exc:
                    logger.warning("skills.send_message_audio_upload_failed", agent_id=agent_id, error=str(exc))
                    audio_b64_for_channels = None

            msg = {"role": "assistant", "content": text, "timestamp": now.isoformat()}
            if audio_url:
                msg["audio_url"] = audio_url
            sess.messages = (sess.messages or []) + [msg]
            sess.last_message_at = now
            await db.commit()
            await db.refresh(sess)

            # 3. Audit outbound message
            channel_msg = ChannelMessage(
                session_id=session_id,
                sequence_number=len(sess.messages),
                channel=channel,
                direction="outbound",
                content=text,
                raw_payload={
                    "source": "send_message_skill",
                    "agent_id": agent_id,
                    "audio_url": audio_url,
                },
            )
            db.add(channel_msg)
            await db.commit()

            # 4. Forward to channels service (only for external channels)
            if channel != "web":
                settings = get_settings()

                async def _send_to_channels():
                    payload_channels = {
                        "channel": channel,
                        "channel_user_id": channel_user_id,
                        "text": text,
                        "agent_id": agent_id,
                    }
                    if audio_b64_for_channels:
                        payload_channels["audio_b64"] = audio_b64_for_channels
                    async with httpx.AsyncClient() as client:
                        resp = await client.post(
                            f"{settings.channels_url}/send",
                            json=payload_channels,
                            headers={"X-Internal-Auth": create_internal_token("core", scopes=["channels:send"], expires_minutes=5)},
                            timeout=10.0,
                        )
                        resp.raise_for_status()

                try:
                    from isli_core.dynamic_config import get_setting
                    max_retries = await get_setting(db, "default_max_retries", scope="general", default=3)
                    base_delay = await get_setting(db, "default_base_delay_seconds", scope="general", default=1.0)
                    max_delay = await get_setting(db, "default_max_delay_seconds", scope="general", default=10.0)
                    await exponential_backoff(
                        _send_to_channels,
                        max_retries=max_retries,
                        base_delay=base_delay,
                        max_delay=max_delay,
                    )
                except Exception as exc:
                    logger.error("skills.send_message_failed", agent_id=agent_id, channel=channel, error=str(exc))
            else:
                logger.debug(
                    "skills.send_message.skip_external_forward",
                    agent_id=agent_id,
                    channel=channel
                )

            return {"status": "sent", "session_id": session_id}

        if skill_name == "notify-user" and action == "send":
            agent_id = body_json.get("agent_id")
            user_id = body_json.get("user_id")
            title = body_json.get("title")
            message = body_json.get("message", "")
            priority = body_json.get("priority", "normal")

            if not all([agent_id, user_id, title]):
                raise HTTPException(status_code=400, detail="Missing required fields: agent_id, user_id, title")

            # Rate limit check (same logic as notifications router)
            AGENT_NOTIFY_RATE_LIMIT = 20
            try:
                from isli_core.redis_client import get_redis
                redis = await get_redis()
                rate_key = f"notif:agent_rate:{agent_id}:{user_id}"
                count = await redis.incr(rate_key)
                if count == 1:
                    await redis.expire(rate_key, 3600)
                if count > AGENT_NOTIFY_RATE_LIMIT:
                    raise HTTPException(status_code=429, detail="Notification rate limit exceeded for this agent (max 20/hour per user)")
            except HTTPException:
                raise
            except Exception as exc:
                logger.warning("skills.notify_user_rate_limit_redis_failed", error=str(exc))

            from isli_core.models import Notification
            from datetime import datetime, timezone

            notif = Notification(
                user_id=user_id,
                event_type="agent:proactive",
                category=priority,
                title=title,
                body=message or None,
                agent_id=agent_id,
            )
            db.add(notif)
            await db.commit()
            await db.refresh(notif)

            # Emit WS event
            from isli_core.event_manager import EventManager
            await EventManager.emit(
                "notification:new",
                {
                    "notification_id": notif.id,
                    "user_id": user_id,
                    "event_type": "agent:proactive",
                    "category": priority,
                    "title": title,
                    "body": message,
                    "created_at": notif.created_at.isoformat() if notif.created_at else None,
                    "agent_id": agent_id,
                },
            )

            return {"ok": True, "notification_id": notif.id}

        if skill_name == "get-secret" and action == "get":
            secret_name = body_json.get("name")
            if not secret_name:
                raise HTTPException(status_code=400, detail="Missing name in request body")

            from isli_core.secrets_service import get_secret_value
            from isli_core.audit_writer import AuditWriter

            value = await get_secret_value(db, agent_id, secret_name)
            if value is None:
                raise HTTPException(status_code=404, detail=f"Secret '{secret_name}' not found")

            # Audit every secret read (value never logged)
            await AuditWriter.write(
                session=db,
                actor_type="agent",
                actor_id=agent_id,
                action="secret.read",
                target_type="secret",
                target_id=secret_name,
                payload={"agent_id": agent_id, "secret_name": secret_name},
            )
            await db.commit()
            return {"status": "ok", "name": secret_name, "value": value}

        if skill_name == "create-kanban-task" and action == "create":
            title = body_json.get("title")
            if not title:
                raise HTTPException(status_code=400, detail="Missing title in request body")

            from isli_core.routers.tasks import _create_task_core, TaskCreate, TaskOut
            from datetime import datetime

            scheduled_at_raw = body_json.get("scheduled_at")
            scheduled_at: datetime | None = None
            if scheduled_at_raw:
                try:
                    scheduled_at = datetime.fromisoformat(scheduled_at_raw.replace("Z", "+00:00"))
                except ValueError as exc:
                    raise HTTPException(status_code=400, detail=f"Invalid scheduled_at format: {exc}")

            payload = TaskCreate(
                title=title,
                description=body_json.get("description"),
                type=body_json.get("task_type", "task"),
                priority=body_json.get("priority", 3),
                agent_id=body_json.get("target_agent_id"),
                created_by=agent_id,
                input=body_json.get("input_data", ""),
                parent_task_id=body_json.get("parent_task_id"),
                scheduled_at=scheduled_at,
                cron_expression=body_json.get("cron_expression"),
            )

            task = await _create_task_core(db, payload, estop_active=request.app.state.estop.active)
            return {
                "status": "created",
                "task": TaskOut.model_validate(task).model_dump(mode="json"),
            }

        if skill_name == "list-kanban-tasks" and action == "list":
            from isli_core.models import Task
            from isli_core.routers.tasks import TaskOut
            from sqlalchemy import select

            stmt = select(Task).where(Task.deleted_at.is_(None))
            if body_json.get("status"):
                stmt = stmt.where(Task.status == body_json.get("status"))
            if body_json.get("assignee_id"):
                stmt = stmt.where(Task.agent_id == body_json.get("assignee_id"))
            
            # Use tags if provided in body
            tags = body_json.get("tags")
            if tags:
                if isinstance(tags, str):
                    tags = [tags]
                for tag in tags:
                    stmt = stmt.where(Task.tags.contains([tag]))

            stmt = stmt.order_by(Task.created_at.desc())
            result = await db.execute(stmt)
            tasks = result.scalars().all()
            return [TaskOut.model_validate(t).model_dump(mode="json") for t in tasks]

        if skill_name == "update-kanban-task" and action == "update":
            task_id = body_json.get("task_id")
            if not task_id:
                raise HTTPException(status_code=400, detail="Missing task_id in request body")
            
            from isli_core.models import Task
            from isli_core.routers.tasks import TaskOut, VALID_STATUSES
            from isli_core.event_manager import EventManager
            from isli_core.audit_writer import AuditWriter
            from datetime import datetime, timezone

            result = await db.execute(select(Task).where(Task.id == task_id, Task.deleted_at.is_(None)))
            task = result.scalar_one_or_none()
            if not task:
                raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")

            changes = {}
            new_status = body_json.get("new_status")
            if new_status:
                if new_status not in VALID_STATUSES:
                    raise HTTPException(status_code=400, detail=f"Invalid status: {new_status}")
                if task.status != new_status:
                    old_status = task.status
                    task.status = new_status
                    changes["status"] = new_status
                    if new_status == "doing":
                        task.started_at = datetime.now(timezone.utc)
                    if new_status in ("done", "failed"):
                        task.completed_at = datetime.now(timezone.utc)
                    
                    await EventManager.emit("task:moved", {
                        "task_id": task_id,
                        "from": old_status,
                        "to": new_status,
                        "task": TaskOut.model_validate(task).model_dump(mode="json")
                    })

            new_priority = body_json.get("new_priority")
            if new_priority is not None:
                task.priority = new_priority
                changes["priority"] = new_priority

            comment = body_json.get("comment")
            if comment:
                timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                addition = f"\n\n--- Handoff/Comment ({timestamp}) ---\n{comment}"
                task.description = (task.description or "") + addition
                changes["description_updated"] = True

            if changes:
                task.updated_at = datetime.now(timezone.utc)
                task.version += 1
                await db.commit()
                await db.refresh(task)
                
                await AuditWriter.write(
                    db, actor_type="agent", actor_id=agent_id, action="update_task_skill",
                    target_type="task", target_id=task.id,
                    payload={"changes": changes, "comment": comment},
                )
                await db.commit()
                
                await EventManager.emit("task:updated", {
                    "task_id": task_id,
                    "changes": changes,
                    "task": TaskOut.model_validate(task).model_dump(mode="json")
                })

            return {"status": "success", "task_id": task_id, "updated": bool(changes)}

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
        estop_active=request.app.state.estop.active,
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

        # Notify isli-skills about usage for telemetry (Hygiene)
        # Avoid double-counting if the skill is already hosted by isli-skills (8100)
        SKILLS_SERVICE_URL = os.getenv("SKILL_WEB_FETCH_URL", "http://localhost:8100").rstrip("/")
        if result.is_valid and ":8100" not in base_url:
            async def _notify_usage():
                async with httpx.AsyncClient() as client:
                    token = create_internal_token("core-api", scopes=["skill:telemetry"], expires_minutes=1)
                    await client.post(
                        f"{SKILLS_SERVICE_URL}/skills/{skill_name}/usage",
                        headers={"X-Internal-Auth": token}
                    )
            asyncio.create_task(_notify_usage())

        # Phase 2: Local Skill Cleaning (Signal Harvesting)
        HEAVY_SKILLS = {"web-fetch", "shell-exec", "web-browse-snapshot", "web-browse-vision"}
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
