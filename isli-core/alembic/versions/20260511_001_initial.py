"""Initial schema

Revision ID: 001
Revises:
Create Date: 2026-05-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agents",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="registered"),
        sa.Column("model_provider", sa.String(64), nullable=True),
        sa.Column("model_id", sa.String(128), nullable=True),
        sa.Column("channels", sa.ARRAY(sa.String(32)), server_default="{}"),
        sa.Column("skills", sa.ARRAY(sa.String(64)), server_default="{}"),
        sa.Column("config", postgresql.JSON(), server_default="{}"),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
    )
    op.create_index("ix_agents_status", "agents", ["status"])

    op.create_table(
        "tasks",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="inbox"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("agent_id", sa.String(64), sa.ForeignKey("agents.id"), nullable=True),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("input", sa.Text(), nullable=False, server_default=""),
        sa.Column("output", sa.Text(), nullable=True),
        sa.Column("channel", sa.String(32), nullable=True),
        sa.Column("parent_task_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tasks.id"), nullable=True),
        sa.Column("child_task_ids", sa.ARRAY(postgresql.UUID(as_uuid=False)), server_default="{}"),
        sa.Column("blocked_reason", sa.Text(), nullable=True),
        sa.Column("token_usage", postgresql.JSON(), nullable=True),
        sa.Column("tags", sa.ARRAY(sa.String(64)), server_default="{}"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("trace_id", sa.String(64), nullable=True),
    )
    op.create_index("ix_tasks_status", "tasks", ["status"])
    op.create_index("ix_tasks_agent_id", "tasks", ["agent_id"])
    op.create_index("ix_tasks_created_at", "tasks", ["created_at"])
    op.create_index("ix_tasks_parent_task_id", "tasks", ["parent_task_id"])

    op.create_table(
        "episodic_memories",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("agent_id", sa.String(64), sa.ForeignKey("agents.id"), nullable=False),
        sa.Column("session_id", sa.String(64), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("tags", sa.ARRAY(sa.String(64)), server_default="{}"),
        sa.Column("importance", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("embedding", sa.ARRAY(sa.Float()), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
    )
    op.create_index("ix_episodic_memories_agent_id", "episodic_memories", ["agent_id"])
    op.create_index("ix_episodic_memories_created_at", "episodic_memories", ["created_at"])

    op.create_table(
        "sessions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("agent_id", sa.String(64), sa.ForeignKey("agents.id"), nullable=False),
        sa.Column("user_id", sa.String(64), nullable=True),
        sa.Column("channel", sa.String(32), nullable=True),
        sa.Column("messages", postgresql.JSON(), server_default="{}"),
        sa.Column("token_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("compacted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_sessions_agent_id", "sessions", ["agent_id"])
    op.create_index("ix_sessions_expires_at", "sessions", ["expires_at"])

    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("actor_type", sa.String(32), nullable=False),
        sa.Column("actor_id", sa.String(64), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("target_type", sa.String(32), nullable=False),
        sa.Column("target_id", sa.String(64), nullable=False),
        sa.Column("payload", postgresql.JSON(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
    )
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_logs_created_at", table_name="audit_logs")
    op.drop_table("audit_logs")

    op.drop_index("ix_sessions_expires_at", table_name="sessions")
    op.drop_index("ix_sessions_agent_id", table_name="sessions")
    op.drop_table("sessions")

    op.drop_index("ix_episodic_memories_created_at", table_name="episodic_memories")
    op.drop_index("ix_episodic_memories_agent_id", table_name="episodic_memories")
    op.drop_table("episodic_memories")

    op.drop_index("ix_tasks_parent_task_id", table_name="tasks")
    op.drop_index("ix_tasks_created_at", table_name="tasks")
    op.drop_index("ix_tasks_agent_id", table_name="tasks")
    op.drop_index("ix_tasks_status", table_name="tasks")
    op.drop_table("tasks")

    op.drop_index("ix_agents_status", table_name="agents")
    op.drop_table("agents")
