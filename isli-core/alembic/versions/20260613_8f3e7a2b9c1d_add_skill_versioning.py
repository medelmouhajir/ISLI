"""Add skill versioning columns.

Revision ID: 20260613_8f3e7a2b9c1d
Revises: 20260612_9ab2c3d4e5f7
Create Date: 2026-06-13 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '20260613_8f3e7a2b9c1d'
down_revision: Union[str, None] = '20260612_9ab2c3d4e5f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('skill_registry', sa.Column('source_url', sa.Text(), nullable=True))
    op.add_column('skill_registry', sa.Column('source_ref', sa.String(64), nullable=False, server_default='main'))
    op.add_column('skill_registry', sa.Column('installed_commit_sha', sa.String(40), nullable=True))
    op.add_column('skill_registry', sa.Column('latest_commit_sha', sa.String(40), nullable=True))
    op.add_column('skill_registry', sa.Column('latest_version', sa.String(32), nullable=True))
    op.add_column('skill_registry', sa.Column('update_policy', sa.String(16), nullable=False, server_default='manual'))
    op.add_column('skill_registry', sa.Column('previous_version', sa.String(32), nullable=True))
    op.add_column('skill_registry', sa.Column('previous_commit_sha', sa.String(40), nullable=True))
    op.add_column('skill_registry', sa.Column('previous_image_tag', sa.String(128), nullable=True))
    op.add_column('skill_registry', sa.Column('changelog', sa.JSON(), nullable=True))
    op.add_column('skill_registry', sa.Column('last_checked_at', sa.DateTime(timezone=True), nullable=True))
    op.create_index('ix_skill_registry_update_policy', 'skill_registry', ['update_policy'])

    # Backfill installed_commit_sha for existing skills from on-disk git repos
    import os, subprocess
    from alembic import context
    conn = op.get_bind()
    installed_skills_path = os.getenv("ISLI_INSTALLED_SKILLS_PATH", "/data/installed_skills")
    rows = conn.execute(sa.text("SELECT id FROM skill_registry")).fetchall()
    for row in rows:
        skill_id = row[0]
        skill_dir = os.path.join(installed_skills_path, skill_id)
        if os.path.isdir(os.path.join(skill_dir, ".git")):
            try:
                sha = subprocess.check_output(
                    ["git", "-C", skill_dir, "rev-parse", "HEAD"],
                    stderr=subprocess.DEVNULL,
                    text=True,
                ).strip()
                conn.execute(
                    sa.text("UPDATE skill_registry SET installed_commit_sha = :sha WHERE id = :id"),
                    {"sha": sha, "id": skill_id},
                )
            except Exception:
                pass


def downgrade() -> None:
    op.drop_index('ix_skill_registry_update_policy', table_name='skill_registry')
    op.drop_column('skill_registry', 'last_checked_at')
    op.drop_column('skill_registry', 'changelog')
    op.drop_column('skill_registry', 'previous_image_tag')
    op.drop_column('skill_registry', 'previous_commit_sha')
    op.drop_column('skill_registry', 'previous_version')
    op.drop_column('skill_registry', 'update_policy')
    op.drop_column('skill_registry', 'latest_version')
    op.drop_column('skill_registry', 'latest_commit_sha')
    op.drop_column('skill_registry', 'installed_commit_sha')
    op.drop_column('skill_registry', 'source_ref')
    op.drop_column('skill_registry', 'source_url')
