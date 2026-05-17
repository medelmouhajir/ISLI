"""Policy engine — evaluate requests against security rules."""

import hashlib
import structlog
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from isli_core.models import PolicyOverride
from isli_core.security.content_scanner import ContentScanner, ScanResult

logger = structlog.get_logger()


class PolicyDecision:
    def __init__(
        self,
        allow: bool,
        reason: str | None = None,
        risk_score: float = 0.0,
        overrideable: bool = False,
        rule: str | None = None,
        context_hash: str | None = None,
    ):
        self.allow = allow
        self.reason = reason
        self.risk_score = risk_score
        self.overrideable = overrideable
        self.rule = rule
        self.context_hash = context_hash


class PolicyEngine:
    """Evaluate request context against security policy rules."""

    @staticmethod
    def _hash_context(context: dict[str, Any]) -> str:
        raw = "|".join(f"{k}={v}" for k, v in sorted(context.items()) if v is not None)
        return hashlib.sha256(raw.encode()).hexdigest()[:32]

    @staticmethod
    async def evaluate(
        session: AsyncSession,
        user_id: str,
        input_text: str | None,
        agent_id: str | None,
        skill_name: str | None,
        model_id: str | None,
        budget_exceeded: bool = False,
        estop_active: bool = False,
    ) -> PolicyDecision:
        # 1. Content scan
        scan = ContentScanner.scan(input_text)
        if scan.blocked:
            return PolicyDecision(
                allow=False,
                reason=f"Content safety block: {scan.reason}",
                risk_score=scan.risk_score,
                overrideable=True,
                rule="content_safety",
                context_hash=PolicyEngine._hash_context({"user_id": user_id, "input": input_text}),
            )

        # 2. Emergency stop
        if estop_active:
            return PolicyDecision(
                allow=False,
                reason="Emergency stop is active",
                risk_score=1.0,
                overrideable=False,
                rule="estop_active",
                context_hash=PolicyEngine._hash_context({"user_id": user_id}),
            )

        # 3. Budget limit
        if budget_exceeded:
            return PolicyDecision(
                allow=False,
                reason="Budget cap exceeded",
                risk_score=0.8,
                overrideable=True,
                rule="budget_within_limit",
                context_hash=PolicyEngine._hash_context({"user_id": user_id, "agent_id": agent_id}),
            )

        # 4. Approved model only
        if model_id and not PolicyEngine._is_approved_model(model_id):
            return PolicyDecision(
                allow=False,
                reason=f"Model '{model_id}' is not in the approved list",
                risk_score=0.6,
                overrideable=True,
                rule="approved_model_only",
                context_hash=PolicyEngine._hash_context({"user_id": user_id, "model_id": model_id}),
            )

        # 5. Dangerous skill chain
        if skill_name and PolicyEngine._is_dangerous_skill(skill_name):
            return PolicyDecision(
                allow=False,
                reason=f"Skill '{skill_name}' is flagged as dangerous",
                risk_score=0.7,
                overrideable=True,
                rule="no_dangerous_skill_chain",
                context_hash=PolicyEngine._hash_context({"user_id": user_id, "skill": skill_name}),
            )

        return PolicyDecision(allow=True, risk_score=scan.risk_score)

    @staticmethod
    def _is_approved_model(model_id: str) -> bool:
        approved = {
            "gpt-4o",
            "gpt-4o-mini",
            "gpt-4",
            "claude-sonnet-4-6",
            "claude-opus-4-7",
            "claude-haiku-4-5",
            "o1",
            "o3",
        }
        return model_id.lower() in approved

    @staticmethod
    def _is_dangerous_skill(skill_name: str) -> bool:
        dangerous = {"shell-exec", "sql-drop", "send-email"}
        return skill_name.lower() in dangerous

    @staticmethod
    async def check_override(
        session: AsyncSession,
        user_id: str,
        rule: str,
        context_hash: str,
    ) -> bool:
        result = await session.execute(
            select(PolicyOverride).where(
                PolicyOverride.user_id == user_id,
                PolicyOverride.rule == rule,
                PolicyOverride.context_hash == context_hash,
                PolicyOverride.granted.is_(True),
                PolicyOverride.expires_at > __import__("datetime").datetime.now(__import__("datetime").timezone.utc),
            )
        )
        return result.scalar_one_or_none() is not None
