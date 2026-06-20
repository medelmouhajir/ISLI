"""add skill owner_agent_id

Revision ID: 0684a5fdc2b9
Revises: 20260617_a1b2c3d4e5f6
Create Date: 2026-06-18 19:51:56.368147

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0684a5fdc2b9'
down_revision: str | None = '20260617_a1b2c3d4e5f6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('skill_registry', sa.Column('owner_agent_id', sa.String(64), nullable=True))
    op.create_index('ix_skill_registry_owner_agent_id', 'skill_registry', ['owner_agent_id'])


def downgrade() -> None:
    op.drop_index('ix_skill_registry_owner_agent_id', table_name='skill_registry')
    op.drop_column('skill_registry', 'owner_agent_id')
