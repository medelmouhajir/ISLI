"""add system settings

Revision ID: f5cb013f7a4f
Revises: f146474bfdb1
Create Date: 2026-05-24 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f5cb013f7a4f'
down_revision: Union[str, None] = 'f146474bfdb1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'system_settings',
        sa.Column('key', sa.String(128), primary_key=True),
        sa.Column('scope', sa.String(32), nullable=False, server_default='global'),
        sa.Column('value', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_by', sa.String(64), nullable=True),
    )
    op.create_index('ix_system_settings_scope', 'system_settings', ['scope'])

    # Seed 12 general settings with their hardcoded defaults
    # PostgreSQL JSON columns accept JSON text literals directly.
    seeds = [
        ("session_idle_timeout_minutes", "general", "30", "Minutes before an idle session is marked for cleanup"),
        ("task_lease_minutes", "general", "30", "Minutes a task worker holds a lease before expiry"),
        ("delegation_max_depth", "general", "3", "Maximum delegation depth for task chains"),
        ("delegation_approval_depth", "general", "2", "Depth at which human approval is required for delegations"),
        ("cors_origins", "general", '""', "Comma-separated list of allowed CORS origins"),
        ("default_max_retries", "general", "3", "Default retry count for exponential backoff"),
        ("default_base_delay_seconds", "general", "1.0", "Initial delay between retries"),
        ("default_max_delay_seconds", "general", "60.0", "Maximum delay between retries"),
        ("circuit_breaker_failure_threshold", "general", "5", "Failures before circuit breaker opens"),
        ("circuit_breaker_recovery_timeout", "general", "30.0", "Seconds before circuit breaker tries recovery"),
        ("bulkhead_max_queue", "general", "100", "Maximum queued requests per bulkhead"),
        ("bulkhead_timeout_seconds", "general", "10.0", "Seconds before bulkhead request times out"),
    ]

    for key, scope, value, description in seeds:
        op.execute(
            f"""
            INSERT INTO system_settings (key, scope, value, description, updated_at)
            VALUES ('{key}', '{scope}', '{value}', '{description}', NOW())
            ON CONFLICT (key) DO NOTHING
            """
        )


def downgrade() -> None:
    op.drop_index('ix_system_settings_scope', table_name='system_settings')
    op.drop_table('system_settings')
