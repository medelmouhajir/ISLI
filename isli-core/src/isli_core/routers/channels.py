import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from isli_core.db import get_db
from isli_core.models import ChannelMessage, Task, UserConsent
from isli_core.schemas import validate_event

logger = structlog.get_logger()
router = APIRouter(prefix="/channels", tags=["channels"])

WEBHOOK_SECRETS = {
    "telegram": "telegram-secret",
    "whatsapp": "whatsapp-secret",
}


class WebhookPayload(BaseModel):
    event_type: str
    data: dict[str, Any]


def verify_webhook_signature(channel: str, request: Request, body: bytes) -> bool:
    secret = WEBHOOK_SECRETS.get(channel)
    if not secret:
        return True
    import hmac, hashlib
    signature = request.headers.get("X-Webhook-Signature", "")
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, expected)


@router.post("/{channel}/webhook")
async def channel_webhook(channel: str, request: Request, db: AsyncSession = Depends(get_db)):
    body = await request.body()
    if not verify_webhook_signature(channel, request, body):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    # Idempotency check via Redis or DB (simplified: check dedup key in payload)
    dedup_key = payload.get("dedup_id") or payload.get("message_id")
    if dedup_key:
        existing = await db.execute(
            select(ChannelMessage).where(
                ChannelMessage.raw_payload.contains({"dedup_id": dedup_key})
            )
        )
        if existing.scalar_one_or_none():
            logger.info("channels.dedup_drop", channel=channel, dedup_id=dedup_key)
            return {"status": "deduplicated"}

    # Consent gate
    user_id = payload.get("user_id")
    if user_id:
        consent = await db.execute(
            select(UserConsent).where(
                UserConsent.user_id == user_id,
                UserConsent.channel == channel,
                UserConsent.granted == True,
            )
        )
        if not consent.scalar_one_or_none():
            logger.warning("channels.consent_missing", channel=channel, user_id=user_id)
            raise HTTPException(status_code=403, detail="User consent not granted")

    # Create a task from the webhook
    task = Task(
        title=f"{channel} message",
        type="channel_message",
        status="inbox",
        created_by=user_id or "system",
        input=payload.get("text", ""),
        channel=channel,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    # Store raw channel message
    msg = ChannelMessage(
        session_id=payload.get("session_id", "unknown"),
        sequence_number=payload.get("sequence_number", 0),
        channel=channel,
        direction="inbound",
        content=payload.get("text", ""),
        raw_payload=payload,
    )
    db.add(msg)
    await db.commit()

    logger.info("channels.webhook_ingested", channel=channel, task_id=task.id)
    return {"status": "ok", "task_id": task.id}
