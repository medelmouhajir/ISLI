"""Thin Core client for Keeper PII mesh endpoints."""

import structlog
from typing import Any
import httpx

from isli_core.config import get_settings
from isli_core.auth import create_internal_token

logger = structlog.get_logger()


class PIIKeeperClient:
    """Async client wrapping Keeper /session-prep and /session-prep/rehydrate."""

    def __init__(self, keeper_url: str | None = None):
        self.keeper_url = keeper_url or get_settings().keeper_url

    def _headers(self) -> dict[str, str]:
        token = create_internal_token("core-api", scopes=["keeper:proxy"], expires_minutes=5)
        return {
            "X-Internal-Auth": token,
            "Content-Type": "application/json",
        }

    async def session_prep(
        self,
        session_id: str,
        agent_id: str,
        messages: list[dict[str, Any]],
        context_summary: str,
        mode: str = "full",
        use_slm: bool = True,
        memory_similarity_threshold: float = 0.4,
        agent_config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Call Keeper /session-prep for unified context + PII."""
        payload = {
            "session_id": session_id,
            "agent_id": agent_id,
            "messages": messages,
            "context_summary": context_summary,
            "mode": mode,
            "use_slm": use_slm,
            "memory_similarity_threshold": memory_similarity_threshold,
            "agent_config": agent_config,
        }
        url = f"{self.keeper_url}/session-prep"
        try:
            async with httpx.AsyncClient(timeout=180.0) as client:
                resp = await client.post(url, json=payload, headers=self._headers())
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPStatusError as exc:
            logger.error("pii_keeper_client.session_prep_http_error", status=exc.response.status_code, detail=exc.response.text[:200])
            raise
        except httpx.RequestError as exc:
            logger.error("pii_keeper_client.session_prep_request_error", error=str(exc))
            raise

    async def rehydrate(self, text: str, session_id: str, agent_id: str | None = None) -> str:
        """Call Keeper /session-prep/rehydrate."""
        payload = {
            "text": text,
            "session_id": session_id,
            "agent_id": agent_id,
        }
        url = f"{self.keeper_url}/session-prep/rehydrate"
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(url, json=payload, headers=self._headers())
                resp.raise_for_status()
                data = resp.json()
                return data.get("original_text", text)
        except Exception as exc:
            logger.error("pii_keeper_client.rehydrate_failed", error=str(exc))
            return text
