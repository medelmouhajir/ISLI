"""add chromadb_backups table

Revision ID: 2954c67aeea3
Revises: f5cb013f7a47
Create Date: 2026-05-30 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2954c67aeea3'
down_revision: Union[str, None] = 'f5cb013f7a47'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'chromadb_backups',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('archive_path', sa.String(length=512), nullable=False),
        sa.Column('checksum_sha256', sa.String(length=64), nullable=False),
        sa.Column('size_bytes', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False, server_default='pending'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_chromadb_backups_status', 'chromadb_backups', ['status'], unique=False)
    op.create_index('ix_chromadb_backups_created_at', 'chromadb_backups', ['created_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_chromadb_backups_created_at', table_name='chromadb_backups')
    op.drop_index('ix_chromadb_backups_status', table_name='chromadb_backups')
    op.drop_table('chromadb_backups')
