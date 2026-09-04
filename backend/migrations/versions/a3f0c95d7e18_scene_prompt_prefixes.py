"""scene prompt prefixes

Revision ID: a3f0c95d7e18
Revises: 36adcf992e8a
Create Date: 2026-09-03
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "a3f0c95d7e18"
down_revision: Union[str, Sequence[str], None] = "36adcf992e8a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


COLUMNS = ("image_prompt_prefixes_json", "video_prompt_prefixes_json")


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    # Same guard as `c93e7a1b4d20`: a database stamped at an earlier revision need not carry
    # every table yet, and reflecting one that is absent raises rather than skipping.
    if "scenes" not in set(inspector.get_table_names()):
        return
    columns = {column["name"] for column in inspector.get_columns("scenes")}
    for name in COLUMNS:
        if name not in columns:
            op.add_column(
                "scenes",
                sa.Column(name, sa.Text(), nullable=False, server_default=sa.text("'[]'")),
            )


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    if "scenes" not in set(inspector.get_table_names()):
        return
    columns = {column["name"] for column in inspector.get_columns("scenes")}
    with op.batch_alter_table("scenes") as batch_op:
        for name in COLUMNS:
            if name in columns:
                batch_op.drop_column(name)
