from __future__ import annotations

from sqlalchemy import Index
from sqlmodel import Field, SQLModel


class ErrorLog(SQLModel, table=True):
    """A redacted, searchable record of a failed API request."""

    __tablename__ = "error_logs"
    __table_args__ = (
        Index("idx_error_logs_created", "created_at"),
        Index("idx_error_logs_code_created", "error_code", "created_at"),
        Index("idx_error_logs_project_created", "project_id", "created_at"),
        Index("idx_error_logs_request_id", "request_id", unique=True),
    )

    id: str = Field(primary_key=True)
    created_at: str
    request_id: str
    method: str
    route: str
    status_code: int
    error_code: str
    message: str
    user_id: int | None = Field(default=None, foreign_key="users.id", ondelete="SET NULL")
    project_id: str | None = None
    episode_id: str | None = None
