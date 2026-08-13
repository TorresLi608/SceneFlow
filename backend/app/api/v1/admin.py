from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Annotated, Any

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, func, or_, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import aliased
from sqlmodel import Session, select

from app.core.database import db
from app.api.deps import current_super_admin_id
from app.models import ChatSession, InvitationCode, ModelConfig, RedemptionCode, UsageLog, User, UserOfficialConfigDefault
from app.schemas.serializers import config_json, official_config_json, user_json
from app.services.config_service import config_api_key, config_create_fields, config_update_fields, normalize_config_payload, validate_api_key
from app.services.usage_service import normalize_pricing, pricing_snapshot, pricing_updates, usage_log_json
from app.utils.common import now


router = APIRouter(prefix="/api/admin", tags=["admin"])


def editable_user(session: Session, target_user_id: int, admin_id: int) -> User:
    user = session.exec(select(User).where(User.id == target_user_id, User.deleted_at.is_(None))).first()
    if not user:
        raise HTTPException(404, "user not found")
    if target_user_id == admin_id or user.role == "superAdmin":
        raise HTTPException(400, "cannot modify superAdmin")
    return user


def invitation_code_json(
    invitation: InvitationCode,
    used_by_username: str | None = None,
    created_by_username: str | None = None,
    stamp: str | None = None,
) -> dict[str, Any]:
    status = "used" if invitation.used_at else "expired" if invitation.expires_at <= (stamp or now()) else "unused"
    return {
        "id": invitation.id,
        "code": invitation.code,
        "status": status,
        "createdAt": invitation.created_at,
        "expiresAt": invitation.expires_at,
        "usedAt": invitation.used_at,
        "usedBy": (
            {"id": invitation.used_by_user_id, "username": used_by_username}
            if invitation.used_by_user_id
            else None
        ),
        "createdBy": (
            {"id": invitation.created_by_user_id, "username": created_by_username}
            if invitation.created_by_user_id
            else None
        ),
    }


def redemption_code_json(
    redemption: RedemptionCode,
    redeemed_by_username: str | None = None,
    created_by_username: str | None = None,
    stamp: str | None = None,
) -> dict[str, Any]:
    status = "redeemed" if redemption.redeemed_at else "expired" if redemption.expires_at <= (stamp or now()) else "unused"
    return {
        "id": redemption.id,
        "code": redemption.code,
        "status": status,
        "amountMicros": str(redemption.amount_micros),
        "createdAt": redemption.created_at,
        "expiresAt": redemption.expires_at,
        "redeemedAt": redemption.redeemed_at,
        "redeemedBy": (
            {"id": redemption.redeemed_by_user_id, "username": redeemed_by_username}
            if redemption.redeemed_by_user_id
            else None
        ),
        "createdBy": (
            {"id": redemption.created_by_user_id, "username": created_by_username}
            if redemption.created_by_user_id
            else None
        ),
    }


