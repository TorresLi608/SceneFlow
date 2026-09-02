"""track explicit empty scene references

Revision ID: a1b2c3d4e5f6
Revises: f1c2d3e4a5b6
Create Date: 2026-08-28
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "f1c2d3e4a5b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in inspect(op.get_bind()).get_columns("scenes")}
    for name in ("image_references_explicit", "video_references_explicit"):
        if name not in columns:
            op.add_column("scenes", sa.Column(name, sa.Boolean(), nullable=False, server_default=sa.text("0")))


def downgrade() -> None:
    columns = {column["name"] for column in inspect(op.get_bind()).get_columns("scenes")}
    with op.batch_alter_table("scenes") as batch_op:
        for name in ("image_references_explicit", "video_references_explicit"):
            if name in columns:
                batch_op.drop_column(name)
