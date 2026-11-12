"""Add project visual style while preserving existing custom style prompts.

Revision ID: a8d5c2e7f901
Revises: e4b7c2d9a1f5
Create Date: 2026-11-10
"""

from alembic import op
import sqlalchemy as sa

revision = "a8d5c2e7f901"
down_revision = "e4b7c2d9a1f5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("visual_style", sa.String(), nullable=False, server_default=""))


def downgrade() -> None:
    with op.batch_alter_table("projects") as batch_op:
        batch_op.drop_column("visual_style")
