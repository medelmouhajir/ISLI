"""Phase 8 audit transparency

Revision ID: 009
Revises: 008
Create Date: 2026-05-12

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("audit_logs", sa.Column("chain_hash", sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column("audit_logs", "chain_hash")
