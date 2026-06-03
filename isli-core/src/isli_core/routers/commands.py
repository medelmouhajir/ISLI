import json
import traceback
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from isli_core.auth import verify_webhook_signature
from isli_core.db import get_db
from isli_core.models import Session, Agent, Task
from isli_core.jobs.journal_worker import update_session_journal
from isli_core.memory.chroma_client import ChromaMemoryClient
from isli_core.event_manager import EventManager
from isli_core.redis_client import get_redis

logger = structlog.get_logger()
router = APIRouter(prefix="/channels", tags=["commands"])
chroma = ChromaMemoryClient()


class CommandRequest(BaseModel):
    user_id: str | None = None
    agent_id: str
    session_id: str
    command: str
    args: str = ""
    text: str = ""


from isli_core.prompts_loader import get_prompts

HELP_TEXT = get_prompts()["core"]["help_text"]


async def _get_session(db: AsyncSession, session_id: str) -> Session:
    result = await db.execute(
        select(Session).where(Session.id == session_id, Session.deleted_at.is_(None))
    )
    sess = result.scalar_one_or_none()
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    return sess


async def _get_agent(db: AsyncSession, agent_id: str) -> Agent:
    result = await db.execute(
        select(Agent).where(Agent.id == agent_id, Agent.deleted_at.is_(None))
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.post("/{channel}/commands")
async def handle_command(
    channel: str,
    request: Request,
    cmd: CommandRequest,
    db: AsyncSession = Depends(get_db),
):
    body = await request.body()
    if not verify_webhook_signature(channel, request, body):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    command = cmd.command.lstrip("/").lower()
    redis = await get_redis()

    try:
        if command == "help":
            return {"response_text": HELP_TEXT}

        if command == "start":
            return await _handle_start(db, cmd, channel)

        if command == "new":
            return await _handle_new(db, redis, cmd)

        if command == "compact":
            return await _handle_compact(db, cmd)

        if command == "context":
            return await _handle_context(db, cmd)

        if command == "status":
            return await _handle_status(db, cmd)

        if command == "remember":
            return await _handle_remember(db, redis, cmd)

        if command == "forget":
            return await _handle_forget(db, redis, cmd)

        if command == "confirm_forget":
            return await _handle_confirm_forget(redis, cmd)

        if command == "memories":
            return await _handle_memories(db, redis, cmd)

        if command == "retry":
            return await _handle_retry(db, redis, cmd)

        if command == "cancel":
            return await _handle_cancel(db, redis, cmd)

        return {"response_text": f"Unknown command: /{command}\n{HELP_TEXT}"}
    except HTTPException:
        raise
    except Exception as exc:
        tb = traceback.format_exc()
        logger.error("commands.error", command=command, error=str(exc), traceback=tb)
        return {"response_text": f"Error processing /{command}. Please try again."}


async def _handle_start(db: AsyncSession, cmd: CommandRequest, channel: str) -> dict:
    from isli_core.consent import grant_consent
    await grant_consent(db, cmd.user_id, channel, purpose="default")
    await db.commit()

    try:
        agent = await _get_agent(db, cmd.agent_id)
        agent_name = agent.name
    except HTTPException:
        agent_name = "your assistant"

    welcome = (
        f"Welcome! I am {agent_name}.\n\n"
        f"I've enabled your access to this channel. You can now send me messages directly.\n\n"
        "Type /help to see what else I can do."
    )
    return {"response_text": welcome}


async def _handle_new(db: AsyncSession, redis, cmd: CommandRequest) -> dict:
    sess = await _get_session(db, cmd.session_id)
    now = datetime.now(timezone.utc)

    # Wipe old session data so accidental revival is harmless
    sess.messages = []
    sess.journal = None
    sess.journal_updated_at = None
    sess.context_summary = None
    sess.deleted_at = now

    # Generate a new short, globally unique session ID
    new_session_id = str(uuid4())

    new_sess = Session(
        id=new_session_id,
        agent_id=cmd.agent_id,
        user_id=cmd.user_id,
        channel=sess.channel,
        messages=[],
        consent_given=True,
        consent_at=now,
        expires_at=now + timedelta(hours=24),
        status="ready",
        journal=None,
        journal_updated_at=None,
    )
    db.add(new_sess)
    await db.commit()

    logger.info(
        "commands.new_session",
        old_session_id=cmd.session_id,
        new_session_id=new_session_id,
    )
    return {
        "response_text": (
            f"New session started. Previous context cleared.\n"
            f"Session ID: `{new_session_id}`"
        ),
        "new_session_id": new_session_id,
    }


async def _handle_compact(db: AsyncSession, cmd: CommandRequest) -> dict:
    sess = await _get_session(db, cmd.session_id)
    success = await update_session_journal(db, sess, trigger="manual")
    if success:
        return {"response_text": "Session compacted. Journal updated and old messages truncated."}
    return {"response_text": "Nothing to compact — no recent messages to summarize."}


async def _handle_context(db: AsyncSession, cmd: CommandRequest) -> dict:
    sess = await _get_session(db, cmd.session_id)
    journal = sess.journal
    if journal:
        return {"response_text": f"Session journal:\n\n{journal}"}
    return {"response_text": "No journal yet for this session."}


async def _handle_status(db: AsyncSession, cmd: CommandRequest) -> dict:
    sess = await _get_session(db, cmd.session_id)
    agent = await _get_agent(db, cmd.agent_id)
    now = datetime.now(timezone.utc)
    age = now - sess.created_at
    age_str = _format_duration(age)

    msg_count = len(sess.messages or [])
    text = (
        f"Agent: {agent.name}\n"
        f"Model: {agent.model_id or 'unknown'}\n"
        f"Session age: {age_str}\n"
        f"Messages: {msg_count}\n"
        f"Token estimate: {sess.token_count}\n"
        f"Status: {sess.status}"
    )
    return {"response_text": text}


async def _handle_remember(db: AsyncSession, redis, cmd: CommandRequest) -> dict:
    if not cmd.args:
        return {"response_text": "Usage: /remember <text>"}

    from uuid import uuid4
    collection_name = f"agent_{cmd.agent_id}"
    fact_id = str(uuid4())

    await chroma.save_fact(
        collection_name=collection_name,
        fact_id=fact_id,
        content=cmd.args,
        metadata={
            "session_id": cmd.session_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    return {"response_text": f"Remembered: {cmd.args}\n(Fact ID: {fact_id})"}


async def _handle_forget(db: AsyncSession, redis, cmd: CommandRequest) -> dict:
    if not cmd.args:
        return {"response_text": "Usage: /forget <text>"}

    collection_name = f"agent_{cmd.agent_id}"
    try:
        results = await chroma.search_facts(
            collection_name=collection_name,
            query_text=cmd.args,
            limit=3,
        )
    except Exception:
        return {"response_text": "No matching memories found."}

    ids = results.get("ids", [[]])[0]
    docs = results.get("documents", [[]])[0]

    if not ids or not docs:
        return {"response_text": "No matching memories found."}

    top_doc = docs[0]
    top_id = ids[0]

    pending_key = f"pending_forget:{cmd.session_id}"
    await redis.setex(pending_key, 300, json.dumps({"fact_id": top_id, "text": top_doc}))

    return {
        "response_text": (
            f"Did you mean to forget:\n'{top_doc}'\n\n"
            f"Reply /confirm_forget to delete this memory."
        )
    }


async def _handle_confirm_forget(redis, cmd: CommandRequest) -> dict:
    pending_key = f"pending_forget:{cmd.session_id}"
    raw = await redis.get(pending_key)
    if not raw:
        return {"response_text": "No pending forget request. Use /forget <text> first."}

    try:
        pending = json.loads(raw)
        fact_id = pending["fact_id"]
        text = pending["text"]
    except (json.JSONDecodeError, KeyError):
        await redis.delete(pending_key)
        return {"response_text": "Pending forget request was corrupted. Please try again."}

    collection_name = f"agent_{cmd.agent_id}"
    try:
        await chroma.delete_fact(collection_name, fact_id)
    except Exception as exc:
        logger.error("commands.forget_delete_failed", fact_id=fact_id, error=str(exc))
        return {"response_text": "Failed to delete memory. Please try again."}

    await redis.delete(pending_key)
    return {"response_text": f"Forgotten: '{text}'"}


async def _handle_memories(db: AsyncSession, redis, cmd: CommandRequest) -> dict:
    collection_name = f"agent_{cmd.agent_id}"
    try:
        results = await chroma.list_facts(collection_name, limit=20)
    except Exception:
        return {"response_text": "No memories pinned."}

    docs = results.get("documents", [])
    if not docs:
        return {"response_text": "No memories pinned."}

    lines = [f"{i + 1}. {doc}" for i, doc in enumerate(docs)]
    return {"response_text": "Pinned memories:\n" + "\n".join(lines)}


async def _handle_retry(db: AsyncSession, redis, cmd: CommandRequest) -> dict:
    sess = await _get_session(db, cmd.session_id)
    messages = sess.messages or []
    if not messages or messages[-1].get("role") != "user":
        return {"response_text": "Nothing to retry — the last message was already answered."}

    sess.status = "pending_context"
    await db.commit()

    latest_message = messages[-1]
    event_payload = {
        "session_id": sess.id,
        "agent_id": sess.agent_id,
        "user_id": sess.user_id,
        "channel": sess.channel,
        "message": latest_message,
        "messages": messages,
        "context_summary": sess.context_summary,
        "journal": sess.journal,
    }
    await EventManager.emit("session:message", event_payload)

    return {"response_text": "Retrying your last message..."}


async def _handle_cancel(db: AsyncSession, redis, cmd: CommandRequest) -> dict:
    result = await db.execute(
        select(Task).where(
            Task.agent_id == cmd.agent_id,
            Task.session_id == cmd.session_id,
            Task.status == "doing",
            Task.deleted_at.is_(None),
        )
    )
    task = result.scalar_one_or_none()
    if not task:
        return {"response_text": "Nothing to cancel — no in-progress task for this session."}

    from isli_core.locking import increment_task_version
    await increment_task_version(db, task.id, task.version)

    old_status = task.status
    task.status = "failed"
    task.blocked_reason = "Cancelled by user via /cancel"
    task.completed_at = datetime.now(timezone.utc)
    await db.commit()

    # Set Redis flag so agent runner can detect mid-flight cancellation
    await redis.setex(f"task_cancelled:{task.id}", 60, "1")

    await EventManager.emit("task:moved", {
        "task_id": task.id,
        "from": old_status,
        "to": "failed",
    })

    logger.info("commands.task_cancelled", task_id=task.id, session_id=cmd.session_id)
    return {"response_text": f"Task cancelled: {task.title} ({task.id})"}


def _format_duration(td) -> str:
    total_seconds = int(td.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"
