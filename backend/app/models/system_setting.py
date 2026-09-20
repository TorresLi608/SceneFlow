from __future__ import annotations

from sqlmodel import Field, SQLModel


# Upper bound for every retention window the admin center accepts, in whole days.
GENERATION_RETENTION_MAX_DAYS = 3650


class SystemSetting(SQLModel, table=True):
    """A super-admin controlled key/value setting that must survive restarts.

    Environment variables cover deployment shape; these cover policy an operator changes
    from the admin center at runtime, such as how long each standalone menu keeps its
    generated results.
    """

    __tablename__ = "system_settings"

    key: str = Field(primary_key=True, max_length=64)
    value: str = Field(default="")
    updated_at: str | None = None
    updated_by_user_id: int | None = Field(default=None, foreign_key="users.id", ondelete="SET NULL")
