import base64
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

import structlog
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel

from isli_audio.auth import require_internal_auth
from isli_audio.config import get_settings
from isli_audio.model_manager import AudioModelManager
from isli_audio.stt_engine import get_stt_engine
from isli_audio.telemetry import AudioMetrics, get_metrics, instrument_fastapi
from isli_audio.tts_engine import get_tts_engine

SERVICE_NAME = "isli-audio"
logger = structlog.get_logger()

model_manager = AudioModelManager()
stt_engine = get_stt_engine()
tts_engine = get_tts_engine()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("audio.startup", service=SERVICE_NAME)
    # Pre-load default models
    try:
        stt_engine.load(model_manager.get_model("stt"))
        logger.info("audio.stt_default_loaded", model=model_manager.get_model("stt"))
    except Exception as exc:
        logger.warning("audio.stt_default_load_failed", error=str(exc))
    try:
        voice = model_manager.get_tts_voice_for_language()
        if tts_engine.is_downloaded(voice):
            tts_engine.load(voice)
            logger.info("audio.tts_default_loaded", voice=voice)
        else:
            logger.info("audio.tts_default_not_downloaded", voice=voice)
    except Exception as exc:
        logger.warning("audio.tts_default_load_failed", error=str(exc))
    yield
    logger.info("audio.shutdown", service=SERVICE_NAME)


app = FastAPI(
    title="ISLI Audio Service",
    version="0.1.0",
    lifespan=lifespan,
)
instrument_fastapi(app, SERVICE_NAME)


# ─── Request Models ───

class TranscribeRequest(BaseModel):
    audio_b64: str | None = None
    audio_ref: str | None = None
    language: str = "auto"


class SynthesizeRequest(BaseModel):
    text: str
    voice: str | None = None
    language: str | None = None


class ActivateRequest(BaseModel):
    slot: str
    model_name: str
    language: str | None = None


class PullRequest(BaseModel):
    slot: str
    model_name: str
    language: str | None = None


class RemoveRequest(BaseModel):
    model_name: str
    slot: str


# ─── Health ───

@app.get("/health")
async def health():
    return {"status": "ok", "service": SERVICE_NAME}


@app.get("/ready")
async def ready():
    stt_ok = stt_engine._model is not None
    tts_voice = model_manager.get_tts_voice_for_language()
    tts_ok = tts_engine.is_downloaded(tts_voice) and tts_engine._synthesizer is not None
    return {
        "status": "ready" if (stt_ok and tts_ok) else "degraded",
        "service": SERVICE_NAME,
        "stt": "ok" if stt_ok else "not_loaded",
        "tts": "ok" if tts_ok else "not_loaded",
    }


# ─── STT ───

@app.post("/stt/transcribe")
async def stt_transcribe(
    request: Request,
    audio: UploadFile | None = File(None),
    language: str = Form("auto"),
    audio_ref: str | None = Form(None),
    auth: dict = Depends(require_internal_auth),
):
    """Transcribe audio to text. Supports multipart upload, JSON base64, or blob reference."""
    metrics = get_metrics()
    metrics.start_request()
    start = time.monotonic()

    audio_bytes = None

    # 1. Check for audio_ref (Redis blob)
    if audio_ref:
        from isli_audio.redis_client import get_blob_redis
        redis = await get_blob_redis()
        audio_bytes = await redis.get(audio_ref)
        if not audio_bytes:
            logger.warning("audio.stt_ref_not_found", ref=audio_ref)
            raise HTTPException(status_code=404, detail=f"Audio reference not found: {audio_ref}")
        logger.info("audio.stt_ref_loaded", ref=audio_ref, size=len(audio_bytes))

    # 2. Check for multipart file upload
    elif audio is not None:
        audio_bytes = await audio.read()

    # 3. Check for JSON body (audio_b64 or audio_ref)
    else:
        body = await request.body()
        if body:
            try:
                data = TranscribeRequest.model_validate_json(body)
                if data.audio_ref:
                    from isli_audio.redis_client import get_blob_redis
                    redis = await get_blob_redis()
                    audio_bytes = await redis.get(data.audio_ref)
                    if not audio_bytes:
                        raise HTTPException(status_code=404, detail="Audio reference not found in store")
                elif data.audio_b64:
                    audio_bytes = base64.b64decode(data.audio_b64)
            except HTTPException:
                raise
            except Exception as exc:
                logger.error("audio.stt_request_parse_failed", error=str(exc))
                raise HTTPException(status_code=400, detail="Invalid JSON body; provide multipart, audio_b64, or audio_ref")

    if not audio_bytes:
        raise HTTPException(status_code=400, detail="No audio provided")

    model_name = model_manager.get_model("stt")
    try:
        result = stt_engine.transcribe(audio_bytes, model_name, language=language)
        latency = (time.monotonic() - start) * 1000
        metrics.record_inference(
            endpoint="stt",
            model=model_name,
            latency_ms=latency,
            status="success",
        )
        return {
            "text": result["text"],
            "language": result["language"],
            "confidence": result["confidence"],
            "model": model_name,
        }
    except Exception as exc:
        latency = (time.monotonic() - start) * 1000
        metrics.record_inference(
            endpoint="stt",
            model=model_name,
            latency_ms=latency,
            status="error",
            error=str(exc),
        )
        logger.error("audio.stt_transcribe_failed", error=str(exc))
        raise HTTPException(status_code=503, detail=f"STT failed: {exc}")
    finally:
        metrics.end_request()


