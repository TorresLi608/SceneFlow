from __future__ import annotations

from fastapi import Depends, Header, HTTPException
from sqlmodel import select

from app.core.database import db
from app.core.security import user_id_from_token
from app.models import User


def current_user_id(authorization: str | None = Header(default=None)) -> int:
    token = (authorization or "").strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    if not token:
        raise HTTPException(401, "missing token")
    try:
        user_id = user_id_from_token(token)
    except Exception as exc:
        raise HTTPException(401, "invalid token") from exc
    with db() as session:
        user = session.exec(select(User).where(User.id == user_id, User.deleted_at.is_(None))).first()
    if not user:
        raise HTTPException(401, "user not found")
    if bool(user.is_disabled):
        raise HTTPException(403, "user is disabled")
    return user_id


def current_super_admin_id(user_id: int = Depends(current_user_id)) -> int:
    with db() as session:
        user = session.exec(select(User).where(User.id == user_id, User.deleted_at.is_(None))).first()
    if not user or user.role != "superAdmin":
        raise HTTPException(403, "superAdmin required")
    return user_id
