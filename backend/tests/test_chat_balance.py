from __future__ import annotations

from pathlib import Path
import tempfile
from unittest.mock import patch

from sqlalchemy import func
from sqlmodel import select

from app.core import database
from app.core.database import db, init_db
from app.models import ChatMessage, ChatSession, User
from app.services.chat_service import begin_chat_turn
from app.utils.common import now


def test_chat_balance_gate_runs_before_message_save() -> None:
    original_path = database.DB_PATH
    with tempfile.TemporaryDirectory() as directory:
        database.DB_PATH = Path(directory) / "chat-balance.db"
        try:
            init_db()
            stamp = now()
            with db() as session:
                user = User(created_at=stamp, updated_at=stamp, username="chat-user", password="x", role="user", is_disabled=False)
                session.add(user)
                session.flush()
                user_id = user.id
                session.add(ChatSession(id="chat-1", created_at=stamp, updated_at=stamp, user_id=user_id, title="新对话"))

            official = {"source": "official", "provider": "openai", "model": "gpt-test"}
            with patch("app.services.chat_service.chat_config", return_value=official):
                with db() as session:
                    try:
                        begin_chat_turn(session, "chat-1", user_id, "hello", [], None)
                        raise AssertionError("official chat must be blocked at zero balance")
                    except Exception as exc:
                        assert getattr(exc, "status_code", None) == 402
                    assert session.exec(select(func.count()).select_from(ChatMessage)).one() == 0
                    assert session.exec(select(ChatSession.title).where(ChatSession.id == "chat-1")).first() == "新对话"

            personal = {"source": "user", "provider": "openai", "model": "gpt-personal"}
            with patch("app.services.chat_service.chat_config", return_value=personal):
                with db() as session:
                    _, message = begin_chat_turn(session, "chat-1", user_id, "  第一个问题\n是什么？  ", [], None)
                    assert message.content == "第一个问题\n是什么？"
                    assert session.exec(select(ChatSession.title).where(ChatSession.id == "chat-1")).first() == "第一个问题 是什么？"
                    begin_chat_turn(session, "chat-1", user_id, "第二个问题", [], None)
                    assert session.exec(select(func.count()).select_from(ChatMessage)).one() == 2
                    assert session.exec(select(ChatSession.title).where(ChatSession.id == "chat-1")).first() == "第一个问题 是什么？"
        finally:
            database.DB_PATH = original_path


if __name__ == "__main__":
    test_chat_balance_gate_runs_before_message_save()
