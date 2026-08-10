from __future__ import annotations

from typing import Any

import bcrypt
from fastapi import APIRouter, HTTPException
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from app.core.database import db
from app.core.security import token_for
from app.models import InvitationCode, User
from app.schemas.serializers import user_json
from app.utils.common import now


router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", status_code=201)
def register(payload: dict[str, Any]) -> dict[str, Any]:
    username = str(payload.get("username", "")).strip()
    password = str(payload.get("password", ""))
    invitation_code = str(payload.get("invitationCode", "")).strip().upper()
    if not 3 <= len(username) <= 64 or not 6 <= len(password) <= 128:
        raise HTTPException(400, "invalid username or password length")
    if not invitation_code:
        raise HTTPException(400, "invitation code required")
    stamp = now()
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    with db() as session:
        invitation = session.exec(select(InvitationCode).where(InvitationCode.code == invitation_code)).first()
        if not invitation:
            raise HTTPException(400, "invalid invitation code")
        if invitation.used_at:
            raise HTTPException(409, "invitation code already used")
        if invitation.expires_at <= stamp:
            raise HTTPException(410, "invitation code expired")
        if session.exec(select(User.id).where(User.username == username, User.deleted_at.is_(None))).first():
            raise HTTPException(409, "username already exists")
        user = User(created_at=stamp, updated_at=stamp, username=username, password=hashed, role="user", is_disabled=False)
        session.add(user)
        try:
            session.flush()
        except IntegrityError as exc:
            raise HTTPException(409, "username already exists") from exc
        # Conditional so two concurrent registrations cannot both consume the same code.
        consumed = session.execute(
            update(InvitationCode)
            .where(InvitationCode.id == invitation.id, InvitationCode.used_at.is_(None), InvitationCode.expires_at > stamp)
            .values(used_at=stamp, used_by_user_id=user.id),
            execution_options={"synchronize_session": False},
        )
        if consumed.rowcount != 1:
            raise HTTPException(409, "invitation code is no longer available")
        return {"token": token_for(user.id), "user": user_json(user)}


@router.post("/login")
def login(payload: dict[str, Any]) -> dict[str, Any]:
    username = str(payload.get("username", "")).strip()
    password = str(payload.get("password", ""))
    with db() as session:
        user = session.exec(select(User).where(User.username == username, User.deleted_at.is_(None))).first()
    if not user or not bcrypt.checkpw(password.encode(), user.password.encode()):
        raise HTTPException(401, "invalid credentials")
    if bool(user.is_disabled):
        raise HTTPException(403, "user is disabled")
    return {"token": token_for(user.id), "user": user_json(user)}
