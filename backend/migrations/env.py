from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection
from sqlmodel import SQLModel

import app.models  # noqa: F401 -- register every SQLModel table for autogenerate
from app.core.database import engine


config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata
SQLITE_EXPRESSION_INDEXES = {
    "idx_export_jobs_project_created",
    "idx_generation_jobs_project_created",
    "idx_invitation_codes_created_at",
    "idx_redemption_codes_created_at",
    "idx_usage_logs_user_created",
}


def include_object(obj, _name, type_, _reflected, _compare_to):
    # SQLite reflects DESC indexes as plain columns, so Alembic would report a false diff.
    return type_ != "index" or obj.name not in SQLITE_EXPRESSION_INDEXES


def configure(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        render_as_batch=True,
        include_object=include_object,
    )


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def _foreign_keys(connection: Connection, enabled: bool) -> bool:
    """Read and set `PRAGMA foreign_keys` on the raw DBAPI connection. Returns the old value.

    Deliberately not `connection.exec_driver_sql`: that autobegins a SQLAlchemy transaction,
    and the migration run would then be nested inside a transaction Alembic does not own and
    never commits — every migration appears to run and nothing persists. Going through the
    driver cursor leaves transaction ownership alone. SQLite also ignores this pragma inside
    a transaction, which is the other reason it has to happen before anything else executes.
    """
    raw = connection.connection.dbapi_connection
    cursor = raw.cursor()
    try:
        previous = bool(cursor.execute("PRAGMA foreign_keys").fetchone()[0])
        cursor.execute(f"PRAGMA foreign_keys = {'ON' if enabled else 'OFF'}")
    finally:
        cursor.close()
    return previous


def _run(connection: Connection) -> None:
    """Run the migrations with SQLite foreign keys off, then restore the setting.

    `render_as_batch` recreates a table to alter it — new table, copy, drop old, rename. With
    `PRAGMA foreign_keys = ON` (which `app/core/database.py` sets on every connection) that
    drop **cascades into the referrers**: altering `model_configs` silently nulled
    `chat_sessions.config_id` and deleted every `user_official_config_defaults` row. Only a
    database that already held data at the revision could show it, which is why it hid in the
    unversioned-upgrade path rather than in a fresh install.

    Off is also the right setting for `345000649eb5`, which rebuilds the whole schema by
    renaming tables aside; enforcement mid-rebuild would reject valid intermediate states.
    Runtime keeps enforcement on — this is scoped to the migration connection.
    """
    previous = _foreign_keys(connection, False)
    try:
        configure(connection)
        with context.begin_transaction():
            context.run_migrations()
    finally:
        # A pooled connection outlives the upgrade; leaving it unenforced would quietly
        # disable foreign keys for whatever ran next on it.
        _foreign_keys(connection, previous)


def run_migrations_online() -> None:
    supplied = config.attributes.get("connection")
    if supplied is not None:
        _run(supplied)
        return

    with engine().connect() as connection:
        _run(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
