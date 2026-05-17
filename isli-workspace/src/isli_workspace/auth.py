from typing import Any
from fastapi import HTTPException, Request, status
from jose import JWTError, jwt
from .config import settings

def verify_internal_token(token: str) -> dict[str, Any]:
    if not settings.jwt_secret:
        return {"sub": "system", "scopes": ["*"]}
        
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
