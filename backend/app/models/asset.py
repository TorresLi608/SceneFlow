from __future__ import annotations

from sqlalchemy import Index, text
from sqlmodel import Field, SQLModel


class Asset(SQLModel, table=True):
    """A named project-owned media file available to prompts and merge jobs."""

    __tablename__ = "assets"
    __table_args__ = (
        Index("idx_assets_project_kind", "project_id", "kind"),
        Index("idx_assets_deleted_at", "deleted_at"),
    )

    id: str = Field(primary_key=True)
    created_at: str | None = None
    updated_at: str | None = None
    deleted_at: str | None = None
    project_id: str = Field(foreign_key="projects.id", ondelete="CASCADE")
    name: str = Field(max_length=120)
    description: str = Field(default="", sa_column_kwargs={"server_default": text("''")})
    kind: str = Field(max_length=16)
    media_type: str = Field(default="application/octet-stream")
    path: str
