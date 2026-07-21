from __future__ import annotations

import sqlite3

import bcrypt

from database import SUPER_ADMIN_USERNAME, seed_super_admin, row


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE users (
            id integer PRIMARY KEY AUTOINCREMENT,
            created_at datetime,
            updated_at datetime,
            deleted_at datetime,
            username text NOT NULL UNIQUE,
            password text NOT NULL,
            role text DEFAULT "user",
            is_disabled numeric DEFAULT false
        )
        """
    )
    return conn


def test_seed_super_admin_creates_missing_user() -> None:
    conn = _conn()
    seed_super_admin(conn)
    user = row(conn, "SELECT * FROM users WHERE username=?", (SUPER_ADMIN_USERNAME,))

    assert user is not None
    assert user["role"] == "superAdmin"
    assert not bool(user["is_disabled"])
    assert bcrypt.checkpw(b"superAdmin@123", user["password"].encode())


def test_seed_super_admin_keeps_existing_password() -> None:
    conn = _conn()
    password = bcrypt.hashpw(b"changed-password", bcrypt.gensalt()).decode()
    conn.execute(
        "INSERT INTO users (created_at, updated_at, deleted_at, username, password, role, is_disabled) VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("old", "old", "old", SUPER_ADMIN_USERNAME, password, "user", 1),
    )

    seed_super_admin(conn)
    user = row(conn, "SELECT * FROM users WHERE username=?", (SUPER_ADMIN_USERNAME,))

    assert user is not None
    assert user["password"] == password
    assert user["role"] == "superAdmin"
    assert not bool(user["is_disabled"])
    assert user["deleted_at"] is None


if __name__ == "__main__":
    test_seed_super_admin_creates_missing_user()
    test_seed_super_admin_keeps_existing_password()
