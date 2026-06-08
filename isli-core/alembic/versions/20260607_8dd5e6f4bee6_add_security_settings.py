"""add security settings

Revision ID: 8dd5e6f4bee6
Revises: a6e94c2b7614
Create Date: 2026-06-07 18:33:23.508522

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8dd5e6f4bee6'
down_revision: Union[str, None] = 'a6e94c2b7614'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Seed security settings
    seeds = [
        ("security_pii_scrubber_enabled", "security", "true", "Whether the PII scrubber is active for all agent interactions"),
        ("security_prompt_injection_threshold", "security", "0.5", "Risk score threshold for blocking prompt injection (0.0 to 1.0)"),
        ("security_default_monthly_usd_cap", "security", "50.0", "Default monthly USD budget cap for new users"),
        ("security_audit_retention_days", "security", "90", "Number of days to retain audit logs before rotation"),
    ]

    for key, scope, value, description in seeds:
        op.execute(
            f"""
            INSERT INTO system_settings (key, scope, value, description, updated_at)
            VALUES ('{key}', '{scope}', '{value}', '{description}', NOW())
            ON CONFLICT (key) DO NOTHING
            """
        )


def downgrade() -> None:
    op.execute("DELETE FROM system_settings WHERE scope = 'security'")
