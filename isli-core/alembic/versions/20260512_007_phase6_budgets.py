"""Phase 6 budget alerts

Revision ID: 007
Revises: 006
Create Date: 2026-05-12

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_budgets",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.String(64), nullable=False, unique=True),
        sa.Column("monthly_usd_cap", sa.Float(), nullable=True),
        sa.Column("monthly_token_cap", sa.Integer(), nullable=True),
        sa.Column("alert_threshold_pct", sa.Float(), nullable=False, server_default="80.0"),
        sa.Column("slack_webhook_url", sa.String(512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_user_budgets_user_id", "user_budgets", ["user_id"])

    op.create_table(
        "org_budgets",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", sa.String(64), nullable=False, unique=True),
        sa.Column("monthly_usd_cap", sa.Float(), nullable=True),
        sa.Column("monthly_token_cap", sa.Integer(), nullable=True),
        sa.Column("alert_threshold_pct", sa.Float(), nullable=False, server_default="80.0"),
        sa.Column("slack_webhook_url", sa.String(512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_org_budgets_org_id", "org_budgets", ["org_id"])

    op.add_column("agents", sa.Column("user_id", sa.String(64), nullable=True))
    op.add_column("agents", sa.Column("org_id", sa.String(64), nullable=True))
    op.create_index("ix_agents_user_id", "agents", ["user_id"])
    op.create_index("ix_agents_org_id", "agents", ["org_id"])


def downgrade() -> None:
    op.drop_index("ix_agents_user_id", table_name="agents")
    op.drop_index("ix_agents_org_id", table_name="agents")
    op.drop_column("agents", "user_id")
    op.drop_column("agents", "org_id")
    op.drop_table("org_budgets")
    op.drop_table("user_budgets")
