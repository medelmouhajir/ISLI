"""add_model_routing

Revision ID: b2283715c21f
Revises: 3a8f2e1b9c4d
Create Date: 2026-05-31 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2283715c21f'
down_revision: Union[str, None] = '3a8f2e1b9c4d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # agents table
    op.add_column('agents', sa.Column('model_routing_enabled', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    op.add_column('agents', sa.Column('secondary_models', sa.JSON(), nullable=False, server_default=sa.text("'[]'")))

    # tasks table
    op.add_column('tasks', sa.Column('complexity_score', sa.Integer(), nullable=True))
    op.add_column('tasks', sa.Column('complexity_tier', sa.String(length=16), nullable=True))
    op.add_column('tasks', sa.Column('routed_model_provider', sa.String(length=64), nullable=True))
    op.add_column('tasks', sa.Column('routed_model_id', sa.String(length=128), nullable=True))
    op.add_column('tasks', sa.Column('routed_model_reason', sa.Text(), nullable=True))

    # sessions table
    op.add_column('sessions', sa.Column('complexity_score', sa.Integer(), nullable=True))
    op.add_column('sessions', sa.Column('complexity_tier', sa.String(length=16), nullable=True))
    op.add_column('sessions', sa.Column('routed_model_provider', sa.String(length=64), nullable=True))
    op.add_column('sessions', sa.Column('routed_model_id', sa.String(length=128), nullable=True))
    op.add_column('sessions', sa.Column('routed_model_reason', sa.Text(), nullable=True))


def downgrade() -> None:
    # sessions table
    op.drop_column('sessions', 'routed_model_reason')
    op.drop_column('sessions', 'routed_model_id')
    op.drop_column('sessions', 'routed_model_provider')
    op.drop_column('sessions', 'complexity_tier')
    op.drop_column('sessions', 'complexity_score')

    # tasks table
    op.drop_column('tasks', 'routed_model_reason')
    op.drop_column('tasks', 'routed_model_id')
    op.drop_column('tasks', 'routed_model_provider')
    op.drop_column('tasks', 'complexity_tier')
    op.drop_column('tasks', 'complexity_score')

    # agents table
    op.drop_column('agents', 'secondary_models')
    op.drop_column('agents', 'model_routing_enabled')
