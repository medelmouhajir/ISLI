"""add session journal

Revision ID: 7c695e5d18a9
Revises: 009
Create Date: 2026-05-17 01:32:07.709705

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7c695e5d18a9'
down_revision: Union[str, None] = '009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("sessions", sa.Column("journal", sa.Text(), nullable=True))
    op.add_column("sessions", sa.Column("journal_updated_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("sessions", "journal_updated_at")
    op.drop_column("sessions", "journal")
