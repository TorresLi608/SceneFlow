from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Any

from config import DB_PATH


@contextmanager
def db() -> Any:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id integer PRIMARY KEY AUTOINCREMENT,
                created_at datetime,
                updated_at datetime,
                deleted_at datetime,
                username text NOT NULL UNIQUE,
                password text NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_users_deleted_at ON users(deleted_at);
            CREATE TABLE IF NOT EXISTS user_configs (
                id integer PRIMARY KEY AUTOINCREMENT,
                created_at datetime,
                updated_at datetime,
                deleted_at datetime,
                user_id integer NOT NULL,
                provider text NOT NULL,
                encrypted_key text NOT NULL,
                is_active numeric DEFAULT false,
                purpose text DEFAULT "script",
                model_name text,
                is_verified numeric DEFAULT false,
                name text,
                description text,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_user_configs_user_id ON user_configs(user_id);
            CREATE INDEX IF NOT EXISTS idx_user_configs_purpose ON user_configs(purpose);
            CREATE INDEX IF NOT EXISTS idx_user_configs_deleted_at ON user_configs(deleted_at);
            CREATE TABLE IF NOT EXISTS projects (
                id text PRIMARY KEY,
                created_at datetime,
                updated_at datetime,
                deleted_at datetime,
                user_id integer NOT NULL,
                original_script text,
                status text DEFAULT "idle",
                video_url text,
                video_status text DEFAULT "idle"
            );
            CREATE INDEX IF NOT EXISTS idx_projects_user_id ON projects(user_id);
            CREATE INDEX IF NOT EXISTS idx_projects_deleted_at ON projects(deleted_at);
            CREATE TABLE IF NOT EXISTS scenes (
                id text PRIMARY KEY,
                created_at datetime,
                updated_at datetime,
                deleted_at datetime,
                project_id text NOT NULL,
                order_num integer,
                narration text,
                visual_prompt text,
                image_url text,
                image_status text DEFAULT "idle",
                audio_url text,
                audio_status text DEFAULT "idle",
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_scenes_project_id ON scenes(project_id);
            CREATE INDEX IF NOT EXISTS idx_scenes_deleted_at ON scenes(deleted_at);
            """
        )


def row(conn: sqlite3.Connection, sql: str, args: tuple[Any, ...] = ()) -> sqlite3.Row | None:
    return conn.execute(sql, args).fetchone()


def rows(conn: sqlite3.Connection, sql: str, args: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
    return list(conn.execute(sql, args).fetchall())
