"""migrate episodic embedding to pgvector and backfill

Revision ID: 0bad60745eba
Revises: 7c695e5d18a9
Create Date: 2026-05-17 15:15:00.178849

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0bad60745eba'
down_revision: Union[str, None] = '7c695e5d18a9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Enable extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    
    # 2. Backfill NULLs with zero vectors (currently ARRAY(FLOAT))
    # We use a SQL array literal for the 768 zero vector to avoid bindparam complexity in migration
    zero_vec_sql = "ARRAY[" + ",".join(["0.0"] * 768) + "]::float[]"
    op.execute(f"UPDATE episodic_memories SET embedding = {zero_vec_sql} WHERE embedding IS NULL")

    # 3. Alter column type to Vector(768)
    op.alter_column(
        'episodic_memories',
        'embedding',
        type_=Vector(768),
        postgresql_using='embedding::vector',
        existing_type=postgresql.ARRAY(sa.Float()),
        nullable=True
    )


def downgrade() -> None:
    # Alter column type back to ARRAY(FLOAT)
    op.alter_column(
        'episodic_memories',
        'embedding',
        type_=postgresql.ARRAY(sa.Float()),
        postgresql_using='embedding::float[]',
        existing_type=Vector(768),
        nullable=True
    )
