"""add email to users and create email_verifications table"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = "e7f1a9b2c3d4"
down_revision: Union[str, Sequence[str], None] = "d2b7f1c4a8e9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("email", sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.create_index("idx_users_email", "users", ["email"], unique=True)

    op.create_table(
        "email_verifications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("expires_at", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("email", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("code", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("used_at", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("ip_address", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sqlite_autoincrement=True,
    )
    op.create_index("idx_email_verifications_email", "email_verifications", ["email"])
    op.create_index("idx_email_verifications_created_at", "email_verifications", ["created_at"])


def downgrade() -> None:
    op.drop_index("idx_email_verifications_created_at", table_name="email_verifications")
    op.drop_index("idx_email_verifications_email", table_name="email_verifications")
    op.drop_table("email_verifications")
    op.drop_index("idx_users_email", table_name="users")
    op.drop_column("users", "email")
