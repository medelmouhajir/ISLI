import os
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel

from .adapters.telegram import TelegramAdapter
from .adapters.whatsapp import WhatsAppAdapter
from .attachments import convert_attachment, validate_for_channel
from .auth import require_internal_auth
from .chunking import MessageChunker
from .offline_queue import OfflineMessageQueue
from .rate_limit import RateLimiter
from .telemetry import get_trace_id, instrument_fastapi
from .webhook_validation import WebhookValidator

SERVICE_NAME = "isli-channels"

logger = structlog.get_logger()
adapters = {}


try:
    from redis.asyncio import Redis
except Exception:
    Redis = None  # type: ignore[misc,assignment]

try:
    from fakeredis.aioredis import FakeRedis
except Exception:
    FakeRedis = None  # type: ignore[misc,assignment]


def _get_redis():
    redis_url = os.getenv("REDIS_URL", "")
    if not redis_url or redis_url.startswith("fakeredis://"):
        if FakeRedis is None:
            raise RuntimeError("fakeredis is not installed")
        return FakeRedis()
    if Redis is None:
        raise RuntimeError("redis is not installed")
    return Redis.from_url(redis_url, decode_responses=True)


redis_client = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis_client, adapters
    logger.info("channels.startup", service=SERVICE_NAME)
    redis_client = _get_redis()

    # Initialize Adapters
    tg_token = os.getenv("TELEGRAM_BOT_TOKEN")
    core_url = os.getenv("CORE_API_URL", "http://localhost:8000")
    webhook_secret = os.getenv("WEBHOOK_SECRET", "")
    if tg_token:
        audio_url = os.getenv("AUDIO_URL", "")
        jwt_secret = os.getenv("JWT_SECRET", "")
        tg_adapter = TelegramAdapter(
            tg_token,
            core_url,
            webhook_secret,
            redis_client=redis_client,
            audio_url=audio_url,
            jwt_secret=jwt_secret,
        )
        await tg_adapter.start()
        adapters["telegram"] = tg_adapter

    if os.getenv("WHATSAPP_ENABLED", "").lower() in ("true", "1", "yes"):
        wa_sidecar_url = os.getenv("WHATSAPP_SIDECAR_URL", "http://whatsapp-sidecar:3001")
        wa_adapter = WhatsAppAdapter(
            core_api_url=core_url,
            webhook_secret=webhook_secret,
            redis_client=redis_client,
            sidecar_url=wa_sidecar_url,
            sidecar_api_token=os.getenv("SIDECAR_API_TOKEN", ""),
            sidecar_webhook_secret=os.getenv("SIDECAR_WEBHOOK_SECRET", ""),
        )
        await wa_adapter.start()
        adapters["whatsapp"] = wa_adapter

    yield
    for adapter in adapters.values():
        await adapter.stop()
    logger.info("channels.shutdown", service=SERVICE_NAME)


app = FastAPI(
    title="ISLI Channels",
    version="0.1.0",
    lifespan=lifespan,
)
instrument_fastapi(app, SERVICE_NAME)


@app.get("/health")
async def health():
    trace_id = get_trace_id()
    return {"status": "ok", "service": SERVICE_NAME, "trace_id": trace_id}


@app.get("/ready")
async def ready():
    global redis_client
    try:
        if redis_client:
            await redis_client.ping()
        return {"status": "ready", "service": SERVICE_NAME, "redis": "ok"}
    except Exception as exc:
        return {"status": "not_ready", "service": SERVICE_NAME, "redis": "fail", "error": str(exc)}


@app.get("/live")
async def live():
    return {"status": "alive", "service": SERVICE_NAME}


@app.post("/chunk")
async def chunk_message(payload: dict[str, Any]):
    text = payload.get("text", "")
    channel = payload.get("channel", "web")
    chunks = MessageChunker.chunk(text, channel)
    return {"channel": channel, "chunks": chunks}


@app.post("/validate-attachment")
async def validate_attachment(payload: dict[str, Any]):
    media_type = payload.get("mime_type", "")
    size_bytes = payload.get("size_bytes", 0)
    channel = payload.get("channel", "web")
    try:
        validate_for_channel(media_type, size_bytes, channel)
        return {"valid": True, "channel": channel}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/convert-attachment")
async def convert_attachment_endpoint(payload: dict[str, Any]):
    attachment = payload.get("attachment", {})
    target_channel = payload.get("target_channel", "web")
    try:
        result = convert_attachment(attachment, target_channel)
        return {"converted": result}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


