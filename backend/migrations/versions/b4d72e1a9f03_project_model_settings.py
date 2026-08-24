"""project model settings, cover prompt, prop owner, video storyboard fields

Revision ID: b4d72e1a9f03
Revises: af31d8e6c9b0
Create Date: 2026-08-21

Four related additions, kept in one revision because they land together:

- `projects.cover_prompt` — the cover is now drawn from what the user asks for rather than
  from the title and synopsis.
- `projects.*_config_id` plus the image/video generation defaults — the model each series
  uses per purpose, and the parameters every render in it starts from. Plain columns, not
  foreign keys: SQLite cannot add a constrained column in place, and an unresolvable id
  falls back to the account default by design.
- `props.owner_character_id` — whose prop it is, printed on the reference image.
- `scenes.transition` / `scenes.video_prompt` — the two things a shot needs before a clip
  can be generated from it that the old parse never produced.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
import sqlmodel


revision: str = "b4d72e1a9f03"
down_revision: Union[str, Sequence[str], None] = "af31d8e6c9b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (table, column, type, server_default). A None default means the column is nullable.
# AutoString, not sa.Text: it is what SQLModel maps `str` to, and `alembic check` compares
# types — a Text column here reads as a permanent pending migration.
ADDITIONS: tuple[tuple[str, str, object, str | None], ...] = (
    ("projects", "cover_prompt", sqlmodel.sql.sqltypes.AutoString(), "('')"),
    ("projects", "text_config_id", sa.Integer(), None),
    ("projects", "image_config_id", sa.Integer(), None),
    ("projects", "video_config_id", sa.Integer(), None),
    ("projects", "audio_config_id", sa.Integer(), None),
    ("projects", "image_resolution", sqlmodel.sql.sqltypes.AutoString(), "('2K')"),
    ("projects", "image_ratio", sqlmodel.sql.sqltypes.AutoString(), "('auto')"),
    ("projects", "video_quality", sqlmodel.sql.sqltypes.AutoString(), "('720p')"),
    ("projects", "video_aspect_ratio", sqlmodel.sql.sqltypes.AutoString(), "('9:16')"),
    ("projects", "video_duration", sa.Integer(), "5"),
    ("projects", "video_fps", sa.Integer(), "24"),
    ("projects", "video_prompt_extend", sa.Boolean(), "0"),
    ("props", "owner_character_id", sqlmodel.sql.sqltypes.AutoString(), None),
    ("scenes", "transition", sqlmodel.sql.sqltypes.AutoString(), "('')"),
    ("scenes", "video_prompt", sqlmodel.sql.sqltypes.AutoString(), "('')"),
)


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    for table in ("projects", "props", "scenes"):
        if table not in tables:
            # Stamped past the baseline without running it: whatever creates the table will
            # do so from current metadata, which already holds these columns.
            continue
        # Guarded because the baseline's legacy path rebuilds tables from *current* SQLModel
        # metadata, so on an upgrade from a pre-Alembic database these already exist.
        columns = {column["name"] for column in inspector.get_columns(table)}
        for owner, name, column_type, default in ADDITIONS:
            if owner != table or name in columns:
                continue
            # Plain add_column, not batch: SQLite recreates a table in batch mode when a new
            # column carries a server default, and that recreate reflects into the shared
            # SQLModel metadata, which already holds columns later revisions add. ALTER TABLE
            # ADD COLUMN handles a constant default natively.
            op.add_column(
                table,
                sa.Column(
                    name,
                    column_type,
                    server_default=sa.text(default) if default is not None else None,
                    nullable=default is None,
                ),
            )


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    for table in ("projects", "props", "scenes"):
        if table not in tables:
            continue
        columns = {column["name"] for column in inspector.get_columns(table)}
        pending = [name for owner, name, _, _ in ADDITIONS if owner == table and name in columns]
        if not pending:
            continue
        # Batch is unavoidable here: SQLite has no ALTER TABLE DROP COLUMN before 3.35, and
        # dropping is the one direction that genuinely needs the table rebuilt.
        with op.batch_alter_table(table, schema=None) as batch_op:
            for name in pending:
                batch_op.drop_column(name)
