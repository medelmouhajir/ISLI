"""Add notification tables

Revision ID: 0849f259c283
Revises: d5e8f2a1b3c9
Create Date: 2026-06-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0849f259c283"
down_revision: Union[str, None] = "d5e8f2a1b3c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from sqlalchemy import inspect as sa_inspect
    conn = op.get_bind()
    inspector = sa_inspect(conn)
    existing = inspector.get_table_names()

    if "notifications" not in existing:
        op.create_table(
            "notifications",
            sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True, server_default=sa.text("gen_random_uuid()")),
            sa.Column("user_id", sa.String(64), nullable=False),
            sa.Column("event_type", sa.String(64), nullable=False),
            sa.Column("category", sa.String(32), nullable=False),
            sa.Column("title", sa.String(255), nullable=False),
            sa.Column("body", sa.Text(), nullable=True),
            sa.Column("payload", postgresql.JSON(), server_default="{}"),
            sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("agent_id", sa.String(64), nullable=True),
            sa.Column("task_id", sa.String(36), nullable=True),
            sa.Column("session_id", sa.String(64), nullable=True),
            sa.Column("channels", postgresql.JSON(), server_default="[]"),
            sa.Column("dedup_key", sa.String(128), nullable=True),
        )
        op.create_index("ix_notifications_user_created", "notifications", ["user_id", "created_at"])
        op.create_index("ix_notifications_user_read", "notifications", ["user_id", "read_at"])
        op.create_index("ix_notifications_dedup", "notifications", ["dedup_key"])

    if "notification_preferences" not in existing:
        op.create_table(
            "notification_preferences",
            sa.Column("user_id", sa.String(64), primary_key=True),
            sa.Column("global_enabled", sa.Boolean(), nullable=False, server_default="true"),
            sa.Column("quiet_hours_enabled", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column("quiet_hours_start", sa.DateTime(timezone=True), nullable=True),
            sa.Column("quiet_hours_end", sa.DateTime(timezone=True), nullable=True),
            sa.Column("timezone", sa.String(64), nullable=False, server_default="UTC"),
            sa.Column("quiet_hours_exceptions", postgresql.JSON(), server_default="[]"),
            sa.Column("categories", postgresql.JSON(), server_default="{}"),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        )


def downgrade() -> None:
    op.drop_table("notification_preferences")
    op.drop_index("ix_notifications_dedup", table_name="notifications")
    op.drop_index("ix_notifications_user_read", table_name="notifications")
    op.drop_index("ix_notifications_user_created", table_name="notifications")
    op.drop_table("notifications")