class RateLimitCheck(BaseModel):
    channel: str


@app.post("/rate-limit/check")
async def rate_limit_check(body: RateLimitCheck):
    global redis_client
    limiter = RateLimiter(redis_client)
    is_limited = await limiter.is_limited(body.channel)
    return {"channel": body.channel, "limited": is_limited}


@app.post("/offline-queue/drain")
async def drain_offline_queue(payload: dict[str, Any]):
    global redis_client
    channel = payload.get("channel", "")
    queue = OfflineMessageQueue(redis_client)
    size_before = await queue.size(channel)
    # Note: sender function would be injected in production
    return {
        "channel": channel,
        "size_before": size_before,
        "note": "drain requires a sender callback",
    }


@app.post("/webhook/telegram/{agent_id}")
async def telegram_webhook(agent_id: str, request: Request):
    if "telegram" not in adapters:
        raise HTTPException(status_code=501, detail="Telegram adapter not initialized")

    raw_update = await request.json()
    return await adapters["telegram"].handle_webhook(raw_update, agent_id)


class SendMessageRequest(BaseModel):
    channel: str
    channel_user_id: str
    text: str
    agent_id: str | None = None
    metadata: dict[str, Any] = {}
    audio_b64: str | None = None
    attachments: list[dict[str, Any]] = []


@app.post("/send")
async def send_message(
    req: SendMessageRequest,
    auth: dict[str, Any] = Depends(require_internal_auth),  # noqa: B008
) -> dict[str, Any]:
    adapter = adapters.get(req.channel)
    if not adapter:
        raise HTTPException(status_code=400, detail=f"No adapter for channel: {req.channel}")

    success = await adapter.send_message(
        req.channel_user_id,
        req.text,
        agent_id=req.agent_id,
        audio_b64=req.audio_b64,
        attachments=req.attachments,
    )
    return {"success": success}


# --- WhatsApp session management endpoints ---


def _get_whatsapp_adapter() -> WhatsAppAdapter:
    adapter = adapters.get("whatsapp")
    if not adapter:
        raise HTTPException(status_code=501, detail="WhatsApp adapter not initialized")
    if not isinstance(adapter, WhatsAppAdapter):
        raise HTTPException(status_code=500, detail="WhatsApp adapter type mismatch")
    return adapter


@app.post("/whatsapp/sessions/{agent_id}")
async def whatsapp_create_session(agent_id: str):
    wa = _get_whatsapp_adapter()
    result = await wa.create_session(agent_id)
    if result.get("status") == "already_connected":
        raise HTTPException(status_code=409, detail="Agent already has an active WhatsApp session")
    return result


@app.get("/whatsapp/sessions/{agent_id}/qr")
async def whatsapp_get_qr(agent_id: str):
    wa = _get_whatsapp_adapter()
    return wa.get_qr(agent_id)


@app.get("/whatsapp/sessions/{agent_id}/status")
async def whatsapp_get_status(agent_id: str):
    wa = _get_whatsapp_adapter()
    return wa.get_status(agent_id)


@app.delete("/whatsapp/sessions/{agent_id}")
async def whatsapp_delete_session(agent_id: str):
    wa = _get_whatsapp_adapter()
    return await wa.delete_session(agent_id)


@app.get("/whatsapp/sessions")
async def whatsapp_list_sessions():
    wa = _get_whatsapp_adapter()
    return {"sessions": wa.list_sessions()}


@app.post("/webhook/whatsapp/{agent_id}")
async def whatsapp_sidecar_webhook(agent_id: str, request: Request):
    if "whatsapp" not in adapters:
        raise HTTPException(status_code=501, detail="WhatsApp adapter not initialized")

    wa = adapters["whatsapp"]
    if wa.sidecar_webhook_secret:
        await WebhookValidator.verify_generic(
            request, wa.sidecar_webhook_secret, "X-Sidecar-Secret"
        )

    payload = await request.json()
    try:
        await adapters["whatsapp"].handle_webhook(agent_id, payload)
    except HTTPException:
        raise
    except Exception as exc:
        # Log full details, then return a 500 so the sidecar retries on transient errors.
        # 403 consent-missing is handled gracefully inside the adapter (auto-reply sent).
        logger.error(
            "whatsapp.webhook_handler_failed",
            agent_id=agent_id,
            error=str(exc),
        )
        raise HTTPException(status_code=500, detail="Webhook processing failed")
    return {"status": "ok"}
