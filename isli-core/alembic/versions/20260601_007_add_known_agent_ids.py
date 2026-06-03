"""add known_agent_ids to agents

Revision ID: 830d0df7f241
Revises: 0849f259c283
Create Date: 2026-06-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "830d0df7f241"
down_revision: Union[str, None] = "0849f259c283"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column("known_agent_ids", sa.JSON(), nullable=False, server_default="[]")
    )


def downgrade() -> None:
    op.drop_column("agents", "known_agent_ids")
