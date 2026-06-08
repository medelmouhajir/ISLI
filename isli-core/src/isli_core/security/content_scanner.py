"""Content safety scanner — prompt injection heuristics and lightweight PII detection."""

import re
import structlog
from typing import Any

logger = structlog.get_logger()


class ScanResult:
    def __init__(self, blocked: bool, reason: str | None = None, risk_score: float = 0.0):
        self.blocked = blocked
        self.reason = reason
        self.risk_score = risk_score


from isli_core.prompts_loader import get_prompts


class ContentScanner:
    """Scan text for prompt injection patterns and basic PII."""

    PROMPT_INJECTION_MARKERS = get_prompts()["core"]["prompt_injection_markers"]

    PII_PATTERNS = {
        "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
        "email": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
        "phone": r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b",
        "credit_card": r"\b(?:\d{4}[-\s]?){3}\d{4}\b",
    }

    @classmethod
    def scan(cls, text: str | None, pii_enabled: bool = True, threshold: float = 0.5) -> ScanResult:
        if not text:
            return ScanResult(blocked=False, risk_score=0.0)

        lower = text.lower()
        risk_score = 0.0
        reasons: list[str] = []

        for pattern in cls.PROMPT_INJECTION_MARKERS:
            if re.search(pattern, lower, re.IGNORECASE):
                risk_score += 0.6
                reasons.append(f"Prompt injection marker: {pattern}")

        if pii_enabled:
            for name, pattern in cls.PII_PATTERNS.items():
                if re.search(pattern, text):
                    risk_score += 0.15
                    reasons.append(f"Possible PII detected: {name}")

        blocked = risk_score >= threshold
        logger.info(
            "content.scan_result",
            blocked=blocked,
            risk_score=round(risk_score, 2),
            markers_found=len(reasons),
        )
        return ScanResult(
            blocked=blocked,
            reason="; ".join(reasons) if reasons else None,
            risk_score=round(risk_score, 2),
        )
