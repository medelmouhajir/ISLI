"""PII Mesh client for the Agent Runner — talks to Keeper /session-prep."""

import os
import re
from typing import Any

import structlog

logger = structlog.get_logger()

# Regex patterns for fast local pre-filter
PII_PATTERNS = {
    "email": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
    "phone": r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b",
    "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
    "credit_card": r"\b(?:\d{4}[-\s]?){3}\d{4}\b",
    "dob": r"\b\d{2}/\d{2}/\d{4}\b",
    "corp_id": r"\b[A-Z]{2,4}-\d{4,8}\b",
}


class PIIKeeperClient:
    """Async client wrapping Keeper /session-prep and local re-hydration."""

    def __init__(self, keeper_url: str | None = None):
        self.keeper_url = keeper_url or os.getenv("KEEPER_URL", "http://localhost:8001")
        self._local_token_maps: dict[str, dict[str, str]] = {}

    @staticmethod
    def regex_hits(text: str) -> dict[str, list[str]]:
        """Fast local regex scan. Returns empty dict if no PII detected."""
        found: dict[str, list[str]] = {}
        for category, pattern in PII_PATTERNS.items():
            matches = list(set(re.findall(pattern, text)))
            if matches:
                found[category] = matches
        return found

    def cache_token_map(self, session_id: str, token_map: dict[str, str]) -> None:
        """Merge incoming token_map into the local session cache."""
        existing = self._local_token_maps.get(session_id, {})
        existing.update(token_map)
        self._local_token_maps[session_id] = existing

    def rehydrate_local(self, text: str, session_id: str) -> str:
        """Zero-latency local re-hydration using cached token_map."""
        token_map = self._local_token_maps.get(session_id, {})
        if not token_map:
            return text
        # Sort by token length descending to avoid partial replacements
        for token, original in sorted(token_map.items(), key=lambda x: len(x[0]), reverse=True):
            text = text.replace(token, original)
        return text

    def session_has_tokens(self, session_id: str) -> bool:
        return bool(self._local_token_maps.get(session_id))

    async def session_prep(
        self,
        session_id: str,
        agent_id: str,
        messages: list[dict[str, Any]],
        context_summary: str,
        mode: str = "pii_only",
        use_slm: bool = True,
    ) -> dict[str, Any]:
        """Call Keeper /session-prep."""
        import httpx
        from .auth import create_internal_token

        payload = {
            "session_id": session_id,
            "agent_id": agent_id,
            "messages": messages,
            "context_summary": context_summary,
            "mode": mode,
            "use_slm": use_slm,
        }
        token = create_internal_token(agent_id, scopes=["keeper:proxy"], expires_minutes=5)
        headers = {
            "X-Internal-Auth": token,
            "Content-Type": "application/json",
        }
        url = f"{self.keeper_url}/session-prep"
        try:
            async with httpx.AsyncClient(timeout=180.0) as client:
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPStatusError as exc:
            logger.error("pii_keeper_client.session_prep_http_error", status=exc.response.status_code)
            raise
        except httpx.RequestError as exc:
            logger.error("pii_keeper_client.session_prep_request_error", error=str(exc))
            raise
