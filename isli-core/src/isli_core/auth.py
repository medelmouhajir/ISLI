from datetime import datetime, timezone, timedelta
from typing import Any

import hashlib
import hmac

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt

from isli_core.config import get_settings

security = HTTPBearer()
security_admin = HTTPBearer()

def verify_webhook_signature(channel: str, request: Request, body: bytes) -> bool:
    settings = get_settings()
    secret = settings.webhook_secrets.get(channel)
    if not secret:
        return True
    signature = request.headers.get("X-Webhook-Signature", "")
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, expected)


def create_internal_token(agent_id: str, scopes: list[str], expires_minutes: int = 60, iat: datetime | None = None) -> str:
    settings = get_settings()
    now = iat if iat is not None else datetime.now(timezone.utc)
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


def verify_session_token(token: str | None = None, credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict[str, Any]:
    """Verify a JWT token from either the Board UI (session) or internal services."""
    token = token or credentials.credentials
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
        # Support both 'internal' (agent-to-core) and 'session' (board-to-core) tokens
        if payload.get("type") not in ("internal", "session"):
            raise JWTError("Invalid token type")
        return payload
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session token",
        ) from exc


async def _check_token_revocation(payload: dict[str, Any]) -> None:
    """Reject the token if it was issued before the agent's current token_issued_at."""
    agent_id = payload.get("sub")
    iat = payload.get("iat")
    if not agent_id or iat is None:
        return

    from sqlalchemy import select
    from isli_core.models import Agent
    from isli_core.db import async_session

    if async_session is None:
        return  # DB not initialized; skip revocation check

    async with async_session() as db:
        result = await db.execute(select(Agent).where(Agent.id == agent_id, Agent.deleted_at.is_(None)))
        agent = result.scalar_one_or_none()
        if not agent:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Agent not found or deleted",
            )
        
        if agent.token_issued_at:
            from datetime import datetime, timezone
            # python-jose encodes iat as integer seconds; truncate DB timestamp to match
            token_iat = int(iat) if isinstance(iat, (int, float)) else int(datetime.fromisoformat(str(iat)).timestamp())
            issued_at_ts = int(agent.token_issued_at.replace(tzinfo=timezone.utc).timestamp())
            if token_iat < issued_at_ts:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token has been revoked (policy violation)",
                )


async def require_internal_auth(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict[str, Any]:
    payload = verify_internal_token(credentials.credentials)
    await _check_token_revocation(payload)
    return payload


async def require_admin_auth(
    credentials: HTTPAuthorizationCredentials = Depends(security_admin),
) -> str:
    settings = get_settings()
    if credentials.credentials != settings.admin_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Admin API Key",
        )
    return credentials.credentials


class SkillProxyAuth:
    """Middleware / dependency to ensure skills only accept requests from Core API proxy."""

    @staticmethod
    def verify(request: Request) -> dict[str, Any]:
        auth = request.headers.get("X-Internal-Auth")
        if not auth:
            # Also accept Authorization: Bearer <token> (agent JWTs)
            bearer = request.headers.get("Authorization", "")
            if bearer.startswith("Bearer "):
                auth = bearer[7:]
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
