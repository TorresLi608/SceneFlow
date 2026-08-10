from __future__ import annotations

from sqlalchemy import CheckConstraint, Index, text
from sqlmodel import Field, SQLModel


class ModelConfig(SQLModel, table=True):
    __tablename__ = "model_configs"
    __table_args__ = (
        CheckConstraint("source IN ('user', 'official')"),
        CheckConstraint("(source='user' AND user_id IS NOT NULL) OR (source='official' AND user_id IS NULL)"),
        Index("idx_model_configs_user_id", "user_id"),
        Index("idx_model_configs_source_purpose", "source", "purpose"),
        Index("idx_model_configs_deleted_at", "deleted_at"),
        {"sqlite_autoincrement": True},
    )
    model_config = {"protected_namespaces": ()}

    id: int | None = Field(default=None, primary_key=True)
    created_at: str | None = None
    updated_at: str | None = None
    deleted_at: str | None = None
    user_id: int | None = Field(default=None, foreign_key="users.id", ondelete="CASCADE")
    source: str = Field(default="user", sa_column_kwargs={"server_default": text("'user'")})
    provider: str
    encrypted_key: str
    is_active: bool | None = Field(default=False, sa_column_kwargs={"server_default": text("false")})
    is_enabled: bool | None = Field(default=True, sa_column_kwargs={"server_default": text("true")})
    purpose: str | None = Field(default="script", sa_column_kwargs={"server_default": text("'script'")})
    model_name: str | None = None
    is_verified: bool | None = Field(default=False, sa_column_kwargs={"server_default": text("false")})
    name: str | None = None
    description: str | None = None
    base_url: str | None = None
    pricing_multiplier: float | None = Field(default=1, sa_column_kwargs={"server_default": text("1")})
    input_price_per_million: float | None = Field(default=0, sa_column_kwargs={"server_default": text("0")})
    output_price_per_million: float | None = Field(default=0, sa_column_kwargs={"server_default": text("0")})
    cache_read_price_per_million: float | None = Field(default=0, sa_column_kwargs={"server_default": text("0")})
    cache_write_price_per_million: float | None = Field(default=0, sa_column_kwargs={"server_default": text("0")})
    unit_price: float | None = Field(default=0, sa_column_kwargs={"server_default": text("0")})
    unit_name: str | None = Field(default="token", sa_column_kwargs={"server_default": text("'token'")})
    pricing_json: str | None = None


class UserOfficialConfigDefault(SQLModel, table=True):
    __tablename__ = "user_official_config_defaults"

    user_id: int = Field(primary_key=True, foreign_key="users.id", ondelete="CASCADE")
    purpose: str = Field(primary_key=True)
    official_config_id: int = Field(foreign_key="model_configs.id", ondelete="CASCADE")
    created_at: str | None = None
    updated_at: str | None = None
