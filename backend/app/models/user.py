from __future__ import annotations

from sqlalchemy import Index, text
from sqlmodel import Field, SQLModel


class User(SQLModel, table=True):
    __tablename__ = "users"
    __table_args__ = (
        Index("idx_users_deleted_at", "deleted_at"),
        {"sqlite_autoincrement": True},
    )

    id: int | None = Field(default=None, primary_key=True)
    created_at: str | None = None
    updated_at: str | None = None
    deleted_at: str | None = None
    username: str = Field(unique=True)
    nickname: str | None = None
    password: str
    role: str | None = Field(default="user", sa_column_kwargs={"server_default": text("'user'")})
    is_disabled: bool | None = Field(default=False, sa_column_kwargs={"server_default": text("false")})
    balance_micros: int = Field(default=0, sa_column_kwargs={"server_default": text("0")})
    level: int = Field(default=1, sa_column_kwargs={"server_default": text("1")})
    user_group: str = Field(default="default", sa_column_kwargs={"server_default": text("'default'")})


class InvitationCode(SQLModel, table=True):
    __tablename__ = "invitation_codes"
    __table_args__ = (
        Index("idx_invitation_codes_created_at", text("created_at DESC")),
        Index("idx_invitation_codes_used_by", "used_by_user_id"),
        {"sqlite_autoincrement": True},
    )

    id: int | None = Field(default=None, primary_key=True)
    created_at: str
    expires_at: str
    code: str = Field(unique=True)
    used_at: str | None = None
    used_by_user_id: int | None = Field(default=None, foreign_key="users.id", ondelete="SET NULL")
    created_by_user_id: int | None = Field(default=None, foreign_key="users.id", ondelete="SET NULL")


class RedemptionCode(SQLModel, table=True):
    __tablename__ = "redemption_codes"
    __table_args__ = (
        Index("idx_redemption_codes_created_at", text("created_at DESC")),
        Index("idx_redemption_codes_redeemed_by", "redeemed_by_user_id"),
        {"sqlite_autoincrement": True},
    )

    id: int | None = Field(default=None, primary_key=True)
    created_at: str
    expires_at: str
    code: str = Field(unique=True)
    amount_micros: int
    redeemed_at: str | None = None
    redeemed_by_user_id: int | None = Field(default=None, foreign_key="users.id", ondelete="SET NULL")
    created_by_user_id: int | None = Field(default=None, foreign_key="users.id", ondelete="SET NULL")
