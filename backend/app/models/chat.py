from __future__ import annotations

from sqlalchemy import Index
from sqlmodel import Field, SQLModel


class ChatSession(SQLModel, table=True):
    __tablename__ = "chat_sessions"
    __table_args__ = (
        Index("idx_chat_sessions_user_id", "user_id"),
        Index("idx_chat_sessions_deleted_at", "deleted_at"),
    )
    model_config = {"protected_namespaces": ()}

    id: str = Field(primary_key=True)
    created_at: str | None = None
    updated_at: str | None = None
    deleted_at: str | None = None
    user_id: int = Field(foreign_key="users.id", ondelete="CASCADE")
    title: str
    config_id: int | None = Field(default=None, foreign_key="model_configs.id", ondelete="SET NULL")
    official_config_id: int | None = Field(default=None, foreign_key="model_configs.id", ondelete="SET NULL")
    provider: str | None = None
    model_name: str | None = None
    context_summary: str | None = None
    context_summary_until: str | None = None


class ChatMessage(SQLModel, table=True):
    __tablename__ = "chat_messages"
    __table_args__ = (Index("idx_chat_messages_session_id", "session_id"),)
    model_config = {"protected_namespaces": ()}

    id: str = Field(primary_key=True)
    created_at: str | None = None
    session_id: str = Field(foreign_key="chat_sessions.id", ondelete="CASCADE")
    role: str
    content: str
    attachments: str | None = None
    reasoning: str | None = None
    provider: str | None = None
    model_name: str | None = None
