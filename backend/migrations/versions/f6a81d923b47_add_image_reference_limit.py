"""add image reference limit

Revision ID: f6a81d923b47
Revises: e5c94a1f6d38
Create Date: 2026-08-18
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "f6a81d923b47"
down_revision: Union[str, Sequence[str], None] = "e5c94a1f6d38"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    columns = {column["name"] for column in inspect(op.get_bind()).get_columns("model_configs")}
    if "image_max_reference_images" not in columns:
        with op.batch_alter_table("model_configs") as batch_op:
            batch_op.add_column(sa.Column("image_max_reference_images", sa.Integer(), nullable=False, server_default="4"))


def downgrade() -> None:
    columns = {column["name"] for column in inspect(op.get_bind()).get_columns("model_configs")}
    if "image_max_reference_images" in columns:
        with op.batch_alter_table("model_configs") as batch_op:
            batch_op.drop_column("image_max_reference_images")
