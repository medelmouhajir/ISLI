"""add file sharing

Revision ID: f5cb013f7a47
Revises: f5cb013f7a4f
Create Date: 2026-05-25 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f5cb013f7a47'
down_revision: Union[str, None] = 'f5cb013f7a4f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Update tasks table
    op.add_column('tasks', sa.Column('attachments', sa.JSON(), nullable=False, server_default='[]'))
    op.add_column('tasks', sa.Column('retain_attachments', sa.Boolean(), nullable=False, server_default='false'))

    # 2. Create shared_workspaces table
    op.create_table(
        'shared_workspaces',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('name', sa.String(length=128), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('owner_id', sa.String(length=64), nullable=False),
        sa.Column('members', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('quota_bytes', sa.Integer(), nullable=False, server_default='524288000'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_shared_workspaces_owner_id', 'shared_workspaces', ['owner_id'], unique=False)
    op.create_index('ix_shared_workspaces_deleted_at', 'shared_workspaces', ['deleted_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_shared_workspaces_deleted_at', table_name='shared_workspaces')
    op.drop_index('ix_shared_workspaces_owner_id', table_name='shared_workspaces')
    op.drop_table('shared_workspaces')
    op.drop_column('tasks', 'retain_attachments')
    op.drop_column('tasks', 'attachments')
