from __future__ import annotations

from fastapi import Depends, Header, HTTPException

from app.core.database import db, row
from app.core.security import user_id_from_token


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
    with db() as conn:
        user = row(conn, "SELECT * FROM users WHERE id=? AND deleted_at IS NULL", (user_id,))
    if not user:
        raise HTTPException(401, "user not found")
    if bool(user["is_disabled"]):
        raise HTTPException(403, "user is disabled")
    return user_id


def current_super_admin_id(user_id: int = Depends(current_user_id)) -> int:
    with db() as conn:
        user = row(conn, "SELECT role FROM users WHERE id=? AND deleted_at IS NULL", (user_id,))
    if not user or user["role"] != "superAdmin":
        raise HTTPException(403, "superAdmin required")
    return user_id