# ─── TTS ───

@app.post("/tts/synthesize")
async def tts_synthesize(
    req: SynthesizeRequest,
    auth: dict = Depends(require_internal_auth),
):
    """Synthesize text to speech audio. Returns a blob reference."""
    import uuid
    metrics = get_metrics()
    metrics.start_request()
    start = time.monotonic()

    voice_name = req.voice or model_manager.get_tts_voice_for_language(req.language)

    # Auto-download if missing
    if not tts_engine.is_downloaded(voice_name):
        try:
            await tts_engine.download(voice_name)
        except Exception as exc:
            logger.error("audio.tts_download_failed", voice=voice_name, error=str(exc))
            raise HTTPException(status_code=503, detail=f"Failed to download TTS voice: {exc}")

    try:
        # result contains "audio_b64" (as bytes-like)
        result = tts_engine.synthesize(req.text, voice_name)
        
        # Strip Base64 and store raw bytes in Redis
        wav_bytes = base64.b64decode(result["audio_b64"])
        blob_id = str(uuid.uuid4())
        blob_key = f"blob:audio:{blob_id}"
        
        from isli_audio.redis_client import get_blob_redis
        redis = await get_blob_redis()
        await redis.setex(blob_key, 86400, wav_bytes) # 24h TTL
        
        latency = (time.monotonic() - start) * 1000
        metrics.record_inference(
            endpoint="tts",
            model=voice_name,
            latency_ms=latency,
            status="success",
        )
        
        return {
            "audio_ref": blob_key,
            "format": result["format"],
            "sample_rate": result["sample_rate"],
            "duration_ms": result["duration_ms"],
            "voice": voice_name,
        }
    except Exception as exc:
        latency = (time.monotonic() - start) * 1000
        metrics.record_inference(
            endpoint="tts",
            model=voice_name,
            latency_ms=latency,
            status="error",
            error=str(exc),
        )
        logger.error("audio.tts_synthesize_failed", error=str(exc))
        raise HTTPException(status_code=503, detail=f"TTS failed: {exc}")
    finally:
        metrics.end_request()


# ─── Admin ───

@app.get("/admin/config")
async def admin_config(auth: dict = Depends(require_internal_auth)):
    return {
        "config": {
            "stt": model_manager.get_model("stt"),
            "tts": model_manager.get_model("tts"),
            "language": model_manager.get_model("language"),
            "tts_voices_by_language": model_manager.config.get("tts_voices_by_language", {}),
        }
    }


@app.post("/admin/activate")
async def admin_activate(
    req: ActivateRequest,
    auth: dict = Depends(require_internal_auth),
):
    if req.slot not in ("stt", "tts", "language"):
        raise HTTPException(status_code=400, detail=f"Invalid slot: {req.slot}")

    # Validate the model/voice exists (for TTS, check download; for STT, check known sizes)
    if req.slot == "stt":
        valid_sizes = {"tiny", "base", "small", "medium", "large-v3"}
        size = req.model_name.replace("whisper-", "")
        if size not in valid_sizes and req.model_name != "whisper-base-darija":
            raise HTTPException(status_code=400, detail=f"Unknown STT model: {req.model_name}")
        # Pre-load so it's ready
        try:
            stt_engine.load(req.model_name)
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Failed to load STT model: {exc}")

    elif req.slot == "tts":
        if not tts_engine.is_downloaded(req.model_name):
            raise HTTPException(status_code=404, detail=f"TTS voice not downloaded: {req.model_name}")
        try:
            tts_engine.load(req.model_name)
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Failed to load TTS voice: {exc}")

    model_manager.set_model(req.slot, req.model_name)
    return {"status": "ok", "slot": req.slot, "model": req.model_name}


