import os
import structlog
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel

from .telemetry import instrument_fastapi, get_trace_id
from .config import get_settings
from .chunking import MessageChunker
from .attachments import convert_attachment, validate_for_channel
from .rate_limit import RateLimiter
from .offline_queue import OfflineMessageQueue
from .webhook_validation import WebhookValidator
from .identity import CrossChannelIdentity

SERVICE_NAME = "isli-channels"

logger = structlog.get_logger()


try:
    from redis.asyncio import Redis
    from fakeredis.aioredis import FakeRedis
except Exception:
    FakeRedis = None  # type: ignore[misc,assignment]


def _get_redis():
    redis_url = os.getenv("REDIS_URL", "")
    if not redis_url or redis_url.startswith("fakeredis://"):
        if FakeRedis is None:
            raise RuntimeError("fakeredis is not installed")
        return FakeRedis()
    return Redis.from_url(redis_url, decode_responses=True)


redis_client = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis_client
    logger.info("channels.startup", service=SERVICE_NAME)
    redis_client = _get_redis()
    yield
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
    return {"channel": channel, "size_before": size_before, "note": "drain requires a sender callback"}
