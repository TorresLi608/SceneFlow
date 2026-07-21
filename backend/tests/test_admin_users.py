from __future__ import annotations

import tempfile
from pathlib import Path

import bcrypt

from app.api.v1.admin import create_user, reset_user_password, update_user
from app.core import database
from app.core.database import db, init_db, row


def test_admin_create_and_reset_user() -> None:
    original_path = database.DB_PATH
    with tempfile.TemporaryDirectory() as directory:
        database.DB_PATH = Path(directory) / "test.db"
        try:
            init_db()
            created = create_user({"username": "alice", "password": "initial-password"}, 1)["user"]
            assert created["role"] == "user"
            assert created["level"] == 1
            super_admin = create_user({"username": "admin-two", "password": "initial-password", "role": "superAdmin"}, 1)["user"]
            assert super_admin["role"] == "superAdmin"
            updated = update_user(created["id"], {"level": 3}, 1)["user"]
            assert updated["level"] == 3

            try:
                create_user({"username": "invalid-level", "password": "password", "level": 0}, 1)
                raise AssertionError("level 0 must be rejected")
            except Exception as exc:
                assert getattr(exc, "status_code", None) == 400

            try:
                create_user({"username": "invalid-role", "password": "password", "role": "owner"}, 1)
                raise AssertionError("unknown roles must be rejected")
            except Exception as exc:
                assert getattr(exc, "status_code", None) == 400

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
