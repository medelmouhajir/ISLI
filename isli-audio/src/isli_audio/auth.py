import time
from typing import Any

import structlog
from fastapi import Depends, HTTPException, Request

from isli_audio.config import get_settings

logger = structlog.get_logger()


def _verify_internal_auth(request: Request) -> dict[str, Any]:
    """Verify X-Internal-Auth JWT token."""
    from jose import JWTError, jwt
    token = request.headers.get("X-Internal-Auth")
    if not token:
        raise HTTPException(status_code=401, detail="Missing X-Internal-Auth header")
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
        return payload
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


async def require_internal_auth(request: Request) -> dict[str, Any]:
    return _verify_internal_auth(request)
