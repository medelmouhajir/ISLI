from datetime import datetime, timezone, timedelta
from typing import Any
from fastapi import HTTPException, Request, status
from jose import JWTError, jwt
from .config import get_settings

def create_internal_token(agent_id: str, scopes: list[str], expires_minutes: int = 60) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": agent_id,
        "scopes": scopes,
        "iat": now,
        "exp": now + timedelta(minutes=expires_minutes),
        "type": "internal",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")

def verify_internal_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    if not settings.jwt_secret:
        if settings.isli_env == "development":
            return {"sub": "system", "scopes": ["*"]}
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="JWT secret not configured",
        )

    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
        if payload.get("type") != "internal":
            raise JWTError("Invalid token type")
        return payload
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired internal token",
        ) from exc

def require_internal_auth(request: Request) -> dict[str, Any]:
    auth = request.headers.get("X-Internal-Auth")
    if not auth:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Internal-Auth header",
        )
    return verify_internal_token(auth)
