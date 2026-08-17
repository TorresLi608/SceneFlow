"""export jobs merge chosen shots

Revision ID: e5c94a1f6d38
Revises: d7b25e91c840
Create Date: 2026-08-17 13:05:00.000000

`export_jobs.episode_ids` becomes `source_scene_ids`. Videos are rendered per shot and the
user picks and orders the clips, so an export is a list of shots rather than of episodes.
The table has never had a service or an endpoint, so there are no rows to carry over — but
the rename is still guarded, like every other revision here.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'e5c94a1f6d38'
down_revision: Union[str, Sequence[str], None] = 'd7b25e91c840'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    inspector = inspect(op.get_bind())
    if 'export_jobs' not in set(inspector.get_table_names()):
        return
    columns = {column['name'] for column in inspector.get_columns('export_jobs')}
    if 'source_scene_ids' not in columns:
        op.add_column(
            'export_jobs',
            sa.Column('source_scene_ids', sqlmodel.sql.sqltypes.AutoString(), server_default=sa.text("('[]')"), nullable=False),
        )
    if 'episode_ids' in columns:
        with op.batch_alter_table('export_jobs', schema=None) as batch_op:
            batch_op.drop_column('episode_ids')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column(
        'export_jobs',
        sa.Column('episode_ids', sqlmodel.sql.sqltypes.AutoString(), server_default=sa.text("('[]')"), nullable=False),
    )
    with op.batch_alter_table('export_jobs', schema=None) as batch_op:
        batch_op.drop_column('source_scene_ids')
