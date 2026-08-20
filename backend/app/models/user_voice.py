from __future__ import annotations

from sqlalchemy import Index, text
from sqlmodel import Field, SQLModel


class UserVoice(SQLModel, table=True):
    """A Qwen voice-design result owned by one account."""

    __tablename__ = "user_voices"
    __table_args__ = (
        Index("idx_user_voices_user_id", "user_id"),
        Index("idx_user_voices_deleted_at", "deleted_at"),
    )

    id: str = Field(primary_key=True)
    created_at: str | None = None
    updated_at: str | None = None
    deleted_at: str | None = None
    user_id: int = Field(foreign_key="users.id", ondelete="CASCADE")
    voice_id: str
    target_model: str = Field(default="qwen3-tts-vd-2026-01-26")
    name: str = Field(default="", sa_column_kwargs={"server_default": text("''")})
    voice_prompt: str = Field(default="", sa_column_kwargs={"server_default": text("''")})
    preview_text: str = Field(default="", sa_column_kwargs={"server_default": text("''")})
    preview_audio_path: str | None = None
    is_saved: bool = Field(default=False, sa_column_kwargs={"server_default": text("false")})
