"""add context inject retry tracking to task and session

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-05-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tasks",
        sa.Column("context_inject_attempts", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column(
        "tasks",
        sa.Column("context_inject_failed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "sessions",
        sa.Column("context_inject_attempts", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column(
        "sessions",
        sa.Column("context_inject_failed_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("sessions", "context_inject_failed_at")
    op.drop_column("sessions", "context_inject_attempts")
    op.drop_column("tasks", "context_inject_failed_at")
    op.drop_column("tasks", "context_inject_attempts")
