from __future__ import annotations

from sqlalchemy import Index, text
from sqlmodel import Field, SQLModel


class GenerationRecord(SQLModel, table=True):
    """One standalone image/video result owned by an account.

    The `/images` and `/videos` panels used to keep their "history" in localStorage, so it
    vanished with the browser profile and could not follow the user between devices. Rows
    keep the stored relative path, never a signed URL, so links can be re-minted after expiry.
    """

    __tablename__ = "generation_records"
    __table_args__ = (
        Index("idx_generation_records_user_kind", "user_id", "kind"),
        Index("idx_generation_records_deleted_at", "deleted_at"),
    )
    model_config = {"protected_namespaces": ()}

    id: str = Field(primary_key=True)
    created_at: str | None = None
    deleted_at: str | None = None
    user_id: int = Field(foreign_key="users.id", ondelete="CASCADE")
    kind: str = Field(max_length=16)
    path: str
    media_type: str = Field(default="application/octet-stream")
    prompt: str = Field(default="", sa_column_kwargs={"server_default": text("''")})
    provider: str = Field(default="", sa_column_kwargs={"server_default": text("''")})
    model_name: str = Field(default="", sa_column_kwargs={"server_default": text("''")})
    source: str = Field(default="", sa_column_kwargs={"server_default": text("''")})
    options_json: str = Field(default="{}", sa_column_kwargs={"server_default": text("'{}'")})
