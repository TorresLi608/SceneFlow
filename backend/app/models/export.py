"""Merged delivery: several rendered shots joined into one file the user can export."""

from __future__ import annotations

from sqlalchemy import CheckConstraint, Index, text
from sqlmodel import Field, SQLModel


# Concatenating an unbounded selection would tie up the process and produce a file nobody
# can upload; this is the documented ceiling for a single export.
MAX_EXPORT_CLIPS = 60


class ExportJob(SQLModel, table=True):
    __tablename__ = "export_jobs"
    __table_args__ = (
        CheckConstraint("status IN ('queued', 'running', 'succeeded', 'failed', 'canceled')"),
        Index("idx_export_jobs_project_created", "project_id", text("created_at DESC")),
        Index("idx_export_jobs_user_id", "user_id"),
    )

    id: str = Field(primary_key=True)
    created_at: str
    updated_at: str
    started_at: str | None = None
    finished_at: str | None = None
    user_id: int = Field(foreign_key="users.id", ondelete="CASCADE")
    project_id: str = Field(foreign_key="projects.id", ondelete="CASCADE")
    # JSON array of scene ids, in output order. The user picks and orders the clips, so this
    # is the export, not a derived view of an episode.
    source_scene_ids: str = Field(default="[]", sa_column_kwargs={"server_default": text("'[]'")})
    # Human-facing label such as "第一集 1-6", kept so the history reads the way it was asked for.
    range_label: str = Field(default="", sa_column_kwargs={"server_default": text("''")})
    status: str = Field(default="queued", sa_column_kwargs={"server_default": text("'queued'")})
    progress: int = Field(default=0, sa_column_kwargs={"server_default": text("0")})
    output_path: str | None = None
    file_size: int = Field(default=0, sa_column_kwargs={"server_default": text("0")})
    include_subtitles: bool = Field(default=True, sa_column_kwargs={"server_default": text("1")})
    title_cards: bool = Field(default=False, sa_column_kwargs={"server_default": text("0")})
    transition: str = Field(default="none", sa_column_kwargs={"server_default": text("'none'")})
    error_message: str | None = None