def pagination(total: int, page: int, page_size: int) -> dict[str, int]:
    return {"total": total, "page": page, "pageSize": page_size, "pageCount": max(1, (total + page_size - 1) // page_size)}


def amount_micros(value: Any) -> int:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise HTTPException(400, "amount must be a valid number") from exc
    if not amount.is_finite() or amount <= 0 or amount > Decimal("1000000"):
        raise HTTPException(400, "amount must be greater than 0 and at most 1000000")
    return int((amount * Decimal(1_000_000)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def user_level(value: Any) -> int:
    try:
        level = int(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, "level must be 1, 2, or 3") from exc
    if level not in {1, 2, 3}:
        raise HTTPException(400, "level must be 1, 2, or 3")
    return level


@router.get("/users")
def list_users(_: int = Depends(current_super_admin_id)) -> dict[str, Any]:
    with db() as session:
        users = session.exec(select(User).where(User.deleted_at.is_(None)).order_by(User.created_at.desc())).all()
    return {"users": [user_json(user) for user in users]}


@router.get("/usage-logs")
def list_all_usage_logs(
    _: int = Depends(current_super_admin_id),
    search: Annotated[str, Query(max_length=64)] = "",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 20,
) -> dict[str, Any]:
    conditions = []
    if search.strip():
        conditions.append(User.username.like(f"%{search.strip()}%"))
    offset = (page - 1) * page_size
    with db() as session:
        total = session.exec(
            select(func.count()).select_from(UsageLog).join(User, User.id == UsageLog.user_id).where(*conditions)
        ).one()
        logs = session.exec(
            select(UsageLog, User.username, ModelConfig.name)
            .join(User, User.id == UsageLog.user_id)
            .join(
                ModelConfig,
                (ModelConfig.id == UsageLog.config_id) & (ModelConfig.source == UsageLog.config_source),
                isouter=True,
            )
            .where(*conditions)
            .order_by(UsageLog.created_at.desc())
            .limit(page_size)
            .offset(offset)
        ).all()
    return {
        "usageLogs": [
            {**usage_log_json(item, config_name), "user": {"id": item.user_id, "username": username}}
            for item, username, config_name in logs
        ],
        "pagination": pagination(total, page, page_size),
    }


@router.post("/users", status_code=201)
def create_user(payload: dict[str, Any], _: int = Depends(current_super_admin_id)) -> dict[str, Any]:
    username = str(payload.get("username", "")).strip()
    password = str(payload.get("password", ""))
    if not 3 <= len(username) <= 64 or not 6 <= len(password) <= 128:
        raise HTTPException(400, "invalid username or password length")
    role = str(payload.get("role", "user"))
    if role not in {"user", "superAdmin"}:
        raise HTTPException(400, "role must be user or superAdmin")
    level = user_level(payload.get("level", 1))
    stamp = now()
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    with db() as session:
        user = User(
            created_at=stamp,
            updated_at=stamp,
            username=username,
            password=hashed,
            role=role,
            is_disabled=False,
            level=level,
        )
        session.add(user)
        try:
            session.flush()
        except IntegrityError as exc:
            raise HTTPException(409, "username already exists") from exc
        return {"user": user_json(user)}


@router.patch("/users/{target_user_id}")
def update_user(target_user_id: int, payload: dict[str, Any], admin_id: int = Depends(current_super_admin_id)) -> dict[str, Any]:
    with db() as session:
        user = editable_user(session, target_user_id, admin_id)
        updates: dict[str, Any] = {}
        if "isDisabled" in payload:
            updates["is_disabled"] = 1 if payload["isDisabled"] else 0
        if "level" in payload:
            updates["level"] = user_level(payload["level"])
        if not updates:
            raise HTTPException(400, "no fields to update")
        for key, value in updates.items():
            setattr(user, key, value)
        user.updated_at = now()
        session.add(user)
        session.flush()
        return {"user": user_json(user)}


@router.post("/users/{target_user_id}")
def reset_user_password(target_user_id: int, admin_id: int = Depends(current_super_admin_id)) -> dict[str, str]:
    password = secrets.token_urlsafe(12)
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    with db() as session:
        user = editable_user(session, target_user_id, admin_id)
        user.password = hashed
        user.updated_at = now()
        session.add(user)
    return {"password": password}


@router.delete("/users/{target_user_id}", status_code=204)
def delete_user(target_user_id: int, admin_id: int = Depends(current_super_admin_id)) -> None:
    with db() as session:
        user = editable_user(session, target_user_id, admin_id)
        user.deleted_at = now()
        user.updated_at = now()
        session.add(user)


@router.get("/invitation-codes")
def list_invitation_codes(
    _: int = Depends(current_super_admin_id),
    status: Annotated[str, Query(pattern="^(all|unused|used|expired)$")] = "all",
    search: Annotated[str, Query(max_length=64)] = "",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 10,
) -> dict[str, Any]:
    stamp = now()
    used_users = aliased(User)
    creator_users = aliased(User)
    conditions = []
    if status == "used":
        conditions.append(InvitationCode.used_at.is_not(None))
    elif status == "expired":
        conditions.append(InvitationCode.used_at.is_(None))
        conditions.append(InvitationCode.expires_at <= stamp)
    elif status == "unused":
        conditions.append(InvitationCode.used_at.is_(None))
        conditions.append(InvitationCode.expires_at > stamp)
    if search.strip():
        conditions.append(used_users.username.like(f"%{search.strip()}%"))
    offset = (page - 1) * page_size
    with db() as session:
        total = session.exec(
            select(func.count())
            .select_from(InvitationCode)
            .join(used_users, used_users.id == InvitationCode.used_by_user_id, isouter=True)
            .where(*conditions)
        ).one()
        invitations = session.exec(
            select(InvitationCode, used_users.username, creator_users.username)
            .join(used_users, used_users.id == InvitationCode.used_by_user_id, isouter=True)
            .join(creator_users, creator_users.id == InvitationCode.created_by_user_id, isouter=True)
            .where(*conditions)
            .order_by(InvitationCode.created_at.desc())
            .limit(page_size)
            .offset(offset)
        ).all()
    return {
        "invitationCodes": [
            invitation_code_json(invitation, used_by, created_by, stamp) for invitation, used_by, created_by in invitations
        ],
        "pagination": pagination(total, page, page_size),
    }


@router.post("/invitation-codes", status_code=201)
def create_invitation_code(payload: dict[str, Any], admin_id: int = Depends(current_super_admin_id)) -> dict[str, Any]:
    try:
        days = int(payload.get("days", 0))
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, "validity must be 1, 7, or 30 days") from exc
    if days not in {1, 7, 30}:
        raise HTTPException(400, "validity must be 1, 7, or 30 days")

    created = datetime.now(timezone.utc)
    with db() as session:
        invitation = InvitationCode(
            created_at=created.isoformat(),
            expires_at=(created + timedelta(days=days)).isoformat(),
            code=secrets.token_hex(6).upper(),
            created_by_user_id=admin_id,
        )
        session.add(invitation)
        session.flush()
        created_by = session.exec(select(User.username).where(User.id == admin_id)).first()
        return {"invitationCode": invitation_code_json(invitation, None, created_by, created.isoformat())}


@router.get("/redemption-codes")
def list_redemption_codes(
    _: int = Depends(current_super_admin_id),
    status: Annotated[str, Query(pattern="^(all|unused|redeemed|expired)$")] = "all",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 10,
) -> dict[str, Any]:
    stamp = now()
    redeemer_users = aliased(User)
    creator_users = aliased(User)
    conditions = []
    if status == "redeemed":
        conditions.append(RedemptionCode.redeemed_at.is_not(None))
    elif status == "expired":
        conditions.append(RedemptionCode.redeemed_at.is_(None))
        conditions.append(RedemptionCode.expires_at <= stamp)
    elif status == "unused":
        conditions.append(RedemptionCode.redeemed_at.is_(None))
        conditions.append(RedemptionCode.expires_at > stamp)
    offset = (page - 1) * page_size
    with db() as session:
        total = session.exec(select(func.count()).select_from(RedemptionCode).where(*conditions)).one()
        redemptions = session.exec(
            select(RedemptionCode, redeemer_users.username, creator_users.username)
            .join(redeemer_users, redeemer_users.id == RedemptionCode.redeemed_by_user_id, isouter=True)
            .join(creator_users, creator_users.id == RedemptionCode.created_by_user_id, isouter=True)
            .where(*conditions)
            .order_by(RedemptionCode.created_at.desc())
            .limit(page_size)
            .offset(offset)
        ).all()
    return {
        "redemptionCodes": [
            redemption_code_json(item, redeemed_by, created_by, stamp) for item, redeemed_by, created_by in redemptions
        ],
        "pagination": pagination(total, page, page_size),
    }


@router.post("/redemption-codes", status_code=201)
def create_redemption_code(payload: dict[str, Any], admin_id: int = Depends(current_super_admin_id)) -> dict[str, Any]:
    try:
        days = int(payload.get("days", 0))
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, "validity must be 1, 7, or 30 days") from exc
    if days not in {1, 7, 30}:
        raise HTTPException(400, "validity must be 1, 7, or 30 days")
    micros = amount_micros(payload.get("amount"))
    created = datetime.now(timezone.utc)
    with db() as session:
        redemption = RedemptionCode(
            created_at=created.isoformat(),
            expires_at=(created + timedelta(days=days)).isoformat(),
            code="RC-" + secrets.token_hex(8).upper(),
            amount_micros=micros,
            created_by_user_id=admin_id,
        )
        session.add(redemption)
        session.flush()
        created_by = session.exec(select(User.username).where(User.id == admin_id)).first()
        return {"redemptionCode": redemption_code_json(redemption, None, created_by, created.isoformat())}


@router.get("/default-models")
def list_default_models(_: int = Depends(current_super_admin_id)) -> dict[str, Any]:
    with db() as session:
        configs = session.exec(
            select(ModelConfig)
            .where(ModelConfig.source == "official", ModelConfig.deleted_at.is_(None))
            .order_by(ModelConfig.updated_at.desc())
        ).all()
    return {"configs": [official_config_json(config) for config in configs]}


def _admin_visible_config(session: Session, config_id: int, admin_id: int) -> ModelConfig | None:
    return session.exec(
        select(ModelConfig).where(
            ModelConfig.id == config_id,
            ModelConfig.deleted_at.is_(None),
            or_(ModelConfig.source == "official", ModelConfig.user_id == admin_id),
        )
    ).first()


@router.post("/model-configs/{config_id}/secret")
def get_model_config_secret(config_id: int, admin_id: int = Depends(current_super_admin_id)) -> dict[str, str]:
    with db() as session:
        config = _admin_visible_config(session, config_id, admin_id)
    if not config:
        raise HTTPException(404, "config not found")
    return {"apiKey": config_api_key(config)}


@router.patch("/model-configs/{config_id}")
async def update_model_config(
    config_id: int,
    payload: dict[str, Any],
    admin_id: int = Depends(current_super_admin_id),
) -> dict[str, Any]:
    with db() as session:
        config = _admin_visible_config(session, config_id, admin_id)
    if not config:
        raise HTTPException(404, "config not found")
    target_source = str(payload.get("source", config.source))
    if target_source not in {"user", "official"}:
        raise HTTPException(400, "invalid config source")

    normalized = normalize_config_payload(payload, config)
    if bool(payload.get("isEnabled", config.is_enabled)):
        validate_api_key(normalized["provider"], normalized["api_key"])
    updates = config_update_fields(payload, config, normalized)
    try:
        updates.update(pricing_updates(payload, config))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    source_changed = target_source != config.source
    if source_changed:
        updates.update(source=target_source, user_id=None if target_source == "official" else admin_id)
    if not updates:
        raise HTTPException(400, "no fields to update")

    stamp = now()
    with db() as session:
        is_active = bool(updates.get("is_active", config.is_active))
        purpose = updates.get("purpose", config.purpose)
        if is_active and target_source == "official":
            session.execute(
                update(ModelConfig)
                .where(
                    ModelConfig.source == "official",
                    ModelConfig.purpose == purpose,
                    ModelConfig.id != config_id,
                    ModelConfig.deleted_at.is_(None),
                )
                .values(is_active=0, updated_at=stamp),
                execution_options={"synchronize_session": False},
            )
        elif is_active:
            session.execute(
                update(ModelConfig)
                .where(
                    ModelConfig.source == "user",
                    ModelConfig.user_id == admin_id,
                    ModelConfig.purpose == purpose,
                    ModelConfig.id != config_id,
                    ModelConfig.deleted_at.is_(None),
                )
                .values(is_active=0, updated_at=stamp),
                execution_options={"synchronize_session": False},
            )
            session.execute(
                delete(UserOfficialConfigDefault).where(
                    UserOfficialConfigDefault.user_id == admin_id,
                    UserOfficialConfigDefault.purpose == purpose,
                ),
                execution_options={"synchronize_session": False},
            )
        if source_changed and target_source == "official":
            session.execute(
                update(ChatSession)
                .where(ChatSession.user_id == admin_id, ChatSession.config_id == config_id)
                .values(config_id=None, official_config_id=config_id),
                execution_options={"synchronize_session": False},
            )
        elif source_changed:
            session.execute(
                delete(UserOfficialConfigDefault).where(UserOfficialConfigDefault.official_config_id == config_id),
                execution_options={"synchronize_session": False},
            )
            session.execute(
                update(ChatSession)
                .where(ChatSession.user_id == admin_id, ChatSession.official_config_id == config_id)
                .values(config_id=config_id, official_config_id=None),
                execution_options={"synchronize_session": False},
            )
            session.execute(
                update(ChatSession).where(ChatSession.official_config_id == config_id).values(official_config_id=None),
                execution_options={"synchronize_session": False},
            )
        session.execute(
            update(ModelConfig).where(ModelConfig.id == config_id).values(**updates, updated_at=stamp),
            execution_options={"synchronize_session": False},
        )
        updated = session.exec(select(ModelConfig).where(ModelConfig.id == config_id)).first()
        return {"config": config_json(updated)}


@router.post("/default-models", status_code=201)
async def create_default_model(payload: dict[str, Any], _: int = Depends(current_super_admin_id)) -> dict[str, Any]:
    normalized = normalize_config_payload(payload)
    if normalized["api_key"] or payload.get("isEnabled", True) or payload.get("isActive"):
        validate_api_key(normalized["provider"], normalized["api_key"])
    fields = config_create_fields(payload, normalized)
    try:
        pricing = normalize_pricing(payload)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    stamp = now()
    with db() as session:
        if bool(payload.get("isActive")):
            session.execute(
                update(ModelConfig)
                .where(
                    ModelConfig.source == "official",
                    ModelConfig.purpose == fields["purpose"],
                    ModelConfig.deleted_at.is_(None),
                )
                .values(is_active=0, updated_at=stamp),
                execution_options={"synchronize_session": False},
            )
        config = ModelConfig(
            created_at=stamp,
            updated_at=stamp,
            user_id=None,
            source="official",
            **fields,
            **pricing,
            pricing_json=pricing_snapshot(pricing),
        )
        session.add(config)
        session.flush()
        session.refresh(config)
        return {"config": official_config_json(config)}


@router.patch("/default-models/{config_id}")
async def update_default_model(config_id: int, payload: dict[str, Any], _: int = Depends(current_super_admin_id)) -> dict[str, Any]:
    with db() as session:
        config = session.exec(
            select(ModelConfig).where(
                ModelConfig.id == config_id,
                ModelConfig.source == "official",
                ModelConfig.deleted_at.is_(None),
            )
        ).first()
    if not config:
        raise HTTPException(404, "official config not found")

    normalized = normalize_config_payload(payload, config)
    if bool(payload.get("isEnabled", config.is_enabled)):
        validate_api_key(normalized["provider"], normalized["api_key"])
    updates = config_update_fields(payload, config, normalized)
    try:
        updates.update(pricing_updates(payload, config))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if not updates:
        raise HTTPException(400, "no fields to update")

    stamp = now()
    with db() as session:
        if payload.get("isActive"):
            session.execute(
                update(ModelConfig)
                .where(
                    ModelConfig.source == "official",
                    ModelConfig.purpose == normalized["purpose"],
                    ModelConfig.id != config_id,
                    ModelConfig.deleted_at.is_(None),
                )
                .values(is_active=0, updated_at=stamp),
                execution_options={"synchronize_session": False},
            )
        session.execute(
            update(ModelConfig)
            .where(ModelConfig.id == config_id, ModelConfig.source == "official")
            .values(**updates, updated_at=stamp),
            execution_options={"synchronize_session": False},
        )
        updated = session.exec(select(ModelConfig).where(ModelConfig.id == config_id)).first()
        return {"config": official_config_json(updated)}


@router.delete("/default-models/{config_id}", status_code=204)
def delete_default_model(config_id: int, _: int = Depends(current_super_admin_id)) -> None:
    with db() as session:
        session.execute(
            update(ModelConfig)
            .where(
                ModelConfig.id == config_id,
                ModelConfig.source == "official",
                ModelConfig.deleted_at.is_(None),
            )
            .values(deleted_at=now(), updated_at=now()),
            execution_options={"synchronize_session": False},
        )
