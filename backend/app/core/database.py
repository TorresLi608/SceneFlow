from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Any

import bcrypt

from app.core.config import DB_PATH, SUPER_ADMIN_PASSWORD
from app.utils.common import now


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
        conn.execute("PRAGMA foreign_keys = OFF")
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
                is_disabled numeric DEFAULT false,
                balance_micros integer NOT NULL DEFAULT 0,
                level integer NOT NULL DEFAULT 1,
                user_group text NOT NULL DEFAULT "default"
            );
            CREATE INDEX IF NOT EXISTS idx_users_deleted_at ON users(deleted_at);
            CREATE TABLE IF NOT EXISTS invitation_codes (
                id integer PRIMARY KEY AUTOINCREMENT,
                created_at datetime NOT NULL,
                expires_at datetime NOT NULL,
                code text NOT NULL UNIQUE,
                used_at datetime,
                used_by_user_id integer,
                created_by_user_id integer,
                FOREIGN KEY(used_by_user_id) REFERENCES users(id) ON DELETE SET NULL,
                FOREIGN KEY(created_by_user_id) REFERENCES users(id) ON DELETE SET NULL
            );
            CREATE INDEX IF NOT EXISTS idx_invitation_codes_created_at ON invitation_codes(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_invitation_codes_used_by ON invitation_codes(used_by_user_id);
            CREATE TABLE IF NOT EXISTS redemption_codes (
                id integer PRIMARY KEY AUTOINCREMENT,
                created_at datetime NOT NULL,
                expires_at datetime NOT NULL,
                code text NOT NULL UNIQUE,
                amount_micros integer NOT NULL,
                redeemed_at datetime,
                redeemed_by_user_id integer,
                created_by_user_id integer,
                FOREIGN KEY(redeemed_by_user_id) REFERENCES users(id) ON DELETE SET NULL,
                FOREIGN KEY(created_by_user_id) REFERENCES users(id) ON DELETE SET NULL
            );
            CREATE INDEX IF NOT EXISTS idx_redemption_codes_created_at ON redemption_codes(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_redemption_codes_redeemed_by ON redemption_codes(redeemed_by_user_id);
            CREATE TABLE IF NOT EXISTS model_configs (
                id integer PRIMARY KEY AUTOINCREMENT,
                created_at datetime,
                updated_at datetime,
                deleted_at datetime,
                user_id integer,
                source text NOT NULL DEFAULT "user" CHECK(source IN ("user", "official")),
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
                unit_name text DEFAULT "token",
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                CHECK((source="user" AND user_id IS NOT NULL) OR (source="official" AND user_id IS NULL))
            );
            CREATE INDEX IF NOT EXISTS idx_model_configs_user_id ON model_configs(user_id);
            CREATE INDEX IF NOT EXISTS idx_model_configs_source_purpose ON model_configs(source, purpose);
            CREATE INDEX IF NOT EXISTS idx_model_configs_deleted_at ON model_configs(deleted_at);
            CREATE TABLE IF NOT EXISTS user_official_config_defaults (
                user_id integer NOT NULL,
                purpose text NOT NULL,
                official_config_id integer NOT NULL,
                created_at datetime,
                updated_at datetime,
                PRIMARY KEY(user_id, purpose),
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY(official_config_id) REFERENCES model_configs(id) ON DELETE CASCADE
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
                FOREIGN KEY(config_id) REFERENCES model_configs(id) ON DELETE SET NULL,
                FOREIGN KEY(official_config_id) REFERENCES model_configs(id) ON DELETE SET NULL
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
        if "balance_micros" not in user_columns:
            conn.execute("ALTER TABLE users ADD COLUMN balance_micros integer NOT NULL DEFAULT 0")
        if "level" not in user_columns:
            conn.execute("ALTER TABLE users ADD COLUMN level integer NOT NULL DEFAULT 1")
        if "user_group" not in user_columns:
            conn.execute('ALTER TABLE users ADD COLUMN user_group text NOT NULL DEFAULT "default"')
        invitation_columns = {item["name"] for item in conn.execute("PRAGMA table_info(invitation_codes)").fetchall()}
        if "created_by_user_id" not in invitation_columns:
            conn.execute("ALTER TABLE invitation_codes ADD COLUMN created_by_user_id integer")
        redemption_columns = {item["name"] for item in conn.execute("PRAGMA table_info(redemption_codes)").fetchall()}
        if "created_by_user_id" not in redemption_columns:
            conn.execute("ALTER TABLE redemption_codes ADD COLUMN created_by_user_id integer")
        _migrate_legacy_model_configs(conn)
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


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return row(conn, "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)) is not None


def _ensure_legacy_config_columns(conn: sqlite3.Connection, table: str) -> None:
    columns = {item["name"] for item in conn.execute(f"PRAGMA table_info({table})").fetchall()}
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
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def _migrate_legacy_model_configs(conn: sqlite3.Connection) -> None:
    has_user_configs = _table_exists(conn, "user_configs")
    has_official_configs = _table_exists(conn, "official_model_configs")
    if not has_user_configs and not has_official_configs:
        return

    conn.execute("SAVEPOINT migrate_model_configs")
    try:
        if has_user_configs:
            _ensure_legacy_config_columns(conn, "user_configs")
        if has_official_configs:
            _ensure_legacy_config_columns(conn, "official_model_configs")

        user_ids: dict[int, int] = {}
        official_ids: dict[int, int] = {}
        columns = (
            "created_at", "updated_at", "deleted_at", "provider", "encrypted_key", "is_active", "is_enabled",
            "purpose", "model_name", "is_verified", "name", "description", "base_url", "pricing_multiplier",
            "input_price_per_million", "output_price_per_million", "cache_read_price_per_million",
            "cache_write_price_per_million", "unit_price", "unit_name",
        )
        if has_user_configs:
            for config in rows(conn, "SELECT * FROM user_configs ORDER BY id"):
                cur = conn.execute(
                    f"INSERT INTO model_configs (user_id, source, {', '.join(columns)}) VALUES (?, 'user', {', '.join('?' for _ in columns)})",
                    (config["user_id"], *(config[column] for column in columns)),
                )
                user_ids[int(config["id"])] = int(cur.lastrowid)
        if has_official_configs:
            for config in rows(conn, "SELECT * FROM official_model_configs ORDER BY id"):
                cur = conn.execute(
                    f"INSERT INTO model_configs (user_id, source, {', '.join(columns)}) VALUES (NULL, 'official', {', '.join('?' for _ in columns)})",
                    tuple(config[column] for column in columns),
                )
                official_ids[int(config["id"])] = int(cur.lastrowid)

        defaults = rows(conn, "SELECT * FROM user_official_config_defaults") if _table_exists(conn, "user_official_config_defaults") else []
        sessions = rows(conn, "SELECT * FROM chat_sessions") if _table_exists(conn, "chat_sessions") else []
        conn.execute("DROP TABLE IF EXISTS user_official_config_defaults")
        conn.execute(
            """CREATE TABLE user_official_config_defaults (
            user_id integer NOT NULL, purpose text NOT NULL, official_config_id integer NOT NULL,
            created_at datetime, updated_at datetime, PRIMARY KEY(user_id, purpose),
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(official_config_id) REFERENCES model_configs(id) ON DELETE CASCADE)"""
        )
        for item in defaults:
            mapped_id = official_ids.get(int(item["official_config_id"]))
            if mapped_id:
                conn.execute(
                    "INSERT INTO user_official_config_defaults VALUES (?, ?, ?, ?, ?)",
                    (item["user_id"], item["purpose"], mapped_id, item["created_at"], item["updated_at"]),
                )

        conn.execute("DROP TABLE IF EXISTS chat_sessions")
        conn.execute(
            """CREATE TABLE chat_sessions (
            id text PRIMARY KEY, created_at datetime, updated_at datetime, deleted_at datetime,
            user_id integer NOT NULL, title text NOT NULL, config_id integer, official_config_id integer,
            provider text, model_name text, context_summary text, context_summary_until datetime,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(config_id) REFERENCES model_configs(id) ON DELETE SET NULL,
            FOREIGN KEY(official_config_id) REFERENCES model_configs(id) ON DELETE SET NULL)"""
        )
        for item in sessions:
            keys = item.keys()
            conn.execute(
                "INSERT INTO chat_sessions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    item["id"], item["created_at"], item["updated_at"], item["deleted_at"], item["user_id"], item["title"],
                    user_ids.get(int(item["config_id"])) if item["config_id"] is not None else None,
                    official_ids.get(int(item["official_config_id"])) if "official_config_id" in keys and item["official_config_id"] is not None else None,
                    item["provider"], item["model_name"],
                    item["context_summary"] if "context_summary" in keys else None,
                    item["context_summary_until"] if "context_summary_until" in keys else None,
                ),
            )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_chat_sessions_user_id ON chat_sessions(user_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_chat_sessions_deleted_at ON chat_sessions(deleted_at)")

        for old_id, new_id in user_ids.items():
            conn.execute("UPDATE usage_logs SET config_id=? WHERE config_source='user' AND config_id=?", (new_id, old_id))
        for old_id, new_id in official_ids.items():
            conn.execute("UPDATE usage_logs SET config_id=? WHERE config_source='official' AND config_id=?", (new_id, old_id))
        conn.execute("DROP TABLE IF EXISTS user_configs")
        conn.execute("DROP TABLE IF EXISTS official_model_configs")
        conn.execute("RELEASE migrate_model_configs")
    except Exception:
        conn.execute("ROLLBACK TO migrate_model_configs")
        conn.execute("RELEASE migrate_model_configs")
        raise


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
