"""add_cron_support_to_tasks

Revision ID: a6e94c2b7614
Revises: 830d0df7f241
Create Date: 2026-06-02 01:44:24.452588

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a6e94c2b7614'
down_revision: Union[str, None] = '830d0df7f241'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('tasks', sa.Column('cron_expression', sa.String(length=128), nullable=True))
    op.add_column('tasks', sa.Column('last_triggered_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('tasks', 'last_triggered_at')
    op.drop_column('tasks', 'cron_expression')
