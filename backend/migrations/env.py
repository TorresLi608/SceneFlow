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


def run_migrations_online() -> None:
    supplied = config.attributes.get("connection")
    if supplied is not None:
        configure(supplied)
        with context.begin_transaction():
            context.run_migrations()
        return

    with engine().connect() as connection:
        configure(connection)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
