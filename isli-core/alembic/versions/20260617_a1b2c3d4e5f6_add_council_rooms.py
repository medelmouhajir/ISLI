"""Add Council rooms and link sessions to rooms.

Revision ID: 20260617_a1b2c3d4e5f6
Revises: 20260613_8f3e7a2b9c1d
Create Date: 2026-06-17 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260617_a1b2c3d4e5f6"
down_revision: str | None = "20260613_8f3e7a2b9c1d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_exists(name: str) -> bool:
    return inspect(op.get_bind()).has_table(name)


def _column_exists(table: str, column: str) -> bool:
    return any(
        col["name"] == column
        for col in inspect(op.get_bind()).get_columns(table)
    )


def _index_exists(table: str, index: str) -> bool:
    return any(
        idx["name"] == index
        for idx in inspect(op.get_bind()).get_indexes(table)
    )


def upgrade() -> None:
    if not _table_exists("rooms"):
        op.create_table(
            "rooms",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("user_id", sa.String(64), nullable=False),
            sa.Column("channel", sa.String(32), nullable=False, server_default="web"),
            sa.Column("status", sa.String(32), nullable=False, server_default="active"),
            sa.Column("messages", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("agent_ids", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("pins", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("room_metadata", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column(
                "expires_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column(
                "last_activity_at", sa.DateTime(timezone=True), nullable=True
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Index("ix_rooms_user_id", "user_id"),
            sa.Index("ix_rooms_status", "status"),
            sa.Index("ix_rooms_last_activity_at", "last_activity_at"),
        )

    if not _column_exists("sessions", "room_id"):
        op.add_column(
            "sessions",
            sa.Column(
                "room_id", sa.String(36), sa.ForeignKey("rooms.id"), nullable=True
            ),
        )

    if not _index_exists("sessions", "ix_sessions_room_id"):
        op.create_index("ix_sessions_room_id", "sessions", ["room_id"])


def downgrade() -> None:
    if _index_exists("sessions", "ix_sessions_room_id"):
        op.drop_index("ix_sessions_room_id", table_name="sessions")

    if _column_exists("sessions", "room_id"):
        op.drop_column("sessions", "room_id")

    if _table_exists("rooms"):
        op.drop_table("rooms")
