from __future__ import annotations

from pathlib import Path
import tempfile
from unittest.mock import patch

from app.core import database
from app.core.database import db, init_db, row
from app.services.chat_service import begin_chat_turn
from app.utils.common import now


def test_chat_balance_gate_runs_before_message_save() -> None:
    original_path = database.DB_PATH
    with tempfile.TemporaryDirectory() as directory:
        database.DB_PATH = Path(directory) / "chat-balance.db"
        try:
            init_db()
            stamp = now()
            with db() as conn:
                user_id = int(
                    conn.execute(
                        "INSERT INTO users (created_at, updated_at, username, password, role, is_disabled) VALUES (?, ?, 'chat-user', 'x', 'user', 0)",
                        (stamp, stamp),
                    ).lastrowid
                )
                conn.execute(
                    "INSERT INTO chat_sessions (id, created_at, updated_at, user_id, title) VALUES ('chat-1', ?, ?, ?, 'test')",
                    (stamp, stamp, user_id),
                )

            official = {"source": "official", "provider": "openai", "model": "gpt-test"}
            with patch("app.services.chat_service.chat_config", return_value=official):
                with db() as conn:
                    try:
                        begin_chat_turn(conn, "chat-1", user_id, "hello", [], None)
                        raise AssertionError("official chat must be blocked at zero balance")
                    except Exception as exc:
                        assert getattr(exc, "status_code", None) == 402
                    assert row(conn, "SELECT COUNT(*) AS total FROM chat_messages")["total"] == 0

            personal = {"source": "user", "provider": "openai", "model": "gpt-personal"}
            with patch("app.services.chat_service.chat_config", return_value=personal):
                with db() as conn:
                    _, message = begin_chat_turn(conn, "chat-1", user_id, "hello", [], None)
                    assert message["content"] == "hello"
                    assert row(conn, "SELECT COUNT(*) AS total FROM chat_messages")["total"] == 1
        finally:
            database.DB_PATH = original_path


if __name__ == "__main__":
    test_chat_balance_gate_runs_before_message_save()
