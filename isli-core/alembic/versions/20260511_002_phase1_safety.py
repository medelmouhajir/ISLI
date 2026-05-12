"""Phase 1 safety columns

Revision ID: 002
Revises: 001
Create Date: 2026-05-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Agent: token_budget, token_used, status_reason, deleted_at
    op.add_column("agents", sa.Column("token_budget", sa.Integer(), nullable=True))
    op.add_column("agents", sa.Column("token_used", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("agents", sa.Column("status_reason", sa.Text(), nullable=True))
    op.add_column("agents", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))

    # Task: depth, deleted_at
    op.add_column("tasks", sa.Column("depth", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("tasks", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))

    # EpisodicMemory: deleted_at
    op.add_column("episodic_memories", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))

    # Session: consent_given, consent_at, deleted_at
    op.add_column("sessions", sa.Column("consent_given", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("sessions", sa.Column("consent_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("sessions", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))

    # UserConsent table
    op.create_table(
        "user_consents",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("channel", sa.String(32), nullable=False),
        sa.Column("purpose", sa.String(64), nullable=False),
        sa.Column("granted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
    )
    op.create_index("ix_user_consents_user_id", "user_consents", ["user_id"])
    op.create_index("ix_user_consents_channel", "user_consents", ["channel"])


def downgrade() -> None:
    op.drop_table("user_consents")

    op.drop_column("sessions", "deleted_at")
    op.drop_column("sessions", "consent_at")
    op.drop_column("sessions", "consent_given")

    op.drop_column("episodic_memories", "deleted_at")

    op.drop_column("tasks", "deleted_at")
    op.drop_column("tasks", "depth")

    op.drop_column("agents", "deleted_at")
    op.drop_column("agents", "status_reason")
    op.drop_column("agents", "token_used")
    op.drop_column("agents", "token_budget")
