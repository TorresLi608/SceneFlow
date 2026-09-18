"""add account image/video generation history

Revision ID: c8d1e2f3a4b5
Revises: b7e2a91c6d04
Create Date: 2026-09-18
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel
from sqlalchemy import inspect


revision: str = "c8d1e2f3a4b5"
down_revision: Union[str, Sequence[str], None] = "b7e2a91c6d04"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    if "generation_records" in set(inspector.get_table_names()):
        return
    op.create_table(
        "generation_records",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("created_at", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("deleted_at", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("kind", sqlmodel.sql.sqltypes.AutoString(length=16), nullable=False),
        sa.Column("path", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("media_type", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("prompt", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=sa.text("''")),
        sa.Column("provider", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=sa.text("''")),
        sa.Column("model_name", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=sa.text("''")),
        sa.Column("source", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=sa.text("''")),
        sa.Column("options_json", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=sa.text("'{}'")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_generation_records_user_kind", "generation_records", ["user_id", "kind"])
    op.create_index("idx_generation_records_deleted_at", "generation_records", ["deleted_at"])


def downgrade() -> None:
    op.drop_index("idx_generation_records_deleted_at", table_name="generation_records")
    op.drop_index("idx_generation_records_user_kind", table_name="generation_records")
    op.drop_table("generation_records")
