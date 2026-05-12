"""Meta Business compliance addendum.

Messaging-template rules and 24h session policies.
"""

import structlog
from datetime import datetime, timezone, timedelta
from typing import Any

logger = structlog.get_logger()

META_SESSION_HOURS = 24


class MetaCompliance:
    """Enforce Meta (WhatsApp/Facebook) messaging policies."""

    @staticmethod
    def is_within_session_window(last_message_at: datetime | None) -> bool:
        """Check if the conversation is within the 24-hour session window."""
        if last_message_at is None:
            return False
        now = datetime.now(timezone.utc)
        window = timedelta(hours=META_SESSION_HOURS)
        return (now - last_message_at) <= window

    @staticmethod
    def requires_template(last_message_at: datetime | None) -> bool:
        """Outside the 24h window, businesses must use approved templates."""
        return not MetaCompliance.is_within_session_window(last_message_at)

    @staticmethod
    def validate_template(template_name: str, approved_templates: list[str]) -> bool:
        """Verify a template is pre-approved by Meta."""
        if template_name not in approved_templates:
            logger.error("meta.template_not_approved", template=template_name)
            return False
        logger.info("meta.template_validated", template=template_name)
        return True

    @staticmethod
    def session_expiry(last_message_at: datetime) -> datetime:
        return last_message_at + timedelta(hours=META_SESSION_HOURS)
