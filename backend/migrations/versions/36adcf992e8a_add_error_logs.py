"""add error logs

Revision ID: 36adcf992e8a
Revises: b2c3d4e5f6a7
Create Date: 2026-09-01 11:17:55.794349

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '36adcf992e8a'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # The baseline creates missing tables from current metadata for pre-Alembic databases.
    if "error_logs" in inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "error_logs",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("created_at", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("request_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("method", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("route", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("error_code", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("message", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("project_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("episode_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_error_logs_created", "error_logs", ["created_at"])
    op.create_index("idx_error_logs_code_created", "error_logs", ["error_code", "created_at"])
    op.create_index("idx_error_logs_project_created", "error_logs", ["project_id", "created_at"])
    op.create_index("idx_error_logs_request_id", "error_logs", ["request_id"], unique=True)


def downgrade() -> None:
    if "error_logs" not in inspect(op.get_bind()).get_table_names():
        return
    op.drop_index("idx_error_logs_request_id", table_name="error_logs")
    op.drop_index("idx_error_logs_project_created", table_name="error_logs")
    op.drop_index("idx_error_logs_code_created", table_name="error_logs")
    op.drop_index("idx_error_logs_created", table_name="error_logs")
    op.drop_table("error_logs")
