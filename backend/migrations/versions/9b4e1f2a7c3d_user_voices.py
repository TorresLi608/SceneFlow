"""add account voice design results

Revision ID: 9b4e1f2a7c3d
Revises: f6a81d923b47
Create Date: 2026-08-19
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel
from sqlalchemy import inspect


revision: str = "9b4e1f2a7c3d"
down_revision: Union[str, Sequence[str], None] = "f6a81d923b47"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    if "user_voices" in set(inspector.get_table_names()):
        return
    op.create_table(
        "user_voices",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("created_at", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("updated_at", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("deleted_at", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("voice_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("target_model", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="qwen3-tts-vd-2026-01-26"),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=sa.text("''")),
        sa.Column("voice_prompt", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=sa.text("''")),
        sa.Column("preview_text", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=sa.text("''")),
        sa.Column("preview_audio_path", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_user_voices_user_id", "user_voices", ["user_id"])
    op.create_index("idx_user_voices_deleted_at", "user_voices", ["deleted_at"])


def downgrade() -> None:
    op.drop_index("idx_user_voices_deleted_at", table_name="user_voices")
    op.drop_index("idx_user_voices_user_id", table_name="user_voices")
    op.drop_table("user_voices")
