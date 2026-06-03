"""add_session_metadata

Revision ID: d5e8f2a1b3c9
Revises: b2283715c21f
Create Date: 2026-05-31 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd5e8f2a1b3c9'
down_revision: Union[str, None] = 'b2283715c21f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('sessions', sa.Column('session_metadata', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('sessions', 'session_metadata')
