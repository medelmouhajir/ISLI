import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import structlog

from .telemetry import instrument_fastapi, get_trace_id
from .config import get_settings
from .ollama_client import OllamaClient
from .fallback import KeeperFallback

SERVICE_NAME = "isli-keeper"

logger = structlog.get_logger()

DEFAULT_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
DEFAULT_GEN_MODEL = os.getenv("OLLAMA_GEN_MODEL", "qwen3:1.7b")

fallback = KeeperFallback()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("keeper.startup", service=SERVICE_NAME)
    yield
    logger.info("keeper.shutdown", service=SERVICE_NAME)


app = FastAPI(
    title="ISLI Keeper",
    version="0.1.0",
    lifespan=lifespan,
)
instrument_fastapi(app, SERVICE_NAME)


class EmbedRequest(BaseModel):
    input: str
    model: str = DEFAULT_EMBED_MODEL


class SummarizeRequest(BaseModel):
    text: str
    max_length: int = 256


class GenerateRequest(BaseModel):
    prompt: str
    model: str = DEFAULT_GEN_MODEL
    options: dict[str, Any] | None = None


class HeartbeatRequest(BaseModel):
    agent_id: str
    status: str
    anomaly: str | None = None


@app.get("/health")
async def health():
    trace_id = get_trace_id()
    return {"status": "ok", "service": SERVICE_NAME, "trace_id": trace_id}


@app.get("/ready")
async def ready():
    ollama_ok = False
    try:
        async with OllamaClient().session() as client:
            await client.list_models()
        ollama_ok = True
    except Exception as exc:
        logger.warning("keeper.ollama_not_ready", error=str(exc))

    fallback_ready = bool(os.getenv("ANTHROPIC_API_KEY") or os.getenv("OPENAI_API_KEY"))
    return {
        "status": "ready" if ollama_ok else "degraded",
        "service": SERVICE_NAME,
        "ollama": "ok" if ollama_ok else "fail",
        "fallback_configured": fallback_ready,
    }


@app.get("/live")
async def live():
    return {"status": "alive", "service": SERVICE_NAME}


@app.post("/embed")
async def embed(req: EmbedRequest):
    try:
        async with OllamaClient().session() as client:
            embedding = await client.embed(req.model, req.input)
        return {"embedding": embedding, "model": req.model}
    except Exception as exc:
        logger.error("keeper.embed_failed", error=str(exc))
        raise HTTPException(status_code=503, detail=str(exc))


@app.post("/summarize")
async def summarize(req: SummarizeRequest):
    prompt = f"Summarize the following text in under {req.max_length} words:\n\n{req.text}\n\nSummary:"
    try:
        result = await fallback.generate(prompt, model=DEFAULT_GEN_MODEL)
        summary = result.get("response", result.get("response", ""))
        return {"summary": summary, "model": DEFAULT_GEN_MODEL}
    except Exception as exc:
        logger.error("keeper.summarize_failed", error=str(exc))
        raise HTTPException(status_code=503, detail=str(exc))


@app.post("/generate")
async def generate(req: GenerateRequest):
    try:
        result = await fallback.generate(req.prompt, model=req.model)
        return result
    except Exception as exc:
        logger.error("keeper.generate_failed", error=str(exc))
        raise HTTPException(status_code=503, detail=str(exc))


@app.get("/models")
async def list_models():
    try:
        async with OllamaClient().session() as client:
            models = await client.list_models()
        return {"models": models}
    except Exception as exc:
        logger.error("keeper.list_models_failed", error=str(exc))
        raise HTTPException(status_code=503, detail=str(exc))


@app.post("/heartbeat")
async def heartbeat(req: HeartbeatRequest):
    if req.anomaly:
        logger.warning("keeper.agent_anomaly", agent_id=req.agent_id, anomaly=req.anomaly)
    logger.info("keeper.heartbeat", agent_id=req.agent_id, status=req.status)
    return {"status": "ok", "agent_id": req.agent_id, "validated": True}
