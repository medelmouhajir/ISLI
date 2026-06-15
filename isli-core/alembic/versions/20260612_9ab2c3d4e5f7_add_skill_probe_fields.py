"""Add probe status fields to skill_registry.

Revision ID: 20260612_9ab2c3d4e5f7
Revises: 20260611_9ab2c3d4e5f6
Create Date: 2026-06-12 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '20260612_9ab2c3d4e5f7'
down_revision: Union[str, None] = '20260611_9ab2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('skill_registry', sa.Column('last_probe_status', sa.String(16), nullable=True))
    op.add_column('skill_registry', sa.Column('last_probe_result', sa.JSON(), nullable=True))
    op.add_column('skill_registry', sa.Column('last_probe_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('skill_registry', 'last_probe_at')
    op.drop_column('skill_registry', 'last_probe_result')
    op.drop_column('skill_registry', 'last_probe_status')
