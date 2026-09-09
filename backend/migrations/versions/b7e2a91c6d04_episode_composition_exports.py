"""Track episode composition targets and ordered episode exports.

Revision ID: b7e2a91c6d04
Revises: a3f0c95d7e18
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel

revision = "b7e2a91c6d04"
down_revision = "a3f0c95d7e18"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("export_jobs", sa.Column("target_episode_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.add_column("export_jobs", sa.Column("source_episode_ids", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=sa.text("'[]'")))


def downgrade():
    with op.batch_alter_table("export_jobs") as batch:
        batch.drop_column("source_episode_ids")
        batch.drop_column("target_episode_id")
