"""baseline schema

Revision ID: 345000649eb5
Revises: 
Create Date: 2026-08-12 17:16:20.407736

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, or_
import sqlmodel
from sqlmodel import SQLModel, Session, select

import app.models  # noqa: F401 -- register all SQLModel tables
from app.models import ChatSession, Episode, ModelConfig, Project, Scene, UsageLog, UserOfficialConfigDefault
from app.services.artifact_service import stored_relative_path
from app.utils.common import new_id, now


# revision identifiers, used by Alembic.
revision: str = '345000649eb5'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _tables() -> set[str]:
    return set(inspect(op.get_bind()).get_table_names()) - {"alembic_version"}


def _columns(table: str) -> set[str]:
    return {column["name"] for column in inspect(op.get_bind()).get_columns(table)}


def _add_columns(table: str, columns: list[sa.Column]) -> None:
    if table not in _tables():
        return
    existing = _columns(table)
    for column in columns:
        if column.name not in existing:
            op.add_column(table, column)


def _upgrade_existing_tables() -> None:
    string = sqlmodel.sql.sqltypes.AutoString
    _add_columns("users", [
        sa.Column("role", string(), server_default="user"),
        sa.Column("is_disabled", sa.Boolean(), server_default=sa.false()),
        sa.Column("balance_micros", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("level", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("user_group", string(), nullable=False, server_default="default"),
    ])
    _add_columns("projects", [
        sa.Column("title", string()),
        sa.Column("video_progress", sa.Integer(), server_default="0"),
        sa.Column("mode", string(), nullable=False, server_default="comic"),
        sa.Column("aspect_ratio", string(), nullable=False, server_default="9:16"),
        sa.Column("width", sa.Integer(), nullable=False, server_default="1080"),
        sa.Column("height", sa.Integer(), nullable=False, server_default="1920"),
        sa.Column("fps", sa.Integer(), nullable=False, server_default="24"),
        sa.Column("target_duration_ms", sa.Integer(), nullable=False, server_default="60000"),
        sa.Column("language", string(), nullable=False, server_default="zh-CN"),
        sa.Column("style_prompt", string(), nullable=False, server_default=""),
        sa.Column("negative_prompt", string(), nullable=False, server_default=""),
        sa.Column("current_stage", string(), nullable=False, server_default="script"),
        sa.Column("series_bible", string(), nullable=False, server_default=""),
    ])
    _add_columns("chat_messages", [
        sa.Column("attachments", string()),
        sa.Column("reasoning", string()),
    ])
    _add_columns("chat_sessions", [
        sa.Column("official_config_id", sa.Integer()),
        sa.Column("context_summary", string()),
        sa.Column("context_summary_until", string()),
    ])
    _add_columns("model_configs", [sa.Column("pricing_json", string())])
    _add_columns("usage_logs", [sa.Column("pricing_json", string())])
    _add_columns("invitation_codes", [sa.Column("created_by_user_id", sa.Integer())])
    _add_columns("redemption_codes", [sa.Column("created_by_user_id", sa.Integer())])

    if "scenes" in _tables():
        scene_columns = _columns("scenes")
        for old_name, new_name in (("image_url", "image_path"), ("audio_url", "audio_path")):
            if new_name not in scene_columns:
                if old_name in scene_columns:
                    op.alter_column("scenes", old_name, new_column_name=new_name)
                else:
                    op.add_column("scenes", sa.Column(new_name, string()))
        _add_columns("scenes", [
            sa.Column("episode_id", string()),
            sa.Column("dialogue", string(), nullable=False, server_default=""),
            sa.Column("speaker_character_id", string()),
            sa.Column("shot_type", string(), nullable=False, server_default=""),
            sa.Column("camera_move", string(), nullable=False, server_default=""),
            sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("subtitle_text", string(), nullable=False, server_default=""),
            sa.Column("audio_duration", sa.Float(), nullable=False, server_default="0"),
            sa.Column("video_path", string()),
            sa.Column("video_status", string(), nullable=False, server_default="idle"),
            sa.Column("is_locked", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("error_message", string()),
        ])
    _add_columns("generation_jobs", [sa.Column("episode_id", string())])


def _create_missing_tables() -> None:
    bind = op.get_bind()
    existing = _tables()
    for table in SQLModel.metadata.sorted_tables:
        if table.name not in existing:
            table.create(bind)


def _legacy_table(name: str) -> sa.Table:
    return sa.Table(name, sa.MetaData(), autoload_with=op.get_bind())


def _add_legacy_config_columns(table: str) -> None:
    string = sqlmodel.sql.sqltypes.AutoString
    _add_columns(table, [
        sa.Column("base_url", string()),
        sa.Column("is_enabled", sa.Boolean(), server_default=sa.true()),
        sa.Column("pricing_multiplier", sa.Float(), server_default="1"),
        sa.Column("input_price_per_million", sa.Float(), server_default="0"),
        sa.Column("output_price_per_million", sa.Float(), server_default="0"),
        sa.Column("cache_read_price_per_million", sa.Float(), server_default="0"),
        sa.Column("cache_write_price_per_million", sa.Float(), server_default="0"),
        sa.Column("unit_price", sa.Float(), server_default="0"),
        sa.Column("unit_name", string(), server_default="token"),
    ])


def _migrate_legacy_model_configs(session: Session) -> None:
    legacy_names = [name for name in ("user_configs", "official_model_configs") if name in _tables()]
    if not legacy_names:
        return
    for name in legacy_names:
        _add_legacy_config_columns(name)

    id_maps: dict[str, dict[int, int]] = {"user": {}, "official": {}}
    shared = (
        "created_at", "updated_at", "deleted_at", "provider", "encrypted_key", "is_active", "is_enabled",
        "purpose", "model_name", "is_verified", "name", "description", "base_url", "pricing_multiplier",
        "input_price_per_million", "output_price_per_million", "cache_read_price_per_million",
        "cache_write_price_per_million", "unit_price", "unit_name",
    )
    for table_name, source in (("user_configs", "user"), ("official_model_configs", "official")):
        if table_name not in legacy_names:
            continue
        table = _legacy_table(table_name)
        columns = [
            sa.cast(column, sa.String()).label(column.name)
            if isinstance(column.type, sa.DateTime)
            else column
            for column in table.columns
        ]
        rows = session.execute(sa.select(*columns).order_by(table.c.id)).mappings().all()
        for row in rows:
            config = ModelConfig(
                user_id=row.get("user_id") if source == "user" else None,
                source=source,
                **{name: row.get(name) for name in shared},
            )
            session.add(config)
            session.flush()
            id_maps[source][int(row["id"])] = int(config.id)

    for item in session.exec(select(UserOfficialConfigDefault)).all():
        item.official_config_id = id_maps["official"].get(item.official_config_id, item.official_config_id)
        session.add(item)
    for chat in session.exec(select(ChatSession)).all():
        if chat.config_id is not None:
            chat.config_id = id_maps["user"].get(chat.config_id, chat.config_id)
        if chat.official_config_id is not None:
            chat.official_config_id = id_maps["official"].get(chat.official_config_id, chat.official_config_id)
        session.add(chat)
    for usage in session.exec(select(UsageLog).where(UsageLog.config_id.is_not(None))).all():
        usage.config_id = id_maps.get(usage.config_source, {}).get(int(usage.config_id), usage.config_id)
        session.add(usage)
    session.flush()
    for table_name in legacy_names:
        op.drop_table(table_name)


def _migrate_scene_assets(session: Session) -> None:
    # Core SQL naming only the columns this rewrite touches, for the same reason as
    # `_backfill_first_episode` below: the legacy `scenes` table predates every column
    # added since, and an ORM select would name today's full column list against
    # yesterday's table — so any future column on Scene would break upgrading a legacy
    # database. (It did, when `transition` and `video_prompt` were added.)
    scenes = sa.table("scenes", sa.column("id"), sa.column("image_path"), sa.column("audio_path"))
    rows = session.execute(
        sa.select(scenes.c.id, scenes.c.image_path, scenes.c.audio_path).where(
            or_(scenes.c.image_path.like("http%"), scenes.c.audio_path.like("http%"))
        )
    ).mappings().all()
    for row in rows:
        updates: dict[str, str | None] = {}
        for field in ("image_path", "audio_path"):
            value = str(row[field] or "")
            if not value.startswith("http"):
                continue
            try:
                updates[field] = stored_relative_path(value)
            except Exception:
                # The token no longer decodes, so the link was already dead; drop it rather
                # than carrying a reference that can only ever 404.
                updates[field] = None
        if updates:
            session.execute(sa.update(scenes).where(scenes.c.id == row["id"]).values(**updates))


def _backfill_first_episode(session: Session) -> None:
    # Read `projects` with core SQL naming only the columns this backfill needs, rather
    # than through the Project model. The legacy table predates every column added since,
    # and an ORM select would name today's full column list against yesterday's table —
    # so any future column on Project would break upgrading a legacy database.
    rows = session.execute(
        sa.select(
            sa.column("id"),
            sa.column("created_at"),
            sa.column("updated_at"),
            sa.column("original_script"),
        )
        .select_from(sa.table("projects"))
        .where(sa.column("deleted_at").is_(None))
    ).mappings().all()
    for row in rows:
        project_id = row["id"]
        episodes = session.exec(
            select(Episode)
            .where(Episode.project_id == project_id, Episode.deleted_at.is_(None))
            .order_by(Episode.episode_number)
        ).all()
        # Core SQL for `scenes` too, and for the same reason as `projects` above: an ORM
        # select here names today's full column list against the legacy table, so every
        # column later added to Scene would break this upgrade. Episodes are exempt — that
        # table is created by this very revision, so it always matches the model.
        scenes = sa.table("scenes", sa.column("id"), sa.column("project_id"), sa.column("deleted_at"), sa.column("episode_id"))
        project_scenes = session.execute(
            sa.select(scenes.c.id, scenes.c.deleted_at, scenes.c.episode_id).where(scenes.c.project_id == project_id)
        ).mappings().all()
        if not episodes:
            stamp = row["updated_at"] or row["created_at"] or now()
            episode = Episode(
                id=new_id("ep"),
                created_at=row["created_at"] or stamp,
                updated_at=stamp,
                project_id=project_id,
                episode_number=1,
                title="第 1 集",
                source_text=row["original_script"] or "",
                status="storyboard" if any(scene["deleted_at"] is None for scene in project_scenes) else "draft",
            )
            session.add(episode)
            session.flush()
            episodes = [episode]
        orphans = [scene["id"] for scene in project_scenes if scene["episode_id"] is None]
        if orphans:
            session.execute(
                sa.update(scenes).where(scenes.c.id.in_(orphans)).values(episode_id=episodes[0].id)
            )


def _dependency_rank(name: str) -> int:
    """Where a table sits in foreign-key dependency order; higher means more dependent.

    Renaming a table aside carries its foreign keys with it, so the `_alembic_old_` copies
    have to be dropped children-first or SQLite refuses on a parent that a sibling still
    references. Metadata supplies the ordering only — never the shape, per `_rebuild_schema`.
    A table metadata no longer knows is genuinely legacy, and sorts last.
    """
    bare = name[len("_alembic_old_"):] if name.startswith("_alembic_old_") else name
    order = [table.name for table in SQLModel.metadata.sorted_tables]
    return order.index(bare) if bare in order else -1


def _rebuild_schema() -> None:
    """Copy an unversioned database into the tables *this revision* defines.

    Frozen on purpose. `_create_schema()` is the baseline, and the rebuild has to land on
    exactly that, because every revision after this one then runs on top of it. Building from
    `SQLModel.metadata` instead materialises *today's* schema, so each table added since —
    `assets`, `email_verifications` — already exists by the time its own migration calls
    `create_table`, and a legacy upgrade dies with "table already exists". That is the same
    trap the column-level comment in `_migrate_scene_assets` describes, one level up: a
    migration must not read a model that is still moving.

    Metadata is still used for one thing — the *order* tables are copied in, which has to
    respect foreign keys. Names only, never shape.
    """
    bind = op.get_bind()
    indexes = list(bind.execute(
        sa.text("SELECT name FROM sqlite_master WHERE type = 'index' AND sql IS NOT NULL")
    ).scalars())
    for name in indexes:
        op.drop_index(name)

    # Everything goes aside, including tables the staging step above created from live
    # metadata: whatever the baseline does not define is dropped below and rebuilt later by
    # the migration that owns it.
    for name in _tables():
        op.rename_table(name, f"_alembic_old_{name}")

    _create_schema()

    inspector = inspect(bind)
    present = set(inspector.get_table_names())
    ordered = [table.name for table in SQLModel.metadata.sorted_tables if table.name in present]
    ordered += sorted(name for name in present if name not in set(ordered) | {"alembic_version"}
                      and not name.startswith("_alembic_old_"))
    for name in ordered:
        old_name = f"_alembic_old_{name}"
        if old_name not in present:
            continue
        old_columns = {column["name"] for column in inspector.get_columns(old_name)}
        shared = [column["name"] for column in inspector.get_columns(name) if column["name"] in old_columns]
        if not shared:
            continue
        quoted = ", ".join(f'"{column}"' for column in shared)
        bind.execute(sa.text(f'INSERT INTO "{name}" ({quoted}) SELECT {quoted} FROM "{old_name}"'))

    for name in sorted(present, key=_dependency_rank, reverse=True):
        if name.startswith("_alembic_old_"):
            op.drop_table(name)


def _upgrade_legacy_schema() -> None:
    _upgrade_existing_tables()
    _create_missing_tables()
    with Session(op.get_bind(), expire_on_commit=False) as session:
        _migrate_legacy_model_configs(session)
        _migrate_scene_assets(session)
        _backfill_first_episode(session)
        session.flush()
    _rebuild_schema()


def _create_schema() -> None:
    """Upgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('projects',
    sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('created_at', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('updated_at', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('deleted_at', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('title', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('original_script', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('status', sqlmodel.sql.sqltypes.AutoString(), server_default=sa.text("'idle'"), nullable=True),
    sa.Column('video_url', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('video_status', sqlmodel.sql.sqltypes.AutoString(), server_default=sa.text("'idle'"), nullable=True),
    sa.Column('video_progress', sa.Integer(), server_default=sa.text('0'), nullable=True),
    sa.Column('mode', sqlmodel.sql.sqltypes.AutoString(), server_default=sa.text("'comic'"), nullable=False),
    sa.Column('aspect_ratio', sqlmodel.sql.sqltypes.AutoString(), server_default=sa.text("'9:16'"), nullable=False),
    sa.Column('width', sa.Integer(), server_default=sa.text('(1080)'), nullable=False),
    sa.Column('height', sa.Integer(), server_default=sa.text('(1920)'), nullable=False),
    sa.Column('fps', sa.Integer(), server_default=sa.text('(24)'), nullable=False),
    sa.Column('target_duration_ms', sa.Integer(), server_default=sa.text('(60000)'), nullable=False),
    sa.Column('language', sqlmodel.sql.sqltypes.AutoString(), server_default=sa.text("'zh-CN'"), nullable=False),
    sa.Column('style_prompt', sqlmodel.sql.sqltypes.AutoString(), server_default=sa.text("('')"), nullable=False),
    sa.Column('negative_prompt', sqlmodel.sql.sqltypes.AutoString(), server_default=sa.text("('')"), nullable=False),
    sa.Column('current_stage', sqlmodel.sql.sqltypes.AutoString(), server_default=sa.text("'script'"), nullable=False),
    sa.Column('series_bible', sqlmodel.sql.sqltypes.AutoString(), server_default=sa.text("('')"), nullable=False),
    sa.CheckConstraint("mode IN ('comic', 'drama')"),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('projects', schema=None) as batch_op:
        batch_op.create_index('idx_projects_deleted_at', ['deleted_at'], unique=False)
        batch_op.create_index('idx_projects_user_id', ['user_id'], unique=False)

    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('created_at', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('updated_at', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('deleted_at', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('username', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('password', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('role', sqlmodel.sql.sqltypes.AutoString(), server_default=sa.text("'user'"), nullable=True),
    sa.Column('is_disabled', sa.Boolean(), server_default=sa.text('(false)'), nullable=True),
    sa.Column('balance_micros', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('level', sa.Integer(), server_default=sa.text('1'), nullable=False),
    sa.Column('user_group', sqlmodel.sql.sqltypes.AutoString(), server_default=sa.text("'default'"), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('username'),
    sqlite_autoincrement=True
    )
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.create_index('idx_users_deleted_at', ['deleted_at'], unique=False)

    op.create_table('characters',
    sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('created_at', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('updated_at', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('deleted_at', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('project_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('name', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('aliases', sqlmodel.sql.sqltypes.AutoString(), server_default=sa.text("('')"), nullable=False),
    sa.Column('description', sqlmodel.sql.sqltypes.AutoString(), server_default=sa.text("('')"), nullable=False),
    sa.Column('appearance_prompt', sqlmodel.sql.sqltypes.AutoString(), server_default=sa.text("('')"), nullable=False),
    sa.Column('reference_image_path', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('image_provider', sqlmodel.sql.sqltypes.AutoString(), server_default=sa.text("('')"), nullable=False),
    sa.Column('image_model', sqlmodel.sql.sqltypes.AutoString(), server_default=sa.text("('')"), nullable=False),
    sa.Column('image_base_url', sqlmodel.sql.sqltypes.AutoString(), server_default=sa.text("('')"), nullable=False),
    sa.Column('voice_provider', sqlmodel.sql.sqltypes.AutoString(), server_default=sa.text("('')"), nullable=False),
    sa.Column('voice_model', sqlmodel.sql.sqltypes.AutoString(), server_default=sa.text("('')"), nullable=False),
    sa.Column('is_locked', sa.Boolean(), server_default=sa.text('0'), nullable=False),
    sa.Column('order_num', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('characters', schema=None) as batch_op:
        batch_op.create_index('idx_characters_deleted_at', ['deleted_at'], unique=False)
        batch_op.create_index('idx_characters_project_id', ['project_id'], unique=False)

    op.create_table('episodes',
    sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('created_at', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('updated_at', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('deleted_at', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('project_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('episode_number', sa.Integer(), nullable=False),
    sa.Column('title', sqlmodel.sql.sqltypes.AutoString(), server_default=sa.text("('')"), nullable=False),
    sa.Column('synopsis', sqlmodel.sql.sqltypes.AutoString(), server_default=sa.text("('')"), nullable=False),
    sa.Column('source_text', sqlmodel.sql.sqltypes.AutoString(), server_default=sa.text("('')"), nullable=False),
    sa.Column('status', sqlmodel.sql.sqltypes.AutoString(), server_default=sa.text("'draft'"), nullable=False),
    sa.Column('video_path', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('video_status', sqlmodel.sql.sqltypes.AutoString(), server_default=sa.text("'idle'"), nullable=False),
    sa.Column('video_progress', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('duration_ms', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('error_message', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.CheckConstraint('episode_number > 0'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('episodes', schema=None) as batch_op:
        batch_op.create_index('idx_episodes_deleted_at', ['deleted_at'], unique=False)
        batch_op.create_index('idx_episodes_project_number', ['project_id', 'episode_number'], unique=True, sqlite_where=sa.text('deleted_at IS NULL'))

    op.create_table('export_jobs',
    sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('created_at', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('updated_at', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('started_at', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('finished_at', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('project_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('episode_ids', sqlmodel.sql.sqltypes.AutoString(), server_default=sa.text("'[]'"), nullable=False),
    sa.Column('range_label', sqlmodel.sql.sqltypes.AutoString(), server_default=sa.text("('')"), nullable=False),
    sa.Column('status', sqlmodel.sql.sqltypes.AutoString(), server_default=sa.text("'queued'"), nullable=False),
    sa.Column('progress', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('output_path', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('file_size', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('include_subtitles', sa.Boolean(), server_default=sa.text('1'), nullable=False),
    sa.Column('title_cards', sa.Boolean(), server_default=sa.text('0'), nullable=False),
    sa.Column('transition', sqlmodel.sql.sqltypes.AutoString(), server_default=sa.text("'none'"), nullable=False),
    sa.Column('error_message', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.CheckConstraint("status IN ('queued', 'running', 'succeeded', 'failed', 'canceled')"),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('export_jobs', schema=None) as batch_op:
        batch_op.create_index('idx_export_jobs_user_id', ['user_id'], unique=False)

    op.create_table('invitation_codes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('created_at', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('expires_at', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('code', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('used_at', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('used_by_user_id', sa.Integer(), nullable=True),
    sa.Column('created_by_user_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['used_by_user_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('code'),
    sqlite_autoincrement=True
    )
    with op.batch_alter_table('invitation_codes', schema=None) as batch_op:
        batch_op.create_index('idx_invitation_codes_used_by', ['used_by_user_id'], unique=False)

    op.create_table('model_configs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('created_at', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('updated_at', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('deleted_at', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('source', sqlmodel.sql.sqltypes.AutoString(), server_default=sa.text("'user'"), nullable=False),
    sa.Column('provider', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('encrypted_key', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('(false)'), nullable=True),
    sa.Column('is_enabled', sa.Boolean(), server_default=sa.text('(true)'), nullable=True),
    sa.Column('purpose', sqlmodel.sql.sqltypes.AutoString(), server_default=sa.text("'script'"), nullable=True),
    sa.Column('model_name', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('is_verified', sa.Boolean(), server_default=sa.text('(false)'), nullable=True),
    sa.Column('name', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('description', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('base_url', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('pricing_multiplier', sa.Float(), server_default=sa.text('1'), nullable=True),
    sa.Column('input_price_per_million', sa.Float(), server_default=sa.text('0'), nullable=True),
    sa.Column('output_price_per_million', sa.Float(), server_default=sa.text('0'), nullable=True),
    sa.Column('cache_read_price_per_million', sa.Float(), server_default=sa.text('0'), nullable=True),
    sa.Column('cache_write_price_per_million', sa.Float(), server_default=sa.text('0'), nullable=True),
    sa.Column('unit_price', sa.Float(), server_default=sa.text('0'), nullable=True),
    sa.Column('unit_name', sqlmodel.sql.sqltypes.AutoString(), server_default=sa.text("'token'"), nullable=True),
    sa.Column('pricing_json', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.CheckConstraint("(source='user' AND user_id IS NOT NULL) OR (source='official' AND user_id IS NULL)"),
    sa.CheckConstraint("source IN ('user', 'official')"),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sqlite_autoincrement=True
    )
    with op.batch_alter_table('model_configs', schema=None) as batch_op:
        batch_op.create_index('idx_model_configs_deleted_at', ['deleted_at'], unique=False)
        batch_op.create_index('idx_model_configs_source_purpose', ['source', 'purpose'], unique=False)
        batch_op.create_index('idx_model_configs_user_id', ['user_id'], unique=False)

    op.create_table('redemption_codes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('created_at', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('expires_at', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('code', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('amount_micros', sa.Integer(), nullable=False),
    sa.Column('redeemed_at', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('redeemed_by_user_id', sa.Integer(), nullable=True),
    sa.Column('created_by_user_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['redeemed_by_user_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('code'),
    sqlite_autoincrement=True
    )
    with op.batch_alter_table('redemption_codes', schema=None) as batch_op:
        batch_op.create_index('idx_redemption_codes_redeemed_by', ['redeemed_by_user_id'], unique=False)

    op.create_table('usage_logs',
    sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('created_at', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('feature', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('config_source', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('config_id', sa.Integer(), nullable=True),
    sa.Column('provider', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('model_name', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('duration_ms', sa.Integer(), server_default=sa.text('0'), nullable=True),
    sa.Column('input_tokens', sa.Integer(), server_default=sa.text('0'), nullable=True),
    sa.Column('output_tokens', sa.Integer(), server_default=sa.text('0'), nullable=True),
    sa.Column('cache_read_tokens', sa.Integer(), server_default=sa.text('0'), nullable=True),
    sa.Column('cache_write_tokens', sa.Integer(), server_default=sa.text('0'), nullable=True),
    sa.Column('quantity', sa.Float(), server_default=sa.text('0'), nullable=True),
    sa.Column('cost_micros', sa.Integer(), server_default=sa.text('0'), nullable=True),
    sa.Column('pricing_multiplier', sa.Float(), server_default=sa.text('1'), nullable=True),
    sa.Column('input_price_per_million', sa.Float(), server_default=sa.text('0'), nullable=True),
    sa.Column('output_price_per_million', sa.Float(), server_default=sa.text('0'), nullable=True),
    sa.Column('cache_read_price_per_million', sa.Float(), server_default=sa.text('0'), nullable=True),
    sa.Column('cache_write_price_per_million', sa.Float(), server_default=sa.text('0'), nullable=True),
    sa.Column('unit_price', sa.Float(), server_default=sa.text('0'), nullable=True),
    sa.Column('unit_name', sqlmodel.sql.sqltypes.AutoString(), server_default=sa.text("'token'"), nullable=True),
    sa.Column('pricing_json', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('character_variants',
    sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('created_at', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('updated_at', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('deleted_at', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('character_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('name', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('appearance_prompt', sqlmodel.sql.sqltypes.AutoString(), server_default=sa.text("('')"), nullable=False),
    sa.Column('reference_image_path', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('voice_model', sqlmodel.sql.sqltypes.AutoString(), server_default=sa.text("('')"), nullable=False),
    sa.Column('from_episode', sa.Integer(), server_default=sa.text('1'), nullable=False),
    sa.Column('to_episode', sa.Integer(), nullable=True),
    sa.CheckConstraint('from_episode > 0'),
    sa.CheckConstraint('to_episode IS NULL OR to_episode >= from_episode'),
    sa.ForeignKeyConstraint(['character_id'], ['characters.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('character_variants', schema=None) as batch_op:
        batch_op.create_index('idx_character_variants_character', ['character_id', 'from_episode'], unique=False)
        batch_op.create_index('idx_character_variants_deleted_at', ['deleted_at'], unique=False)

    op.create_table('chat_sessions',
    sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('created_at', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('updated_at', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('deleted_at', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('title', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('config_id', sa.Integer(), nullable=True),
    sa.Column('official_config_id', sa.Integer(), nullable=True),
    sa.Column('provider', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('model_name', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('context_summary', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('context_summary_until', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.ForeignKeyConstraint(['config_id'], ['model_configs.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['official_config_id'], ['model_configs.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('chat_sessions', schema=None) as batch_op:
        batch_op.create_index('idx_chat_sessions_deleted_at', ['deleted_at'], unique=False)
        batch_op.create_index('idx_chat_sessions_user_id', ['user_id'], unique=False)

    op.create_table('scenes',
    sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('created_at', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('updated_at', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('deleted_at', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('project_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('episode_id', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('order_num', sa.Integer(), nullable=True),
    sa.Column('narration', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('dialogue', sqlmodel.sql.sqltypes.AutoString(), server_default=sa.text("('')"), nullable=False),
    sa.Column('speaker_character_id', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('visual_prompt', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('shot_type', sqlmodel.sql.sqltypes.AutoString(), server_default=sa.text("('')"), nullable=False),
    sa.Column('camera_move', sqlmodel.sql.sqltypes.AutoString(), server_default=sa.text("('')"), nullable=False),
    sa.Column('duration_ms', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('subtitle_text', sqlmodel.sql.sqltypes.AutoString(), server_default=sa.text("('')"), nullable=False),
    sa.Column('image_path', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('image_status', sqlmodel.sql.sqltypes.AutoString(), server_default=sa.text("'idle'"), nullable=True),
    sa.Column('audio_path', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('audio_status', sqlmodel.sql.sqltypes.AutoString(), server_default=sa.text("'idle'"), nullable=True),
    sa.Column('audio_duration', sa.Float(), server_default=sa.text('0'), nullable=False),
    sa.Column('video_path', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('video_status', sqlmodel.sql.sqltypes.AutoString(), server_default=sa.text("'idle'"), nullable=False),
    sa.Column('is_locked', sa.Boolean(), server_default=sa.text('0'), nullable=False),
    sa.Column('error_message', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.ForeignKeyConstraint(['episode_id'], ['episodes.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('scenes', schema=None) as batch_op:
        batch_op.create_index('idx_scenes_deleted_at', ['deleted_at'], unique=False)
        batch_op.create_index('idx_scenes_episode_order', ['episode_id', 'order_num'], unique=False)
        batch_op.create_index('idx_scenes_project_id', ['project_id'], unique=False)

    op.create_table('user_official_config_defaults',
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('purpose', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('official_config_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('updated_at', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.ForeignKeyConstraint(['official_config_id'], ['model_configs.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id', 'purpose')
    )
    op.create_table('chat_messages',
    sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('created_at', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('session_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('role', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('content', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('attachments', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('reasoning', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('provider', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('model_name', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.ForeignKeyConstraint(['session_id'], ['chat_sessions.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('chat_messages', schema=None) as batch_op:
        batch_op.create_index('idx_chat_messages_session_id', ['session_id'], unique=False)

    op.create_table('generation_jobs',
    sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('created_at', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('updated_at', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('started_at', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('finished_at', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('project_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('episode_id', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('scene_id', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('job_type', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('status', sqlmodel.sql.sqltypes.AutoString(), server_default=sa.text("'queued'"), nullable=False),
    sa.Column('progress', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('input_json', sqlmodel.sql.sqltypes.AutoString(), server_default=sa.text("'{}'"), nullable=False),
    sa.Column('result_json', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('attempt', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('max_attempts', sa.Integer(), server_default=sa.text('3'), nullable=False),
    sa.Column('idempotency_key', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('lease_owner', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('lease_expires_at', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('heartbeat_at', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('error_code', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('error_message', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.CheckConstraint("status IN ('queued', 'running', 'succeeded', 'failed', 'canceled')"),
    sa.ForeignKeyConstraint(['episode_id'], ['episodes.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['scene_id'], ['scenes.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('generation_jobs', schema=None) as batch_op:
        batch_op.create_index('idx_generation_jobs_idempotency', ['user_id', 'project_id', 'idempotency_key'], unique=True, sqlite_where=sa.text('idempotency_key IS NOT NULL'))
        batch_op.create_index('idx_generation_jobs_status_lease', ['status', 'lease_expires_at', 'created_at'], unique=False)

    op.create_table('scene_characters',
    sa.Column('scene_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('character_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('created_at', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.ForeignKeyConstraint(['character_id'], ['characters.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['scene_id'], ['scenes.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('scene_id', 'character_id')
    )
    with op.batch_alter_table('scene_characters', schema=None) as batch_op:
        batch_op.create_index('idx_scene_characters_character', ['character_id'], unique=False)

    op.create_index('idx_export_jobs_project_created', 'export_jobs', ['project_id', sa.text('created_at DESC')])
    op.create_index('idx_invitation_codes_created_at', 'invitation_codes', [sa.text('created_at DESC')])
    op.create_index('idx_redemption_codes_created_at', 'redemption_codes', [sa.text('created_at DESC')])
    op.create_index('idx_usage_logs_user_created', 'usage_logs', ['user_id', sa.text('created_at DESC')])
    op.create_index('idx_generation_jobs_project_created', 'generation_jobs', ['project_id', sa.text('created_at DESC')])
    # ### end Alembic commands ###


def upgrade() -> None:
    """Create the current schema, or take ownership of an unversioned SQLite database."""
    if not _tables():
        _create_schema()
    else:
        _upgrade_legacy_schema()


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('idx_generation_jobs_project_created', table_name='generation_jobs')
    op.drop_index('idx_usage_logs_user_created', table_name='usage_logs')
    op.drop_index('idx_redemption_codes_created_at', table_name='redemption_codes')
    op.drop_index('idx_invitation_codes_created_at', table_name='invitation_codes')
    op.drop_index('idx_export_jobs_project_created', table_name='export_jobs')
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('scene_characters', schema=None) as batch_op:
        batch_op.drop_index('idx_scene_characters_character')

    op.drop_table('scene_characters')
    with op.batch_alter_table('generation_jobs', schema=None) as batch_op:
        batch_op.drop_index('idx_generation_jobs_status_lease')
        batch_op.drop_index('idx_generation_jobs_idempotency', sqlite_where=sa.text('idempotency_key IS NOT NULL'))

    op.drop_table('generation_jobs')
    with op.batch_alter_table('chat_messages', schema=None) as batch_op:
        batch_op.drop_index('idx_chat_messages_session_id')

    op.drop_table('chat_messages')
    op.drop_table('user_official_config_defaults')
    with op.batch_alter_table('scenes', schema=None) as batch_op:
        batch_op.drop_index('idx_scenes_project_id')
        batch_op.drop_index('idx_scenes_episode_order')
        batch_op.drop_index('idx_scenes_deleted_at')

    op.drop_table('scenes')
    with op.batch_alter_table('chat_sessions', schema=None) as batch_op:
        batch_op.drop_index('idx_chat_sessions_user_id')
        batch_op.drop_index('idx_chat_sessions_deleted_at')

    op.drop_table('chat_sessions')
    with op.batch_alter_table('character_variants', schema=None) as batch_op:
        batch_op.drop_index('idx_character_variants_deleted_at')
        batch_op.drop_index('idx_character_variants_character')

    op.drop_table('character_variants')
    op.drop_table('usage_logs')
    with op.batch_alter_table('redemption_codes', schema=None) as batch_op:
        batch_op.drop_index('idx_redemption_codes_redeemed_by')

    op.drop_table('redemption_codes')
    with op.batch_alter_table('model_configs', schema=None) as batch_op:
        batch_op.drop_index('idx_model_configs_user_id')
        batch_op.drop_index('idx_model_configs_source_purpose')
        batch_op.drop_index('idx_model_configs_deleted_at')

    op.drop_table('model_configs')
    with op.batch_alter_table('invitation_codes', schema=None) as batch_op:
        batch_op.drop_index('idx_invitation_codes_used_by')

    op.drop_table('invitation_codes')
    with op.batch_alter_table('export_jobs', schema=None) as batch_op:
        batch_op.drop_index('idx_export_jobs_user_id')

    op.drop_table('export_jobs')
    with op.batch_alter_table('episodes', schema=None) as batch_op:
        batch_op.drop_index('idx_episodes_project_number', sqlite_where=sa.text('deleted_at IS NULL'))
        batch_op.drop_index('idx_episodes_deleted_at')

    op.drop_table('episodes')
    with op.batch_alter_table('characters', schema=None) as batch_op:
        batch_op.drop_index('idx_characters_project_id')
        batch_op.drop_index('idx_characters_deleted_at')

    op.drop_table('characters')
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index('idx_users_deleted_at')

    op.drop_table('users')
    with op.batch_alter_table('projects', schema=None) as batch_op:
        batch_op.drop_index('idx_projects_user_id')
        batch_op.drop_index('idx_projects_deleted_at')

    op.drop_table('projects')
    # ### end Alembic commands ###
