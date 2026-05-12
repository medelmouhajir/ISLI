"""Phase 4 memory

Revision ID: 005
Revises: 004
Create Date: 2026-05-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # EpisodicMemory: embedding_model, composite index
    op.add_column("episodic_memories", sa.Column("embedding_model", sa.String(64), nullable=False, server_default="nomic-embed-text"))
    op.create_index("ix_episodic_memories_agent_id_created_at", "episodic_memories", ["agent_id", "created_at"])

    # AuditLog: composite index
    op.create_index("ix_audit_logs_actor_created", "audit_logs", ["actor_id", "created_at"])

    # Outbox table
    op.create_table(
        "outbox",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("topic", sa.String(64), nullable=False),
        sa.Column("payload", postgresql.JSON(), nullable=False),
        sa.Column("headers", postgresql.JSON(), server_default="{}"),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_outbox_status_created", "outbox", ["status", "created_at"])
    op.create_index("ix_outbox_topic", "outbox", ["topic"])


def downgrade() -> None:
    op.drop_table("outbox")
    op.drop_index("ix_audit_logs_actor_created", table_name="audit_logs")
    op.drop_index("ix_episodic_memories_agent_id_created_at", table_name="episodic_memories")
    op.drop_column("episodic_memories", "embedding_model")
