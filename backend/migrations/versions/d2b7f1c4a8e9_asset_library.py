"""project asset library"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel

revision: str = "d2b7f1c4a8e9"
down_revision: Union[str, Sequence[str], None] = "c93e7a1b4d20"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "assets",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("created_at", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("updated_at", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("deleted_at", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("project_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(length=120), nullable=False),
        sa.Column("description", sqlmodel.sql.sqltypes.AutoString(), server_default=sa.text("''"), nullable=False),
        sa.Column("kind", sqlmodel.sql.sqltypes.AutoString(length=16), nullable=False),
        sa.Column("media_type", sqlmodel.sql.sqltypes.AutoString(), server_default=sa.text("'application/octet-stream'"), nullable=False),
        sa.Column("path", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_assets_project_kind", "assets", ["project_id", "kind"])
    op.create_index("idx_assets_deleted_at", "assets", ["deleted_at"])


def downgrade() -> None:
    op.drop_index("idx_assets_deleted_at", table_name="assets")
    op.drop_index("idx_assets_project_kind", table_name="assets")
    op.drop_table("assets")
