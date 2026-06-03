"""add secrets table

Revision ID: 3a8f2e1b9c4d
Revises: 2954c67aeea3
Create Date: 2026-05-31 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3a8f2e1b9c4d'
down_revision: Union[str, None] = '2954c67aeea3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


from sqlalchemy import inspect

def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if 'secrets' not in inspector.get_table_names():
        op.create_table(
            'secrets',
            sa.Column('id', sa.String(length=36), nullable=False),
            sa.Column('agent_id', sa.String(length=64), nullable=False),
            sa.Column('name', sa.String(length=128), nullable=False),
            sa.Column('value_encrypted', sa.Text(), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['agent_id'], ['agents.id']),
            sa.UniqueConstraint('agent_id', 'name', name='ix_secrets_agent_id_name')
        )
        op.create_index('ix_secrets_agent_id', 'secrets', ['agent_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_secrets_agent_id', table_name='secrets')
    op.drop_table('secrets')
