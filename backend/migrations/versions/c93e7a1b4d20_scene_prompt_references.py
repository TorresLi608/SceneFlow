"""scene prompt reference mentions

Revision ID: c93e7a1b4d20
Revises: b4d72e1a9f03
Create Date: 2026-08-24
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
import sqlmodel


revision: str = "c93e7a1b4d20"
down_revision: Union[str, Sequence[str], None] = "b4d72e1a9f03"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


COLUMNS = ("image_references_json", "video_references_json")


def upgrade() -> None:
    columns = {column["name"] for column in inspect(op.get_bind()).get_columns("scenes")}
    for name in COLUMNS:
        if name not in columns:
            op.add_column(
                "scenes",
                sa.Column(name, sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=sa.text("'[]'")),
            )


def downgrade() -> None:
    columns = {column["name"] for column in inspect(op.get_bind()).get_columns("scenes")}
    with op.batch_alter_table("scenes") as batch_op:
        for name in COLUMNS:
            if name in columns:
                batch_op.drop_column(name)