@app.post("/admin/pull")
async def admin_pull(
    req: PullRequest,
    auth: dict = Depends(require_internal_auth),
):
    if req.slot == "stt":
        # For STT, faster-whisper downloads on first use via load(). We just verify it's valid.
        valid_sizes = {"tiny", "base", "small", "medium", "large-v3"}
        size = req.model_name.replace("whisper-", "")
        if size not in valid_sizes and req.model_name != "whisper-base-darija":
            raise HTTPException(status_code=400, detail=f"Unknown STT model: {req.model_name}")
        try:
            stt_engine.load(req.model_name)
            model_manager.set_model("stt", req.model_name)
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Failed to pull STT model: {exc}")

    elif req.slot == "tts":
        try:
            await tts_engine.download(req.model_name)
            model_manager.set_model("tts", req.model_name)
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Failed to pull TTS voice: {exc}")

    else:
        raise HTTPException(status_code=400, detail=f"Invalid slot: {req.slot}")

    return {"status": "ok", "slot": req.slot, "model": req.model_name}


@app.post("/admin/remove")
async def admin_remove(
    req: RemoveRequest,
    auth: dict = Depends(require_internal_auth),
):
    settings = get_settings()

    if req.slot == "stt":
        import shutil
        model_dir = f"{settings.models_dir}/whisper"
        if os.path.exists(model_dir):
            shutil.rmtree(model_dir, ignore_errors=True)
        # Reset to default
        model_manager.set_model("stt", settings.audio_stt_model)
        stt_engine._model = None
        stt_engine._loaded_size = ""
        return {"status": "ok", "removed": req.model_name, "slot": "stt"}

    elif req.slot == "tts":
        voice_dir = tts_engine._voice_dir(req.model_name)
        if os.path.exists(voice_dir):
            for f in os.listdir(voice_dir):
                if f.startswith(req.model_name):
                    os.remove(os.path.join(voice_dir, f))
        # Reset to default if this was active
        if model_manager.get_model("tts") == req.model_name:
            model_manager.set_model("tts", settings.audio_tts_model)
        tts_engine._synthesizer = None
        tts_engine._loaded_voice = ""
        return {"status": "ok", "removed": req.model_name, "slot": "tts"}

    else:
        raise HTTPException(status_code=400, detail=f"Invalid slot: {req.slot}")


# ─── Models listing ───

@app.get("/models")
async def list_models(auth: dict = Depends(require_internal_auth)):
    """List available/downloaded audio models."""
    settings = get_settings()

    stt_models = []
    whisper_dir = f"{settings.models_dir}/whisper"
    if os.path.exists(whisper_dir):
        for size in ["tiny", "base", "small", "medium", "large-v3"]:
            # faster-whisper creates subdirs like models--Systran--faster-whisper-...
            # We just report what sizes have been downloaded
            stt_models.append(f"whisper-{size}")
        if os.path.exists(os.path.join(whisper_dir, "whisper-base-darija", "model.bin")):
            stt_models.append("whisper-base-darija")

    tts_voices = []
    piper_dir = f"{settings.models_dir}/piper"
    if os.path.exists(piper_dir):
        for root, dirs, files in os.walk(piper_dir):
            for f in files:
                if f.endswith(".onnx") and not f.endswith(".json"):
                    voice_name = f.replace(".onnx", "")
                    tts_voices.append(voice_name)

    return {
        "stt": stt_models,
        "tts": tts_voices,
    }


# ─── Dashboard ───

@app.get("/dashboard")
async def dashboard(auth: dict = Depends(require_internal_auth)):
    metrics = get_metrics()
    snapshot = metrics.get_snapshot()

    uptime_seconds = round(time.monotonic() - getattr(metrics, "_start_time", time.monotonic()), 2)
    if not hasattr(metrics, "_start_time"):
        uptime_seconds = 0

    return {
        "identity": {
            "service": SERVICE_NAME,
            "default_stt_model": model_manager.get_model("stt"),
            "default_tts_voice": model_manager.get_model("tts"),
            "language": model_manager.get_model("language"),
        },
        "health": {
            "status": "ready",
            "uptime_seconds": uptime_seconds,
            "active_requests": snapshot["active_requests"],
        },
        "stats": {
            "total_requests": snapshot["total_requests"],
            "inference_counts": snapshot["inference_counts"],
            "avg_latency_ms": snapshot["avg_latency_ms"],
            "error_counts": snapshot["error_counts"],
        },
        "recent_inferences": snapshot["recent_inferences"],
        "config": {
            "stt": model_manager.get_model("stt"),
            "tts": model_manager.get_model("tts"),
            "language": model_manager.get_model("language"),
        },
    }
