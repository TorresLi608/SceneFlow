from __future__ import annotations

import tempfile
from pathlib import Path

import bcrypt

import database
from database import db, init_db, row
from routers.admin import create_user, reset_user_password


def test_admin_create_and_reset_user() -> None:
    original_path = database.DB_PATH
    with tempfile.TemporaryDirectory() as directory:
        database.DB_PATH = Path(directory) / "test.db"
        try:
            init_db()
            created = create_user({"username": "alice", "password": "initial-password"}, 1)["user"]
            assert created["role"] == "user"

            reset = reset_user_password(created["id"], 1)["password"]
            assert len(reset) >= 6
            with db() as conn:
                saved = row(conn, "SELECT * FROM users WHERE id=?", (created["id"],))
            assert bcrypt.checkpw(reset.encode(), saved["password"].encode())
            assert not bcrypt.checkpw(b"initial-password", saved["password"].encode())
        finally:
            database.DB_PATH = original_path


if __name__ == "__main__":
    test_admin_create_and_reset_user()
