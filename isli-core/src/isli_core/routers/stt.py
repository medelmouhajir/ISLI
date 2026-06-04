import base64
import structlog
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
import httpx

from isli_core.auth import create_internal_token, require_admin_auth
from isli_core.config import get_settings

logger = structlog.get_logger()
router = APIRouter(prefix="/stt", tags=["stt"])


@router.post("/transcribe")
async def stt_transcribe(
    audio: UploadFile = File(...),
    language: str = Form("auto"),
    admin: str = Depends(require_admin_auth),
) -> dict[str, Any]:
    """Transcribe uploaded audio to text using the local audio service (Whisper STT).

    Accepts multipart/form-data audio upload (e.g., webm, wav, mp3) and returns
    the transcribed text, detected language, and confidence.
    """
    settings = get_settings()
    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio file")

    # Encode audio as base64 JSON payload for the audio service
    audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
    payload = {
        "audio_b64": audio_b64,
        "language": language,
    }

    token = create_internal_token("core-api", scopes=["stt:transcribe"], expires_minutes=5)
    headers = {
        "X-Internal-Auth": token,
        "Content-Type": "application/json",
    }

    audio_url = settings.audio_url.rstrip("/")
    url = f"{audio_url}/stt/transcribe"

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as exc:
        logger.error(
            "stt.http_error",
            url=url,
            status=exc.response.status_code,
            detail=exc.response.text,
        )
        raise HTTPException(
            status_code=exc.response.status_code,
            detail=f"STT service error: {exc.response.text}",
        ) from exc
    except httpx.RequestError as exc:
        logger.error("stt.request_error", url=url, error=str(exc))
        raise HTTPException(
            status_code=503,
            detail=f"STT service unreachable: {exc}",
        ) from exc
    except Exception as exc:
        logger.error("stt.unexpected_error", url=url, error=str(exc))
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected STT error: {exc}",
        ) from exc
