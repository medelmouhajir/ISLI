from fastapi import APIRouter, Depends, HTTPException, Response
from isli_core.auth import require_internal_auth, verify_session_token
from isli_core.redis_blob_client import get_blob_redis
import structlog

logger = structlog.get_logger()
router = APIRouter(prefix="/blobs", tags=["blobs"])

@router.get("/{uuid}")
async def get_blob(
    uuid: str,
):
    """Fetch binary data from the Redis blob store.

    Format of key in Redis is blob:{service}:{uuid}.
    We try known service prefixes until we find it.
    """
    redis = await get_blob_redis()
    
    # Try common prefixes
    blob_key = None
    for service in ["audio", "browser", "agent"]:
        key = f"blob:{service}:{uuid}"
        if await redis.exists(key):
            blob_key = key
            break
    
    if not blob_key:
        # Fallback: check if uuid itself is the full key (unlikely but safe)
        if await redis.exists(uuid):
            blob_key = uuid
        else:
            raise HTTPException(status_code=404, detail="Blob not found or expired")

    data = await redis.get(blob_key)
    if not data:
        raise HTTPException(status_code=404, detail="Blob content is empty")

    # Detect Content-Type
    content_type = "application/octet-stream"
    if "audio" in blob_key:
        content_type = "audio/wav"
    elif "browser" in blob_key or "agent" in blob_key:
        # Default to image/png if we can't detect better, but check magic bytes
        content_type = "image/png"
        if data.startswith(b"\xff\xd8\xff"):
            content_type = "image/jpeg"
        elif data.startswith(b"\x89PNG\r\n\x1a\n"):
            content_type = "image/png"
        elif data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
            content_type = "image/gif"
        elif data.startswith(b"RIFF") and data[8:12] == b"WEBP":
            content_type = "image/webp"
    elif data.startswith(b"\x89PNG\r\n\x1a\n"):
        content_type = "image/png"
    elif data.startswith(b"RIFF") and b"WAVE" in data[:12]:
        content_type = "audio/wav"

    return Response(content=data, media_type=content_type)
