"""add provider settings and agent api_key

Revision ID: f146474bfdb1
Revises: 11d2a499d4c2
Create Date: 2026-05-21 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f146474bfdb1'
down_revision: Union[str, None] = '11d2a499d4c2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create llm_providers table
    op.create_table(
        'llm_providers',
        sa.Column('provider', sa.String(64), primary_key=True),
        sa.Column('api_key', sa.Text(), nullable=True),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
    )

    # Create permitted_models table
    op.create_table(
        'permitted_models',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('provider', sa.String(64), sa.ForeignKey('llm_providers.provider'), nullable=False),
        sa.Column('model_id', sa.String(128), nullable=False),
        sa.Column('name', sa.String(128), nullable=True),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    op.create_index('ix_permitted_models_provider', 'permitted_models', ['provider'])
    op.create_index('ix_permitted_models_provider_model', 'permitted_models', ['provider', 'model_id'], unique=True)

    # Add api_key to agents
    op.add_column('agents', sa.Column('api_key', sa.Text(), nullable=True))

    # Seed default providers
    providers_table = sa.table(
        'llm_providers',
        sa.column('provider', sa.String(64)),
        sa.column('enabled', sa.Boolean()),
    )
    op.bulk_insert(providers_table, [
        {'provider': 'ollama', 'enabled': True},
        {'provider': 'anthropic', 'enabled': True},
        {'provider': 'openai', 'enabled': True},
        {'provider': 'kimi', 'enabled': True},
        {'provider': 'deepseek', 'enabled': True},
        {'provider': 'google', 'enabled': True},
        {'provider': 'azure', 'enabled': True},
    ])

    # Seed default permitted models
    models_table = sa.table(
        'permitted_models',
        sa.column('provider', sa.String(64)),
        sa.column('model_id', sa.String(128)),
        sa.column('name', sa.String(128)),
        sa.column('enabled', sa.Boolean()),
    )
    op.bulk_insert(models_table, [
        {'provider': 'openai', 'model_id': 'gpt-4o', 'name': 'GPT-4o', 'enabled': True},
        {'provider': 'openai', 'model_id': 'gpt-4o-mini', 'name': 'GPT-4o Mini', 'enabled': True},
        {'provider': 'anthropic', 'model_id': 'claude-sonnet-4-6', 'name': 'Claude Sonnet 4.6', 'enabled': True},
        {'provider': 'anthropic', 'model_id': 'claude-opus-4-7', 'name': 'Claude Opus 4.7', 'enabled': True},
        {'provider': 'anthropic', 'model_id': 'claude-haiku-4-5', 'name': 'Claude Haiku 4.5', 'enabled': True},
        {'provider': 'ollama', 'model_id': 'qwen3:1.7b', 'name': 'Qwen3 1.7B', 'enabled': True},
        {'provider': 'ollama', 'model_id': 'qwen2.5:7b', 'name': 'Qwen2.5 7B', 'enabled': True},
        {'provider': 'ollama', 'model_id': 'kimi-k2.6', 'name': 'Kimi K2.6', 'enabled': True},
    ])


def downgrade() -> None:
    op.drop_column('agents', 'api_key')
    op.drop_index('ix_permitted_models_provider_model', table_name='permitted_models')
    op.drop_index('ix_permitted_models_provider', table_name='permitted_models')
    op.drop_table('permitted_models')
    op.drop_table('llm_providers')
