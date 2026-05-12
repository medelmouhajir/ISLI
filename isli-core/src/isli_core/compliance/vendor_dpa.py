"""Vendor Data Processing Agreement (DPA) register for channel providers."""

import structlog
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()


class VendorDPA:
    """In-memory vendor compliance register. In production, this would be a table."""

    REGISTER: dict[str, dict[str, Any]] = {
        "telegram": {
            "provider": "Telegram (LLC / FZ-LLC)",
            "dpa_signed": True,
            "signed_date": "2026-01-15",
            "data_residency": "EU (Frankfurt), SG",
            "scc_in_place": True,
            "last_reviewed": "2026-04-01",
            "next_review": "2026-10-01",
            "risk_level": "low",
        },
        "whatsapp": {
            "provider": "Meta Platforms, Inc.",
            "dpa_signed": True,
            "signed_date": "2026-02-01",
            "data_residency": "EU (Dublin), US",
            "scc_in_place": True,
            "last_reviewed": "2026-04-01",
            "next_review": "2026-10-01",
            "risk_level": "medium",
            "notes": "Requires Meta Business verification",
        },
        "twilio": {
            "provider": "Twilio Inc.",
            "dpa_signed": True,
            "signed_date": "2026-01-20",
            "data_residency": "US, EU",
            "scc_in_place": True,
            "last_reviewed": "2026-04-01",
            "next_review": "2026-10-01",
            "risk_level": "low",
        },
        "email": {
            "provider": "Self-hosted (SMTP)",
            "dpa_signed": True,
            "signed_date": "2026-01-01",
            "data_residency": "Same as ISLI deployment",
            "scc_in_place": False,
            "last_reviewed": "2026-04-01",
            "next_review": "2026-10-01",
            "risk_level": "low",
        },
    }

    @staticmethod
    def get(provider: str) -> dict[str, Any] | None:
        return VendorDPA.REGISTER.get(provider)

    @staticmethod
    def list_all() -> list[dict[str, Any]]:
        return [{"channel": k, **v} for k, v in VendorDPA.REGISTER.items()]

    @staticmethod
    def validate(provider: str) -> bool:
        entry = VendorDPA.REGISTER.get(provider)
        if entry is None:
            logger.error("vendor_dpa.missing", provider=provider)
            return False
        if not entry.get("dpa_signed"):
            logger.error("vendor_dpa.unsigned", provider=provider)
            return False
        next_review = entry.get("next_review")
        if next_review and datetime.strptime(next_review, "%Y-%m-%d").date() < datetime.now(timezone.utc).date():
            logger.warning("vendor_dpa.overdue_review", provider=provider, next_review=next_review)
        logger.info("vendor_dpa.validated", provider=provider)
        return True
