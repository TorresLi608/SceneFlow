"""project video audio default

Revision ID: f1c2d3e4a5b6
Revises: e7f1a9b2c3d4
Create Date: 2026-08-27
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "f1c2d3e4a5b6"
down_revision: Union[str, Sequence[str], None] = "e7f1a9b2c3d4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "projects" in inspect(op.get_bind()).get_table_names() and "video_audio_enabled" not in {
        column["name"] for column in inspect(op.get_bind()).get_columns("projects")
    }:
        op.add_column("projects", sa.Column("video_audio_enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")))


def downgrade() -> None:
    if "projects" in inspect(op.get_bind()).get_table_names() and "video_audio_enabled" in {
        column["name"] for column in inspect(op.get_bind()).get_columns("projects")
    }:
        with op.batch_alter_table("projects") as batch_op:
            batch_op.drop_column("video_audio_enabled")
