from datetime import datetime, timezone, timedelta
from typing import Any

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt

from isli_core.config import get_settings

security = HTTPBearer()


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


async def require_internal_auth(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict[str, Any]:
    return verify_internal_token(credentials.credentials)


class SkillProxyAuth:
    """Middleware / dependency to ensure skills only accept requests from Core API proxy."""

    @staticmethod
    def verify(request: Request) -> dict[str, Any]:
        auth = request.headers.get("X-Internal-Auth")
        if not auth:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing X-Internal-Auth header",
            )
        return verify_internal_token(auth)


def require_scopes(required_scopes: list[str]):
    """Dependency factory that validates JWT scopes."""

    async def _check_scopes(
        credentials: HTTPAuthorizationCredentials = Depends(security),
    ) -> dict[str, Any]:
        payload = verify_internal_token(credentials.credentials)
        token_scopes = set(payload.get("scopes", []))
        if not all(scope in token_scopes for scope in required_scopes):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required scopes: {required_scopes}",
            )
        return payload

    return _check_scopes
