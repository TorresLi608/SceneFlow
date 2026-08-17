"""episode tone sheet

Revision ID: d7b25e91c840
Revises: c3f18d7ae204
Create Date: 2026-08-17 11:40:00.000000

Guarded like its predecessors: the baseline's legacy path ends in `_rebuild_schema()`, which
builds tables from *current* SQLModel metadata, so on an upgrade from a pre-Alembic database
these columns already exist by the time this revision runs.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'd7b25e91c840'
down_revision: Union[str, Sequence[str], None] = 'c3f18d7ae204'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    inspector = inspect(op.get_bind())
    if 'episodes' not in set(inspector.get_table_names()):
        return
    columns = {column['name'] for column in inspector.get_columns('episodes')}
    if 'tone_image_path' not in columns:
        op.add_column('episodes', sa.Column('tone_image_path', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    if 'tone_image_status' not in columns:
        op.add_column(
            'episodes',
            sa.Column('tone_image_status', sqlmodel.sql.sqltypes.AutoString(), server_default=sa.text("('idle')"), nullable=False),
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('episodes', schema=None) as batch_op:
        batch_op.drop_column('tone_image_status')
        batch_op.drop_column('tone_image_path')
