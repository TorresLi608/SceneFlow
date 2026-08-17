"""add project description and cover image

Revision ID: 6655a5517a16
Revises: 7c1a9f4e2b6d
Create Date: 2026-08-14 14:17:53.373864

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '6655a5517a16'
down_revision: Union[str, Sequence[str], None] = '7c1a9f4e2b6d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    inspector = inspect(op.get_bind())
    if 'projects' not in set(inspector.get_table_names()):
        # A database stamped past the baseline without ever running it has no projects
        # table to extend; whatever creates it will do so from current metadata.
        return
    # Guarded because the baseline's legacy path ends in `_rebuild_schema()`, which builds
    # tables from *current* SQLModel metadata — so on an upgrade from a pre-Alembic database
    # these columns already exist by the time this revision runs.
    columns = {column['name'] for column in inspector.get_columns('projects')}
    # Plain add_column, not batch: SQLite recreates a table in batch mode when a new column
    # carries a server default, and that recreate reflects into the shared SQLModel metadata,
    # which already holds columns later revisions add. ALTER TABLE ADD COLUMN handles a
    # constant default natively.
    if 'description' not in columns:
        op.add_column('projects', sa.Column('description', sqlmodel.sql.sqltypes.AutoString(), server_default=sa.text("('')"), nullable=False))
    if 'cover_image_path' not in columns:
        op.add_column('projects', sa.Column('cover_image_path', sqlmodel.sql.sqltypes.AutoString(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('projects', schema=None) as batch_op:
        batch_op.drop_column('cover_image_path')
        batch_op.drop_column('description')
