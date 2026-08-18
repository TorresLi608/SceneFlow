"""voice profiles and the merged timbre reference track

Revision ID: c3f18d7ae204
Revises: 8a41c0d7b2e5
Create Date: 2026-08-17 10:20:00.000000

Guarded like its predecessors: the baseline's legacy path ends in `_rebuild_schema()`, which
builds tables from *current* SQLModel metadata, so on an upgrade from a pre-Alembic database
this schema is already in place by the time this revision runs.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'c3f18d7ae204'
down_revision: Union[str, Sequence[str], None] = '8a41c0d7b2e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _tables() -> set[str]:
    return set(inspect(op.get_bind()).get_table_names())


def _columns(table: str) -> set[str]:
    return {column['name'] for column in inspect(op.get_bind()).get_columns(table)}


def _indexes(table: str) -> set[str]:
    return {index['name'] for index in inspect(op.get_bind()).get_indexes(table)}


def upgrade() -> None:
    """Upgrade schema."""
    if 'voice_profiles' not in _tables():
        op.create_table(
            'voice_profiles',
            sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column('created_at', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.Column('updated_at', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.Column('deleted_at', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.Column('project_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column('name', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column('note', sqlmodel.sql.sqltypes.AutoString(), server_default=sa.text("('')"), nullable=False),
            sa.Column('voice_provider', sqlmodel.sql.sqltypes.AutoString(), server_default=sa.text("('')"), nullable=False),
            sa.Column('voice_model', sqlmodel.sql.sqltypes.AutoString(), server_default=sa.text("('')"), nullable=False),
            sa.Column('sample_text', sqlmodel.sql.sqltypes.AutoString(), server_default=sa.text("('')"), nullable=False),
            sa.Column('audio_path', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.Column('order_num', sa.Integer(), server_default=sa.text('0'), nullable=False),
            sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id'),
        )
    profile_indexes = _indexes('voice_profiles')
    if 'idx_voice_profiles_project_id' not in profile_indexes:
        op.create_index('idx_voice_profiles_project_id', 'voice_profiles', ['project_id'])
    if 'idx_voice_profiles_deleted_at' not in profile_indexes:
        op.create_index('idx_voice_profiles_deleted_at', 'voice_profiles', ['deleted_at'])

    if 'characters' in _tables() and 'voice_profile_id' not in _columns('characters'):
        # Added without the foreign key: SQLite cannot add a constrained column in place, and
        # a batch recreate here would reflect into the shared SQLModel metadata. The binding
        # is cleaned up in application code when a profile is deleted.
        op.add_column('characters', sa.Column('voice_profile_id', sqlmodel.sql.sqltypes.AutoString(), nullable=True))

    if 'projects' in _tables() and 'voice_sheet_path' not in _columns('projects'):
        op.add_column('projects', sa.Column('voice_sheet_path', sqlmodel.sql.sqltypes.AutoString(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('projects', schema=None) as batch_op:
        batch_op.drop_column('voice_sheet_path')
    with op.batch_alter_table('characters', schema=None) as batch_op:
        batch_op.drop_column('voice_profile_id')
    op.drop_index('idx_voice_profiles_deleted_at', table_name='voice_profiles')
    op.drop_index('idx_voice_profiles_project_id', table_name='voice_profiles')
    op.drop_table('voice_profiles')
