"""Voices: what each character and the narrator sound like.

A video model given a merged reference track — every voice in the show introducing itself in
its own timbre — can keep speakers apart. That merged track is the point of this table; the
individual profiles exist so the user can audition and bind them one at a time.
"""

from __future__ import annotations

from sqlalchemy import Index, text
from sqlmodel import Field, SQLModel


class VoiceProfile(SQLModel, table=True):
    __tablename__ = "voice_profiles"
    __table_args__ = (
        Index("idx_voice_profiles_project_id", "project_id"),
        Index("idx_voice_profiles_deleted_at", "deleted_at"),
    )

    id: str = Field(primary_key=True)
    created_at: str | None = None
    updated_at: str | None = None
    deleted_at: str | None = None
    project_id: str = Field(foreign_key="projects.id", ondelete="CASCADE")
    name: str
    # Free-text note for the user ("沙哑，压低"), never sent to a provider.
    note: str = Field(default="", sa_column_kwargs={"server_default": text("''")})
    # A provider and a model, never credentials — those stay on the account's audio config,
    # which is why synthesis refuses a model from a provider the project is not set up for.
    voice_provider: str = Field(default="", sa_column_kwargs={"server_default": text("''")})
    voice_model: str = Field(default="", sa_column_kwargs={"server_default": text("''")})
    # The line this voice says in the merged reference track. Editable, because the wording
    # is what tells the video model when to use this voice.
    sample_text: str = Field(default="", sa_column_kwargs={"server_default": text("''")})
    # A path relative to PRIVATE_GENERATED_DIR, never a URL — signed links expire.
    audio_path: str | None = None
    order_num: int = Field(default=0, sa_column_kwargs={"server_default": text("0")})
