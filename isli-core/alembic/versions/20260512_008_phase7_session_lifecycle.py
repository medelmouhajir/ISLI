"""Phase 7 session lifecycle

Revision ID: 008
Revises: 007
Create Date: 2026-05-12

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("sessions", sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_sessions_last_activity_at", "sessions", ["last_activity_at"])

    op.add_column("checkpoints", sa.Column("recovered_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("checkpoints", sa.Column("recovery_turn_number", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("checkpoints", "recovery_turn_number")
    op.drop_column("checkpoints", "recovered_at")
    op.drop_index("ix_sessions_last_activity_at", table_name="sessions")
    op.drop_column("sessions", "last_activity_at")
