from __future__ import annotations

from sqlalchemy import Index, text
from sqlmodel import Field, SQLModel


class UsageLog(SQLModel, table=True):
    __tablename__ = "usage_logs"
    __table_args__ = (Index("idx_usage_logs_user_created", "user_id", text("created_at DESC")),)
    model_config = {"protected_namespaces": ()}

    id: str = Field(primary_key=True)
    created_at: str
    user_id: int = Field(foreign_key="users.id", ondelete="CASCADE")
    feature: str
    config_source: str
    config_id: int | None = None
    provider: str | None = None
    model_name: str | None = None
    duration_ms: int | None = Field(default=0, sa_column_kwargs={"server_default": text("0")})
    input_tokens: int | None = Field(default=0, sa_column_kwargs={"server_default": text("0")})
    output_tokens: int | None = Field(default=0, sa_column_kwargs={"server_default": text("0")})
    cache_read_tokens: int | None = Field(default=0, sa_column_kwargs={"server_default": text("0")})
    cache_write_tokens: int | None = Field(default=0, sa_column_kwargs={"server_default": text("0")})
    quantity: float | None = Field(default=0, sa_column_kwargs={"server_default": text("0")})
    cost_micros: int | None = Field(default=0, sa_column_kwargs={"server_default": text("0")})
    pricing_multiplier: float | None = Field(default=1, sa_column_kwargs={"server_default": text("1")})
    input_price_per_million: float | None = Field(default=0, sa_column_kwargs={"server_default": text("0")})
    output_price_per_million: float | None = Field(default=0, sa_column_kwargs={"server_default": text("0")})
    cache_read_price_per_million: float | None = Field(default=0, sa_column_kwargs={"server_default": text("0")})
    cache_write_price_per_million: float | None = Field(default=0, sa_column_kwargs={"server_default": text("0")})
    unit_price: float | None = Field(default=0, sa_column_kwargs={"server_default": text("0")})
    unit_name: str | None = Field(default="token", sa_column_kwargs={"server_default": text("'token'")})
    pricing_json: str | None = None
