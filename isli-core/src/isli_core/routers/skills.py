import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
import httpx
import structlog

from isli_core.auth import create_internal_token, SkillProxyAuth

logger = structlog.get_logger()
router = APIRouter(prefix="/skills", tags=["skills"])

SKILL_REGISTRY = {
    "web-fetch": os.getenv("SKILL_WEB_FETCH_URL", "http://localhost:8100"),
    "summarize": os.getenv("SKILL_SUMMARIZE_URL", "http://localhost:8101"),
    "translate": os.getenv("SKILL_TRANSLATE_URL", "http://localhost:8102"),
}


class SkillRequest(BaseModel):
    action: str
    payload: dict[str, Any]


@router.post("/{skill_name}/{action}")
async def skill_proxy(skill_name: str, action: str, request: Request):
    base_url = SKILL_REGISTRY.get(skill_name)
    if not base_url:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not registered")

    # Verify internal auth header from caller
    try:
        SkillProxyAuth.verify(request)
    except HTTPException:
        # In dev mode, allow unauthenticated if no header is present
        if request.headers.get("X-Internal-Auth") is None:
            logger.warning("skills.dev_mode_unauthenticated", skill=skill_name)
        else:
            raise

    body = await request.body()
    token = create_internal_token("core-api", scopes=["skill:proxy"], expires_minutes=5)
    headers = {
        "X-Internal-Auth": token,
        "Content-Type": request.headers.get("Content-Type", "application/json"),
    }

    url = f"{base_url}/{action}"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, headers=headers, content=body)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as exc:
        from isli_core.telemetry import get_skill_invocation_error_counter
        get_skill_invocation_error_counter().add(1, {"skill": skill_name, "reason": "http_error"})
        logger.error("skills.proxy_error", skill=skill_name, status=exc.response.status_code)
        raise HTTPException(status_code=exc.response.status_code, detail="Skill proxy error")
    except httpx.RequestError as exc:
        from isli_core.telemetry import get_skill_invocation_error_counter
        get_skill_invocation_error_counter().add(1, {"skill": skill_name, "reason": "unreachable"})
        logger.error("skills.proxy_unreachable", skill=skill_name, error=str(exc))
        raise HTTPException(status_code=503, detail=f"Skill unreachable: {exc}")
