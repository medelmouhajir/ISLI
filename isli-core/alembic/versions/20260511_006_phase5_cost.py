"""Phase 5 cost optimization

Revision ID: 006
Revises: 005
Create Date: 2026-05-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cost_ledger",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("agent_id", sa.String(64), sa.ForeignKey("agents.id"), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tasks.id"), nullable=True),
        sa.Column("model_id", sa.String(128), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("tier", sa.String(16), nullable=False, server_default="standard"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
    )
    op.create_index("ix_cost_ledger_agent_id", "cost_ledger", ["agent_id"])
    op.create_index("ix_cost_ledger_created_at", "cost_ledger", ["created_at"])
    op.create_index("ix_cost_ledger_agent_created", "cost_ledger", ["agent_id", "created_at"])


def downgrade() -> None:
    op.drop_table("cost_ledger")
