"""character states, props, and merged reference sheets

Revision ID: 8a41c0d7b2e5
Revises: 6655a5517a16
Create Date: 2026-08-14 15:05:00.000000

`character_variants` becomes `character_states`. The rows carry over untouched: an
episode-scoped variant is simply a state that happens to pin `from_episode`, which is why
that column becomes nullable rather than gaining a default.

Every step is guarded. The baseline's legacy path ends in `_rebuild_schema()`, which builds
tables from *current* SQLModel metadata, so on an upgrade from a pre-Alembic database this
schema is already in place by the time this revision runs.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '8a41c0d7b2e5'
down_revision: Union[str, Sequence[str], None] = '6655a5517a16'
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
    inspector = inspect(op.get_bind())
    tables = set(inspector.get_table_names())

    if 'character_variants' in tables and 'character_states' not in tables:
        # Drop the old indexes first: SQLite carries index names across a table rename, so
        # recreating them under the new name would collide.
        for index in inspector.get_indexes('character_variants'):
            op.drop_index(index['name'], table_name='character_variants')
        op.rename_table('character_variants', 'character_states')

    # Each block is skipped when its table is absent. A database stamped past the baseline
    # without ever running it has only a partial schema, and there is nothing to extend.
    if 'character_states' in _tables():
        state_columns = _columns('character_states')
        additions = [
            ('description', sa.Column('description', sqlmodel.sql.sqltypes.AutoString(), server_default=sa.text("('')"), nullable=False)),
            ('system_prompt', sa.Column('system_prompt', sqlmodel.sql.sqltypes.AutoString(), server_default=sa.text("('')"), nullable=False)),
            ('final_prompt', sa.Column('final_prompt', sqlmodel.sql.sqltypes.AutoString(), server_default=sa.text("('')"), nullable=False)),
            ('order_num', sa.Column('order_num', sa.Integer(), server_default=sa.text('0'), nullable=False)),
        ]
        for name, column in additions:
            if name not in state_columns:
                op.add_column('character_states', column)
        # A state that is one of several parallel looks is not pinned to the timeline. Batch
        # is unavoidable here (SQLite cannot relax NOT NULL in place) but safe: every column
        # this table has in the model exists by now, so the recreate has nothing to reorder.
        if any(
            column['name'] == 'from_episode' and not column['nullable']
            for column in inspect(op.get_bind()).get_columns('character_states')
        ):
            with op.batch_alter_table('character_states', schema=None) as batch_op:
                batch_op.alter_column('from_episode', existing_type=sa.Integer(), nullable=True, server_default=None)

        state_indexes = _indexes('character_states')
        if 'idx_character_states_character' not in state_indexes:
            op.create_index('idx_character_states_character', 'character_states', ['character_id', 'from_episode'])
        if 'idx_character_states_deleted_at' not in state_indexes:
            op.create_index('idx_character_states_deleted_at', 'character_states', ['deleted_at'])

    if 'characters' in _tables() and 'sheet_image_path' not in _columns('characters'):
        op.add_column('characters', sa.Column('sheet_image_path', sqlmodel.sql.sqltypes.AutoString(), nullable=True))

    if 'projects' in _tables():
        project_columns = _columns('projects')
        if 'character_sheet_path' not in project_columns:
            op.add_column('projects', sa.Column('character_sheet_path', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
        if 'prop_sheet_path' not in project_columns:
            op.add_column('projects', sa.Column('prop_sheet_path', sqlmodel.sql.sqltypes.AutoString(), nullable=True))

    if 'props' not in _tables():
        op.create_table(
            'props',
            sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column('created_at', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.Column('updated_at', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.Column('deleted_at', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.Column('project_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column('name', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column('description', sqlmodel.sql.sqltypes.AutoString(), server_default=sa.text("('')"), nullable=False),
            sa.Column('system_prompt', sqlmodel.sql.sqltypes.AutoString(), server_default=sa.text("('')"), nullable=False),
            sa.Column('final_prompt', sqlmodel.sql.sqltypes.AutoString(), server_default=sa.text("('')"), nullable=False),
            sa.Column('image_path', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.Column('order_num', sa.Integer(), server_default=sa.text('0'), nullable=False),
            sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id'),
        )
    prop_indexes = _indexes('props')
    if 'idx_props_project_id' not in prop_indexes:
        op.create_index('idx_props_project_id', 'props', ['project_id'])
    if 'idx_props_deleted_at' not in prop_indexes:
        op.create_index('idx_props_deleted_at', 'props', ['deleted_at'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('idx_props_deleted_at', table_name='props')
    op.drop_index('idx_props_project_id', table_name='props')
    op.drop_table('props')

    with op.batch_alter_table('projects', schema=None) as batch_op:
        batch_op.drop_column('prop_sheet_path')
        batch_op.drop_column('character_sheet_path')

    with op.batch_alter_table('characters', schema=None) as batch_op:
        batch_op.drop_column('sheet_image_path')

    op.drop_index('idx_character_states_deleted_at', table_name='character_states')
    op.drop_index('idx_character_states_character', table_name='character_states')
    # Rows added as unpinned states have no episode to fall back to, so they take the
    # column's original default rather than blocking the downgrade.
    op.execute("UPDATE character_states SET from_episode = 1 WHERE from_episode IS NULL")
    with op.batch_alter_table('character_states', schema=None) as batch_op:
        batch_op.alter_column('from_episode', existing_type=sa.Integer(), nullable=False, server_default=sa.text('1'))
        batch_op.drop_column('order_num')
        batch_op.drop_column('final_prompt')
        batch_op.drop_column('system_prompt')
        batch_op.drop_column('description')
    op.rename_table('character_states', 'character_variants')
    op.create_index('idx_character_variants_character', 'character_variants', ['character_id', 'from_episode'])
    op.create_index('idx_character_variants_deleted_at', 'character_variants', ['deleted_at'])
