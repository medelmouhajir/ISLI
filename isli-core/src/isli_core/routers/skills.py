import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
import httpx
import structlog

from isli_core.auth import create_internal_token, SkillProxyAuth
from isli_core.security.content_scanner import ContentScanner
from isli_core.security.policy_engine import PolicyEngine
from isli_core.db import get_db
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()
router = APIRouter(prefix="/skills", tags=["skills"])

SKILL_REGISTRY = {
    "web-fetch": os.getenv("SKILL_WEB_FETCH_URL", "http://localhost:8100"),
    "summarize": os.getenv("SKILL_SUMMARIZE_URL", "http://localhost:8101"),
    "translate": os.getenv("SKILL_TRANSLATE_URL", "http://localhost:8102"),
    "shell-exec": os.getenv("SKILL_SHELL_EXEC_URL", "http://localhost:8103"),
}


class SkillRequest(BaseModel):
    action: str
    payload: dict[str, Any]


@router.post("/{skill_name}/{action}")
async def skill_proxy(
    skill_name: str,
    action: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
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

    # Content scan on the raw body text
    body_text = body.decode("utf-8", errors="ignore") if body else ""
    scan = ContentScanner.scan(body_text)
    if scan.blocked:
        raise HTTPException(status_code=403, detail=f"Content safety block: {scan.reason}")

    # Policy evaluation for skill invocation
    decision = await PolicyEngine.evaluate(
        db,
        user_id="anonymous",
        input_text=body_text,
        agent_id=None,
        skill_name=skill_name,
        model_id=None,
        budget_exceeded=False,
        estop_active=False,
    )
    if not decision.allow:
        detail: dict[str, Any] = {
            "detail": f"Policy block: {decision.reason}",
            "policy_decision": {
                "allow": decision.allow,
                "reason": decision.reason,
                "risk_score": decision.risk_score,
                "overrideable": decision.overrideable,
                "rule": decision.rule,
                "context_hash": decision.context_hash,
            },
        }
        if decision.overrideable:
            detail["override_request_url"] = "/v1/security/override-request"
        raise HTTPException(status_code=403, detail=detail)
    token = create_internal_token("core-api", scopes=["skill:proxy"], expires_minutes=5)
    headers = {
        "X-Internal-Auth": token,
        "Content-Type": request.headers.get("Content-Type", "application/json"),
    }

    from isli_core.verification.grounding import GroundingVerifier
    from isli_core.telemetry import get_verification_failure_counter

    url = f"{base_url}/{action}"

    async def _call_skill() -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, headers=headers, content=body)
            resp.raise_for_status()
            return resp.json()

    try:
        raw, result = await GroundingVerifier.verify_with_retry(
            skill_name, _call_skill, max_retries=3
        )
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

    if not result.is_valid:
        get_verification_failure_counter().add(1, {"skill": skill_name, "reason": result.reason})
        logger.error("skills.verification_failed", skill=skill_name, reason=result.reason)
        raise HTTPException(
            status_code=502,
            detail={"success": False, "error": result.reason, "skill": skill_name},
        )

    return raw
