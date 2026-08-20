"""track saved user voice designs

Revision ID: af31d8e6c9b0
Revises: 9b4e1f2a7c3d
Create Date: 2026-08-19
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "af31d8e6c9b0"
down_revision: Union[str, Sequence[str], None] = "9b4e1f2a7c3d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if "is_saved" not in {column["name"] for column in inspect(op.get_bind()).get_columns("user_voices")}:
        with op.batch_alter_table("user_voices") as batch_op:
            batch_op.add_column(sa.Column("is_saved", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    if "is_saved" in {column["name"] for column in inspect(op.get_bind()).get_columns("user_voices")}:
        with op.batch_alter_table("user_voices") as batch_op:
            batch_op.drop_column("is_saved")
