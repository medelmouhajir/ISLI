"""Phase 2 resilience columns

Revision ID: 003
Revises: 002
Create Date: 2026-05-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Agent: fallback_agent_id, max_retries
    op.add_column("agents", sa.Column("fallback_agent_id", sa.String(64), sa.ForeignKey("agents.id"), nullable=True))
    op.add_column("agents", sa.Column("max_retries", sa.Integer(), nullable=False, server_default="3"))

    # Task: retry_count, idempotency_key
    op.add_column("tasks", sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("tasks", sa.Column("idempotency_key", sa.String(128), nullable=True))
    op.create_index("ix_tasks_idempotency_key", "tasks", ["idempotency_key"])

    # Checkpoints table
    op.create_table(
        "checkpoints",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("task_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tasks.id"), nullable=False),
        sa.Column("turn_number", sa.Integer(), nullable=False),
        sa.Column("messages", postgresql.JSON(), server_default="{}"),
        sa.Column("tool_calls", postgresql.JSON(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
    )
    op.create_index("ix_checkpoints_task_id", "checkpoints", ["task_id"])
    op.create_index("ix_checkpoints_turn_number", "checkpoints", ["turn_number"])


def downgrade() -> None:
    op.drop_table("checkpoints")
    op.drop_index("ix_tasks_idempotency_key", table_name="tasks")
    op.drop_column("tasks", "idempotency_key")
    op.drop_column("tasks", "retry_count")
    op.drop_column("agents", "max_retries")
    op.drop_column("agents", "fallback_agent_id")
