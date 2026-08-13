from __future__ import annotations

from typing import Any

import bcrypt
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, update
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.api.deps import current_user_id
from app.core.database import db
from app.models import RedemptionCode, UsageLog, User
from app.schemas.serializers import user_json
from app.utils.common import now


router = APIRouter(prefix="/api/users", tags=["users"])


def user_profile(session: Session, user_id: int) -> tuple[User, int, int] | None:
    return session.exec(
        select(User, func.count(UsageLog.id), func.coalesce(func.sum(UsageLog.cost_micros), 0))
        .join(UsageLog, UsageLog.user_id == User.id, isouter=True)
        .where(User.id == user_id, User.deleted_at.is_(None))
        .group_by(User.id)
    ).first()


def profile_json(profile: tuple[User, int, int]) -> dict[str, Any]:
    user, request_count, historical_cost_micros = profile
    return user_json(user, request_count=request_count, historical_cost_micros=historical_cost_micros)


@router.get("/me")
def get_me(user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    with db() as session:
        profile = user_profile(session, user_id)
        if not profile:
            raise HTTPException(401, "user not found")
        return {"user": profile_json(profile)}


@router.post("/redeem")
def redeem_code(payload: dict[str, Any], user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    code = str(payload.get("code") or "").strip().upper()
    if not 4 <= len(code) <= 64:
        raise HTTPException(400, "invalid redemption code")
    stamp = now()
    with db() as session:
        redemption = session.exec(select(RedemptionCode).where(RedemptionCode.code == code)).first()
        if not redemption:
            raise HTTPException(404, "redemption code not found")
        if redemption.redeemed_at:
            raise HTTPException(409, "redemption code already redeemed")
        if redemption.expires_at <= stamp:
            raise HTTPException(410, "redemption code expired")
        # Conditional so a code can only ever be credited once.
        redeemed = session.execute(
            update(RedemptionCode)
            .where(
                RedemptionCode.id == redemption.id,
                RedemptionCode.redeemed_at.is_(None),
                RedemptionCode.expires_at > stamp,
            )
            .values(redeemed_at=stamp, redeemed_by_user_id=user_id),
            execution_options={"synchronize_session": False},
        )
        if redeemed.rowcount != 1:
            raise HTTPException(409, "redemption code is no longer available")
        session.execute(
            update(User)
            .where(User.id == user_id)
            .values(balance_micros=User.balance_micros + redemption.amount_micros, updated_at=stamp),
            execution_options={"synchronize_session": "fetch"},
        )
        profile = user_profile(session, user_id)
        return {"amountMicros": str(redemption.amount_micros), "user": profile_json(profile)}


@router.patch("/me")
def update_me(payload: dict[str, Any], user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    if "username" in payload:
        username = str(payload["username"]).strip()
        if not 3 <= len(username) <= 64:
            raise HTTPException(400, "username length must be between 3 and 64")
        updates["username"] = username
    if "nickname" in payload:
        nickname = str(payload["nickname"]).strip()
        if len(nickname) > 64:
            raise HTTPException(400, "nickname must be at most 64 characters")
        updates["nickname"] = nickname or None
    if "password" in payload:
        current_password = str(payload.get("currentPassword", ""))
        password = str(payload["password"])
        if not 1 <= len(current_password) <= 128:
            raise HTTPException(400, "current password is invalid")
        if not 6 <= len(password) <= 128:
            raise HTTPException(400, "password length must be between 6 and 128")
        if len(password.encode()) > 72:
            raise HTTPException(400, "password must be at most 72 bytes")
    if not updates and "password" not in payload:
        raise HTTPException(400, "no fields to update")
    with db() as session:
        if "password" in payload:
            user = session.exec(select(User).where(User.id == user_id, User.deleted_at.is_(None))).first()
            try:
                password_matches = bool(user) and bcrypt.checkpw(current_password.encode(), user.password.encode())
            except ValueError:
                password_matches = False
            if not password_matches:
                raise HTTPException(400, "current password is incorrect")
            updates["password"] = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        try:
            session.execute(
                update(User).where(User.id == user_id, User.deleted_at.is_(None)).values(**updates, updated_at=now()),
                execution_options={"synchronize_session": "fetch"},
            )
        except IntegrityError as exc:
            raise HTTPException(409, "username already exists") from exc
        return {"user": profile_json(user_profile(session, user_id))}


@router.delete("/me", status_code=204)
def delete_me(user_id: int = Depends(current_user_id)) -> None:
    with db() as session:
        session.execute(
            update(User).where(User.id == user_id, User.deleted_at.is_(None)).values(deleted_at=now(), updated_at=now()),
            execution_options={"synchronize_session": False},
        )
