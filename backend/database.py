from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Any

import bcrypt

from config import DB_PATH, SUPER_ADMIN_PASSWORD
from utils import now


SUPER_ADMIN_USERNAME = "superAdmin"


@contextmanager
def db() -> Any:
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
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
                password text NOT NULL,
                role text DEFAULT "user",
                is_disabled numeric DEFAULT false
            );
            CREATE INDEX IF NOT EXISTS idx_users_deleted_at ON users(deleted_at);
            CREATE TABLE IF NOT EXISTS invitation_codes (
                id integer PRIMARY KEY AUTOINCREMENT,
                created_at datetime NOT NULL,
                expires_at datetime NOT NULL,
                code text NOT NULL UNIQUE,
                used_at datetime,
                used_by_user_id integer,
                FOREIGN KEY(used_by_user_id) REFERENCES users(id) ON DELETE SET NULL
            );
            CREATE INDEX IF NOT EXISTS idx_invitation_codes_created_at ON invitation_codes(created_at DESC);
            CREATE TABLE IF NOT EXISTS user_configs (
                id integer PRIMARY KEY AUTOINCREMENT,
                created_at datetime,
                updated_at datetime,
                deleted_at datetime,
                user_id integer NOT NULL,
                provider text NOT NULL,
                encrypted_key text NOT NULL,
                is_active numeric DEFAULT false,
                is_enabled numeric DEFAULT true,
                purpose text DEFAULT "script",
                model_name text,
                is_verified numeric DEFAULT false,
                name text,
                description text,
                base_url text,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_user_configs_user_id ON user_configs(user_id);
            CREATE INDEX IF NOT EXISTS idx_user_configs_purpose ON user_configs(purpose);
            CREATE INDEX IF NOT EXISTS idx_user_configs_deleted_at ON user_configs(deleted_at);
            CREATE TABLE IF NOT EXISTS official_model_configs (
                id integer PRIMARY KEY AUTOINCREMENT,
                created_at datetime,
                updated_at datetime,
                deleted_at datetime,
                provider text NOT NULL,
                encrypted_key text NOT NULL,
                is_active numeric DEFAULT false,
                is_enabled numeric DEFAULT true,
                purpose text DEFAULT "script",
                model_name text,
                is_verified numeric DEFAULT false,
                name text,
                description text,
                base_url text,
                pricing_multiplier real DEFAULT 1,
                input_price_per_million real DEFAULT 0,
                output_price_per_million real DEFAULT 0,
                cache_read_price_per_million real DEFAULT 0,
                cache_write_price_per_million real DEFAULT 0,
                unit_price real DEFAULT 0,
                unit_name text DEFAULT "token"
            );
            CREATE INDEX IF NOT EXISTS idx_official_model_configs_purpose ON official_model_configs(purpose);
            CREATE INDEX IF NOT EXISTS idx_official_model_configs_deleted_at ON official_model_configs(deleted_at);
            CREATE TABLE IF NOT EXISTS user_official_config_defaults (
                user_id integer NOT NULL,
                purpose text NOT NULL,
                official_config_id integer NOT NULL,
                created_at datetime,
                updated_at datetime,
                PRIMARY KEY(user_id, purpose),
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY(official_config_id) REFERENCES official_model_configs(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS projects (
                id text PRIMARY KEY,
                created_at datetime,
                updated_at datetime,
                deleted_at datetime,
                user_id integer NOT NULL,
                title text,
                original_script text,
                status text DEFAULT "idle",
                video_url text,
                video_status text DEFAULT "idle",
                video_progress integer DEFAULT 0
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
            CREATE TABLE IF NOT EXISTS chat_sessions (
                id text PRIMARY KEY,
                created_at datetime,
                updated_at datetime,
                deleted_at datetime,
                user_id integer NOT NULL,
                title text NOT NULL,
                config_id integer,
                official_config_id integer,
                provider text,
                model_name text,
                context_summary text,
                context_summary_until datetime,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY(config_id) REFERENCES user_configs(id) ON DELETE SET NULL,
                FOREIGN KEY(official_config_id) REFERENCES official_model_configs(id) ON DELETE SET NULL
            );
            CREATE INDEX IF NOT EXISTS idx_chat_sessions_user_id ON chat_sessions(user_id);
            CREATE INDEX IF NOT EXISTS idx_chat_sessions_deleted_at ON chat_sessions(deleted_at);
            CREATE TABLE IF NOT EXISTS chat_messages (
                id text PRIMARY KEY,
                created_at datetime,
                session_id text NOT NULL,
                role text NOT NULL,
                content text NOT NULL,
                attachments text,
                reasoning text,
                provider text,
                model_name text,
                FOREIGN KEY(session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_chat_messages_session_id ON chat_messages(session_id);
            CREATE TABLE IF NOT EXISTS usage_logs (
                id text PRIMARY KEY,
                created_at datetime NOT NULL,
                user_id integer NOT NULL,
                feature text NOT NULL,
                config_source text NOT NULL,
                config_id integer,
                provider text,
                model_name text,
                duration_ms integer DEFAULT 0,
                input_tokens integer DEFAULT 0,
                output_tokens integer DEFAULT 0,
                cache_read_tokens integer DEFAULT 0,
                cache_write_tokens integer DEFAULT 0,
                quantity real DEFAULT 0,
                cost_micros integer DEFAULT 0,
                pricing_multiplier real DEFAULT 1,
                input_price_per_million real DEFAULT 0,
                output_price_per_million real DEFAULT 0,
                cache_read_price_per_million real DEFAULT 0,
                cache_write_price_per_million real DEFAULT 0,
                unit_price real DEFAULT 0,
                unit_name text DEFAULT "token",
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_usage_logs_user_created ON usage_logs(user_id, created_at DESC);
            """
        )
        columns = {item["name"] for item in conn.execute("PRAGMA table_info(chat_messages)").fetchall()}
        if "reasoning" not in columns:
            conn.execute("ALTER TABLE chat_messages ADD COLUMN reasoning text")
        if "attachments" not in columns:
            conn.execute("ALTER TABLE chat_messages ADD COLUMN attachments text")
        user_columns = {item["name"] for item in conn.execute("PRAGMA table_info(users)").fetchall()}
        if "role" not in user_columns:
            conn.execute('ALTER TABLE users ADD COLUMN role text DEFAULT "user"')
        if "is_disabled" not in user_columns:
            conn.execute("ALTER TABLE users ADD COLUMN is_disabled numeric DEFAULT false")
        user_config_columns = {item["name"] for item in conn.execute("PRAGMA table_info(user_configs)").fetchall()}
        if "base_url" not in user_config_columns:
            conn.execute("ALTER TABLE user_configs ADD COLUMN base_url text")
        if "is_enabled" not in user_config_columns:
            conn.execute("ALTER TABLE user_configs ADD COLUMN is_enabled numeric DEFAULT true")
        official_config_columns = {item["name"] for item in conn.execute("PRAGMA table_info(official_model_configs)").fetchall()}
        if "base_url" not in official_config_columns:
            conn.execute("ALTER TABLE official_model_configs ADD COLUMN base_url text")
        if "is_enabled" not in official_config_columns:
            conn.execute("ALTER TABLE official_model_configs ADD COLUMN is_enabled numeric DEFAULT true")
        for name, definition in (
            ("pricing_multiplier", "real DEFAULT 1"),
            ("input_price_per_million", "real DEFAULT 0"),
            ("output_price_per_million", "real DEFAULT 0"),
            ("cache_read_price_per_million", "real DEFAULT 0"),
            ("cache_write_price_per_million", "real DEFAULT 0"),
            ("unit_price", "real DEFAULT 0"),
            ("unit_name", 'text DEFAULT "token"'),
        ):
            if name not in official_config_columns:
                conn.execute(f"ALTER TABLE official_model_configs ADD COLUMN {name} {definition}")
        session_columns = {item["name"] for item in conn.execute("PRAGMA table_info(chat_sessions)").fetchall()}
        if "official_config_id" not in session_columns:
            conn.execute("ALTER TABLE chat_sessions ADD COLUMN official_config_id integer")
        if "context_summary" not in session_columns:
            conn.execute("ALTER TABLE chat_sessions ADD COLUMN context_summary text")
        if "context_summary_until" not in session_columns:
            conn.execute("ALTER TABLE chat_sessions ADD COLUMN context_summary_until datetime")
        project_columns = {item["name"] for item in conn.execute("PRAGMA table_info(projects)").fetchall()}
        if "title" not in project_columns:
            conn.execute("ALTER TABLE projects ADD COLUMN title text")
        if "video_progress" not in project_columns:
            conn.execute("ALTER TABLE projects ADD COLUMN video_progress integer DEFAULT 0")
        seed_super_admin(conn)


def seed_super_admin(conn: sqlite3.Connection) -> None:
    stamp = now()
    user = row(conn, "SELECT * FROM users WHERE username=?", (SUPER_ADMIN_USERNAME,))
    if user:
        conn.execute(
            "UPDATE users SET role='superAdmin', is_disabled=0, deleted_at=NULL, updated_at=? WHERE id=?",
            (stamp, user["id"]),
        )
        return
    password = bcrypt.hashpw(SUPER_ADMIN_PASSWORD.encode(), bcrypt.gensalt()).decode()
    conn.execute(
        "INSERT INTO users (created_at, updated_at, username, password, role, is_disabled) VALUES (?, ?, ?, ?, 'superAdmin', 0)",
        (stamp, stamp, SUPER_ADMIN_USERNAME, password),
    )


def row(conn: sqlite3.Connection, sql: str, args: tuple[Any, ...] = ()) -> sqlite3.Row | None:
    return conn.execute(sql, args).fetchone()


def rows(conn: sqlite3.Connection, sql: str, args: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
    return list(conn.execute(sql, args).fetchall())
