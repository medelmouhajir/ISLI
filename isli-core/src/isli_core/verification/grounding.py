"""Grounding verifier — detect tool failure and hallucinated success."""

import asyncio
from typing import Any

import structlog

from isli_core.verification.schema_registry import SKILL_OUTPUT_SCHEMAS
from isli_core.verification.retry_policy import RetryPolicyMapper

logger = structlog.get_logger()


class VerificationResult:
    def __init__(self, is_valid: bool, reason: str | None = None):
        self.is_valid = is_valid
        self.reason = reason


class GroundingVerifier:
    """Validate skill output against schema, contradictions, and HTTP error markers."""

    @staticmethod
    def verify(skill_name: str, raw_response: dict[str, Any]) -> VerificationResult:
        # 1. Check for hallucinated success / contradiction
        status = raw_response.get("status")
        error = raw_response.get("error")
        success = raw_response.get("success")

        if success is True and error:
            return VerificationResult(
                is_valid=False,
                reason=f"Contradiction: success=True but error present: {error}",
            )

        if status in ("ok", "success") and error:
            return VerificationResult(
                is_valid=False,
                reason=f"Contradiction: status='{status}' but error present: {error}",
            )

        # 2. Detect HTTP error markers inside JSON body
        if isinstance(error, str) and any(
            marker in error.lower()
            for marker in ("internal server error", "bad gateway", "service unavailable", "timeout")
        ):
            return VerificationResult(
                is_valid=False,
                reason=f"HTTP error marker in response body: {error}",
            )

        # 3. Schema validation for known skills
        schema = SKILL_OUTPUT_SCHEMAS.get(skill_name)
        if schema:
            missing = [f for f in schema["required"] if f not in raw_response]
            if missing:
                return VerificationResult(
                    is_valid=False,
                    reason=f"Missing required fields: {missing}",
                )
            for field, expected_type in schema.get("types", {}).items():
                if field in raw_response and not isinstance(raw_response[field], expected_type):
                    return VerificationResult(
                        is_valid=False,
                        reason=f"Field '{field}' expected {expected_type.__name__}, got {type(raw_response[field]).__name__}",
                    )

        return VerificationResult(is_valid=True)

    @staticmethod
    async def verify_with_retry(
        skill_name: str,
        call_fn,
        max_retries: int | None = None,
    ) -> tuple[dict[str, Any], VerificationResult]:
        """Call skill, verify, retry up to max_retries if invalid.

        call_fn is an async callable returning the raw response dict.
        """
        policy = RetryPolicyMapper.get("verification_fail")
        retries = max_retries if max_retries is not None else policy["max_retries"]
        base = policy["backoff_base"]
        cap = policy["backoff_cap"]
        jitter = policy["jitter"]

        last_result = VerificationResult(is_valid=False, reason="No attempts made")

        for attempt in range(retries + 1):
            try:
                raw = await call_fn()
            except Exception as exc:
                logger.warning(
                    "verification.call_failed",
                    skill=skill_name,
                    attempt=attempt,
                    error=str(exc),
                )
                last_result = VerificationResult(is_valid=False, reason=f"Call failed: {exc}")
                if attempt < retries:
                    delay = RetryPolicyMapper.compute_delay(attempt, base, cap, jitter)
                    await asyncio.sleep(delay)
                continue

            result = GroundingVerifier.verify(skill_name, raw)
            
            # Phase 2: Local Logic Judge (Quality Gating) - Risk Based
            HIGH_RISK_SKILLS = {"shell-exec", "file-write", "file-delete", "file-list"}
            if result.is_valid and skill_name in HIGH_RISK_SKILLS:
                from isli_core.memory.keeper_client import KeeperClient
                judge_result = await KeeperClient.verify_logic(str(raw))
                if not judge_result.get("is_valid", True):
                    logger.warning("verification.judge_fail", skill=skill_name, reason=judge_result.get("reason"))
                    result = VerificationResult(is_valid=False, reason=f"Local Judge: {judge_result.get('reason')}")

            if result.is_valid:
                return raw, result

            last_result = result
            logger.warning(
                "verification.failed",
                skill=skill_name,
                attempt=attempt,
                reason=result.reason,
            )

            if attempt < retries:
                delay = RetryPolicyMapper.compute_delay(attempt, base, cap, jitter)
                await asyncio.sleep(delay)

        return {}, last_result
