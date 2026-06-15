"""Add skill_registry and skill_runs tables.

Revision ID: 20260611_9ab2c3d4e5f6
Revises: 20260607_8dd5e6f4bee6
Create Date: 2026-06-11 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '20260611_9ab2c3d4e5f6'
down_revision: Union[str, None] = '785c62fa414a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create skill_registry table
    op.create_table(
        'skill_registry',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('name', sa.String(128), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('version', sa.String(32), nullable=True),
        sa.Column('author', sa.String(128), nullable=True),
        sa.Column('category', sa.String(32), nullable=False),
        sa.Column('manifest', sa.JSON(), default=dict),
        sa.Column('base_url', sa.Text(), nullable=False),
        sa.Column('status', sa.String(16), nullable=False, server_default='pending'),
        sa.Column('installed_by', sa.String(64), nullable=True),
        sa.Column('installed_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Index('ix_skill_registry_status', 'status'),
        sa.Index('ix_skill_registry_category', 'category'),
    )

    # Create skill_runs table
    op.create_table(
        'skill_runs',
        sa.Column('id', sa.String(36), primary_key=True, default=lambda: str(__import__('uuid').uuid4())),
        sa.Column('skill_id', sa.String(64), sa.ForeignKey('skill_registry.id', ondelete='CASCADE'), nullable=False),
        sa.Column('container_id', sa.String(128), nullable=True),
        sa.Column('container_name', sa.String(128), nullable=True),
        sa.Column('host_port', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(16), nullable=False, server_default='pending'),
        sa.Column('last_heartbeat', sa.DateTime(timezone=True), nullable=True),
        sa.Column('exit_code', sa.Integer(), nullable=True),
        sa.Column('error_log', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('stopped_at', sa.DateTime(timezone=True), nullable=True),
        sa.Index('ix_skill_runs_skill_id', 'skill_id'),
        sa.Index('ix_skill_runs_status', 'status'),
    )


def downgrade() -> None:
    op.drop_table('skill_runs')
    op.drop_table('skill_registry')
