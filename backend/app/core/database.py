from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import bcrypt
from sqlalchemy import Connection, Engine, event
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import app.models  # noqa: F401  -- import for the side effect of registering every table on SQLModel.metadata
from app.core.config import DB_PATH, SUPER_ADMIN_PASSWORD
from app.models import User
from app.utils.common import new_id, now


SUPER_ADMIN_USERNAME = "superAdmin"

_engines: dict[str, Engine] = {}


def _apply_pragmas(dbapi_connection: Any, _record: Any) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys = ON")
    cursor.execute("PRAGMA busy_timeout = 30000")
    cursor.close()


def _build_engine(path: str) -> Engine:
    if path == ":memory:":
        # A pooled in-memory database would hand out a different empty database per connection.
        built = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    else:
        built = create_engine(f"sqlite:///{path}", connect_args={"timeout": 30, "check_same_thread": False})
    event.listen(built, "connect", _apply_pragmas)
    return built


def engine() -> Engine:
    # Built lazily and cached per path because DB_PATH is rebound at runtime (tests point it at a temp file).
    path = str(DB_PATH)
    if path not in _engines:
        _engines[path] = _build_engine(path)
    return _engines[path]


@contextmanager
def db() -> Iterator[Session]:
    # expire_on_commit=False keeps loaded instances readable after the block exits, matching the
    # snapshot semantics callers relied on when this yielded sqlite3.Row values.
    session = Session(engine(), expire_on_commit=False)
    try:
        yield session
        session.commit()
    finally:
        session.close()


def _columns(connection: Connection, table: str) -> set[str]:
    return {item[1] for item in connection.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()}


