from __future__ import annotations

from fastapi import Depends, Header, HTTPException, Request
from sqlmodel import select

from app.core.database import db
from app.core.security import user_id_from_token
from app.models import User


def bearer_token(authorization: str | None) -> str:
    """Extract the credential from an Authorization header.

    Prefix-strip rather than replace so a token whose body happens to contain "Bearer"
    survives intact.
    """
    header = (authorization or "").strip()
    return header[7:].strip() if header[:7].lower() == "bearer " else header


def current_user(request: Request, authorization: str | None = Header(default=None)) -> User:
    token = bearer_token(authorization)
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
    request.state.user_id = int(user.id)
    return user


def current_user_id(user: User = Depends(current_user)) -> int:
    return int(user.id)


def current_super_admin_id(user: User = Depends(current_user)) -> int:
    # Reuses the row `current_user` already loaded instead of querying the user a second time.
    if user.role != "superAdmin":
        raise HTTPException(403, "superAdmin required")
    return int(user.id)