def _table_exists(connection: Connection, name: str) -> bool:
    return connection.exec_driver_sql("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).first() is not None


def _legacy_rows(connection: Connection, sql: str, args: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return [dict(item._mapping) for item in connection.exec_driver_sql(sql, args).fetchall()]


def init_db() -> None:
    with engine().connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys = OFF")
        SQLModel.metadata.create_all(connection)
        _add_missing_columns(connection)
        _migrate_legacy_model_configs(connection)
        connection.exec_driver_sql("DROP INDEX IF EXISTS idx_generation_jobs_idempotency")
        connection.exec_driver_sql(
            "CREATE UNIQUE INDEX idx_generation_jobs_idempotency ON generation_jobs(user_id, project_id, idempotency_key) WHERE idempotency_key IS NOT NULL"
        )
        connection.commit()
    with db() as session:
        seed_super_admin(session)
    path = Path(str(DB_PATH))
    if str(DB_PATH) != ":memory:" and path.is_file():
        path.chmod(0o600)


def _add_missing_columns(connection: Connection) -> None:
    """Bring databases created by older releases up to the current schema."""
    message_columns = _columns(connection, "chat_messages")
    if "reasoning" not in message_columns:
        connection.exec_driver_sql("ALTER TABLE chat_messages ADD COLUMN reasoning text")
    if "attachments" not in message_columns:
        connection.exec_driver_sql("ALTER TABLE chat_messages ADD COLUMN attachments text")
    user_columns = _columns(connection, "users")
    if "role" not in user_columns:
        connection.exec_driver_sql('ALTER TABLE users ADD COLUMN role text DEFAULT "user"')
    if "is_disabled" not in user_columns:
        connection.exec_driver_sql("ALTER TABLE users ADD COLUMN is_disabled numeric DEFAULT false")
    if "balance_micros" not in user_columns:
        connection.exec_driver_sql("ALTER TABLE users ADD COLUMN balance_micros integer NOT NULL DEFAULT 0")
    if "level" not in user_columns:
        connection.exec_driver_sql("ALTER TABLE users ADD COLUMN level integer NOT NULL DEFAULT 1")
    if "user_group" not in user_columns:
        connection.exec_driver_sql('ALTER TABLE users ADD COLUMN user_group text NOT NULL DEFAULT "default"')
    if "created_by_user_id" not in _columns(connection, "invitation_codes"):
        connection.exec_driver_sql("ALTER TABLE invitation_codes ADD COLUMN created_by_user_id integer")
    if "created_by_user_id" not in _columns(connection, "redemption_codes"):
        connection.exec_driver_sql("ALTER TABLE redemption_codes ADD COLUMN created_by_user_id integer")
    if "pricing_json" not in _columns(connection, "model_configs"):
        connection.exec_driver_sql("ALTER TABLE model_configs ADD COLUMN pricing_json text")
    if "pricing_json" not in _columns(connection, "usage_logs"):
        connection.exec_driver_sql("ALTER TABLE usage_logs ADD COLUMN pricing_json text")
    session_columns = _columns(connection, "chat_sessions")
    if "official_config_id" not in session_columns:
        connection.exec_driver_sql("ALTER TABLE chat_sessions ADD COLUMN official_config_id integer")
    if "context_summary" not in session_columns:
        connection.exec_driver_sql("ALTER TABLE chat_sessions ADD COLUMN context_summary text")
    if "context_summary_until" not in session_columns:
        connection.exec_driver_sql("ALTER TABLE chat_sessions ADD COLUMN context_summary_until datetime")
    project_columns = _columns(connection, "projects")
    if "title" not in project_columns:
        connection.exec_driver_sql("ALTER TABLE projects ADD COLUMN title text")
    if "video_progress" not in project_columns:
        connection.exec_driver_sql("ALTER TABLE projects ADD COLUMN video_progress integer DEFAULT 0")
    for name, definition in (
        ("mode", 'text NOT NULL DEFAULT "comic"'),
        ("aspect_ratio", 'text NOT NULL DEFAULT "9:16"'),
        ("width", "integer NOT NULL DEFAULT 1080"),
        ("height", "integer NOT NULL DEFAULT 1920"),
        ("fps", "integer NOT NULL DEFAULT 24"),
        ("target_duration_ms", "integer NOT NULL DEFAULT 60000"),
        ("language", 'text NOT NULL DEFAULT "zh-CN"'),
        ("style_prompt", 'text NOT NULL DEFAULT ""'),
        ("negative_prompt", 'text NOT NULL DEFAULT ""'),
        ("current_stage", 'text NOT NULL DEFAULT "script"'),
    ):
        if name not in project_columns:
            connection.exec_driver_sql(f"ALTER TABLE projects ADD COLUMN {name} {definition}")
    if "audio_duration" not in _columns(connection, "scenes"):
        connection.exec_driver_sql("ALTER TABLE scenes ADD COLUMN audio_duration real NOT NULL DEFAULT 0")
    _migrate_scene_assets(connection)
    _add_episode_columns(connection)
    _backfill_first_episode(connection)


def _add_episode_columns(connection: Connection) -> None:
    """Add the storyboard and series columns introduced with multi-episode projects."""
    if "series_bible" not in _columns(connection, "projects"):
        connection.exec_driver_sql("ALTER TABLE projects ADD COLUMN series_bible text NOT NULL DEFAULT ''")
    scene_columns = _columns(connection, "scenes")
    for name, definition in (
        ("episode_id", "text REFERENCES episodes(id) ON DELETE CASCADE"),
        ("dialogue", "text NOT NULL DEFAULT ''"),
        ("speaker_character_id", "text"),
        ("shot_type", "text NOT NULL DEFAULT ''"),
        ("camera_move", "text NOT NULL DEFAULT ''"),
        ("duration_ms", "integer NOT NULL DEFAULT 0"),
        ("subtitle_text", "text NOT NULL DEFAULT ''"),
        ("video_path", "text"),
        ("video_status", "text NOT NULL DEFAULT 'idle'"),
        ("is_locked", "numeric NOT NULL DEFAULT 0"),
    ):
        if name not in scene_columns:
            connection.exec_driver_sql(f"ALTER TABLE scenes ADD COLUMN {name} {definition}")
    if "episode_id" not in _columns(connection, "generation_jobs"):
        connection.exec_driver_sql(
            "ALTER TABLE generation_jobs ADD COLUMN episode_id text REFERENCES episodes(id) ON DELETE CASCADE"
        )


def _backfill_first_episode(connection: Connection) -> None:
    """Give every pre-existing project an episode 1 that owns its current shots.

    Projects predate the episode layer, so their scenes hang directly off the project. One
    episode per project keeps that work reachable in the new UI instead of orphaning it.
    """
    orphans = _legacy_rows(
        connection,
        """SELECT p.id, p.title, p.original_script, p.created_at, p.updated_at
           FROM projects p
           WHERE p.deleted_at IS NULL
             AND NOT EXISTS (SELECT 1 FROM episodes e WHERE e.project_id = p.id AND e.deleted_at IS NULL)""",
    )
    for project in orphans:
        episode_id = new_id("ep")
        stamp = project["updated_at"] or project["created_at"] or now()
        has_scenes = connection.exec_driver_sql(
            "SELECT 1 FROM scenes WHERE project_id=? AND deleted_at IS NULL LIMIT 1", (project["id"],)
        ).first()
        connection.exec_driver_sql(
            """INSERT INTO episodes (id, created_at, updated_at, project_id, episode_number, title,
               synopsis, source_text, status, video_status, video_progress, duration_ms)
               VALUES (?, ?, ?, ?, 1, ?, '', ?, ?, 'idle', 0, 0)""",
            (
                episode_id,
                project["created_at"] or stamp,
                stamp,
                project["id"],
                "第 1 集",
                project["original_script"] or "",
                "storyboard" if has_scenes else "draft",
            ),
        )
        connection.exec_driver_sql(
            "UPDATE scenes SET episode_id=? WHERE project_id=? AND episode_id IS NULL",
            (episode_id, project["id"]),
        )

    # Shots written before their project had an episode: a build that predates the episode
    # layer, or a project created between two startups. They belong to the earliest episode,
    # which is the one already holding that project's original storyboard.
    connection.exec_driver_sql(
        """UPDATE scenes SET episode_id = (
               SELECT e.id FROM episodes e
               WHERE e.project_id = scenes.project_id AND e.deleted_at IS NULL
               ORDER BY e.episode_number ASC LIMIT 1
           )
           WHERE episode_id IS NULL
             AND deleted_at IS NULL
             AND EXISTS (
               SELECT 1 FROM episodes e WHERE e.project_id = scenes.project_id AND e.deleted_at IS NULL
             )"""
    )


def _migrate_scene_assets(connection: Connection) -> None:
    """Move scene assets off stored signed URLs and onto stable relative paths.

    Signed links expire after 30 days, so a URL written into a row turned every image and
    voice track in an older project into a 404. The column now holds the artifact path and
    the serializer signs a fresh link per response. Links whose token no longer decodes were
    already dead, so the reference is dropped instead of kept as a broken string.
    """
    # Imported here rather than at module scope: core must not depend on services, and this
    # one-shot startup path is the only place that needs to read a legacy signed link.
    from app.services.artifact_service import stored_relative_path

    columns = _columns(connection, "scenes")
    for old_name, new_name in (("image_url", "image_path"), ("audio_url", "audio_path")):
        if new_name in columns:
            continue
        if old_name in columns:
            connection.exec_driver_sql(f"ALTER TABLE scenes RENAME COLUMN {old_name} TO {new_name}")
        else:
            connection.exec_driver_sql(f"ALTER TABLE scenes ADD COLUMN {new_name} text")
    if "error_message" not in _columns(connection, "scenes"):
        connection.exec_driver_sql("ALTER TABLE scenes ADD COLUMN error_message text")

    rows = _legacy_rows(
        connection,
        "SELECT id, image_path, audio_path FROM scenes WHERE image_path LIKE 'http%' OR audio_path LIKE 'http%'",
    )
    for row in rows:
        values = {}
        for column in ("image_path", "audio_path"):
            value = str(row[column] or "")
            if not value.startswith("http"):
                continue
            try:
                values[column] = stored_relative_path(value)
            except Exception:
                values[column] = None
        if values:
            assignments = ", ".join(f"{column}=?" for column in values)
            connection.exec_driver_sql(
                f"UPDATE scenes SET {assignments} WHERE id=?",
                (*values.values(), row["id"]),
            )


def _ensure_legacy_config_columns(connection: Connection, table: str) -> None:
    columns = _columns(connection, table)
    for name, definition in (
        ("base_url", "text"),
        ("is_enabled", "numeric DEFAULT true"),
        ("pricing_multiplier", "real DEFAULT 1"),
        ("input_price_per_million", "real DEFAULT 0"),
        ("output_price_per_million", "real DEFAULT 0"),
        ("cache_read_price_per_million", "real DEFAULT 0"),
        ("cache_write_price_per_million", "real DEFAULT 0"),
        ("unit_price", "real DEFAULT 0"),
        ("unit_name", 'text DEFAULT "token"'),
    ):
        if name not in columns:
            connection.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def _migrate_legacy_model_configs(connection: Connection) -> None:
    """Fold the retired user_configs/official_model_configs tables into model_configs."""
    has_user_configs = _table_exists(connection, "user_configs")
    has_official_configs = _table_exists(connection, "official_model_configs")
    if not has_user_configs and not has_official_configs:
        return

    connection.exec_driver_sql("SAVEPOINT migrate_model_configs")
    try:
        if has_user_configs:
            _ensure_legacy_config_columns(connection, "user_configs")
        if has_official_configs:
            _ensure_legacy_config_columns(connection, "official_model_configs")

        user_ids: dict[int, int] = {}
        official_ids: dict[int, int] = {}
        columns = (
            "created_at", "updated_at", "deleted_at", "provider", "encrypted_key", "is_active", "is_enabled",
            "purpose", "model_name", "is_verified", "name", "description", "base_url", "pricing_multiplier",
            "input_price_per_million", "output_price_per_million", "cache_read_price_per_million",
            "cache_write_price_per_million", "unit_price", "unit_name",
        )
        if has_user_configs:
            for config in _legacy_rows(connection, "SELECT * FROM user_configs ORDER BY id"):
                cur = connection.exec_driver_sql(
                    f"INSERT INTO model_configs (user_id, source, {', '.join(columns)}) VALUES (?, 'user', {', '.join('?' for _ in columns)})",
                    (config["user_id"], *(config[column] for column in columns)),
                )
                user_ids[int(config["id"])] = int(cur.lastrowid)
        if has_official_configs:
            for config in _legacy_rows(connection, "SELECT * FROM official_model_configs ORDER BY id"):
                cur = connection.exec_driver_sql(
                    f"INSERT INTO model_configs (user_id, source, {', '.join(columns)}) VALUES (NULL, 'official', {', '.join('?' for _ in columns)})",
                    tuple(config[column] for column in columns),
                )
                official_ids[int(config["id"])] = int(cur.lastrowid)

        defaults = _legacy_rows(connection, "SELECT * FROM user_official_config_defaults") if _table_exists(connection, "user_official_config_defaults") else []
        sessions = _legacy_rows(connection, "SELECT * FROM chat_sessions") if _table_exists(connection, "chat_sessions") else []
        connection.exec_driver_sql("DROP TABLE IF EXISTS user_official_config_defaults")
        connection.exec_driver_sql(
            """CREATE TABLE user_official_config_defaults (
            user_id integer NOT NULL, purpose text NOT NULL, official_config_id integer NOT NULL,
            created_at datetime, updated_at datetime, PRIMARY KEY(user_id, purpose),
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(official_config_id) REFERENCES model_configs(id) ON DELETE CASCADE)"""
        )
        for item in defaults:
            mapped_id = official_ids.get(int(item["official_config_id"]))
            if mapped_id:
                connection.exec_driver_sql(
                    "INSERT INTO user_official_config_defaults VALUES (?, ?, ?, ?, ?)",
                    (item["user_id"], item["purpose"], mapped_id, item["created_at"], item["updated_at"]),
                )

        connection.exec_driver_sql("DROP TABLE IF EXISTS chat_sessions")
        connection.exec_driver_sql(
            """CREATE TABLE chat_sessions (
            id text PRIMARY KEY, created_at datetime, updated_at datetime, deleted_at datetime,
            user_id integer NOT NULL, title text NOT NULL, config_id integer, official_config_id integer,
            provider text, model_name text, context_summary text, context_summary_until datetime,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(config_id) REFERENCES model_configs(id) ON DELETE SET NULL,
            FOREIGN KEY(official_config_id) REFERENCES model_configs(id) ON DELETE SET NULL)"""
        )
        for item in sessions:
            connection.exec_driver_sql(
                "INSERT INTO chat_sessions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    item["id"], item["created_at"], item["updated_at"], item["deleted_at"], item["user_id"], item["title"],
                    user_ids.get(int(item["config_id"])) if item["config_id"] is not None else None,
                    official_ids.get(int(item["official_config_id"])) if item.get("official_config_id") is not None else None,
                    item["provider"], item["model_name"],
                    item.get("context_summary"),
                    item.get("context_summary_until"),
                ),
            )
        connection.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_chat_sessions_user_id ON chat_sessions(user_id)")
        connection.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_chat_sessions_deleted_at ON chat_sessions(deleted_at)")

        for old_id, new_id in user_ids.items():
            connection.exec_driver_sql("UPDATE usage_logs SET config_id=? WHERE config_source='user' AND config_id=?", (new_id, old_id))
        for old_id, new_id in official_ids.items():
            connection.exec_driver_sql("UPDATE usage_logs SET config_id=? WHERE config_source='official' AND config_id=?", (new_id, old_id))
        connection.exec_driver_sql("DROP TABLE IF EXISTS user_configs")
        connection.exec_driver_sql("DROP TABLE IF EXISTS official_model_configs")
        connection.exec_driver_sql("RELEASE migrate_model_configs")
    except Exception:
        connection.exec_driver_sql("ROLLBACK TO migrate_model_configs")
        connection.exec_driver_sql("RELEASE migrate_model_configs")
        raise


def seed_super_admin(session: Session) -> None:
    stamp = now()
    user = session.exec(select(User).where(User.username == SUPER_ADMIN_USERNAME)).first()
    if user:
        user.role = "superAdmin"
        user.is_disabled = False
        user.deleted_at = None
        user.updated_at = stamp
        session.add(user)
        return
    password = bcrypt.hashpw(SUPER_ADMIN_PASSWORD.encode(), bcrypt.gensalt()).decode()
    session.add(
        User(
            created_at=stamp,
            updated_at=stamp,
            username=SUPER_ADMIN_USERNAME,
            password=password,
            role="superAdmin",
            is_disabled=False,
        )
    )
