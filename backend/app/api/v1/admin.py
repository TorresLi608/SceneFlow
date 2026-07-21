from __future__ import annotations

import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Annotated, Any

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.database import db, row, rows
from app.api.deps import current_super_admin_id
from app.schemas.serializers import config_json, official_config_json, user_json
from app.services.config_service import config_create_fields, config_update_fields, normalize_config_payload, validate_provider
from app.services.usage_service import normalize_pricing, pricing_updates, usage_log_json
from app.utils.common import now


router = APIRouter(prefix="/api/admin", tags=["admin"])


def editable_user(conn: sqlite3.Connection, target_user_id: int, admin_id: int) -> sqlite3.Row:
    user = row(conn, "SELECT * FROM users WHERE id=? AND deleted_at IS NULL", (target_user_id,))
    if not user:
        raise HTTPException(404, "user not found")
    if target_user_id == admin_id or user["role"] == "superAdmin":
        raise HTTPException(400, "cannot modify superAdmin")
    return user


def invitation_code_json(invitation: sqlite3.Row, stamp: str | None = None) -> dict[str, Any]:
    status = "used" if invitation["used_at"] else "expired" if invitation["expires_at"] <= (stamp or now()) else "unused"
    return {
        "id": invitation["id"],
        "code": invitation["code"],
        "status": status,
        "createdAt": invitation["created_at"],
        "expiresAt": invitation["expires_at"],
        "usedAt": invitation["used_at"],
        "usedBy": (
            {"id": invitation["used_by_user_id"], "username": invitation["used_by_username"]}
            if invitation["used_by_user_id"]
            else None
        ),
        "createdBy": (
            {"id": invitation["created_by_user_id"], "username": invitation["created_by_username"]}
            if invitation["created_by_user_id"]
            else None
        ),
    }


def redemption_code_json(redemption: sqlite3.Row, stamp: str | None = None) -> dict[str, Any]:
    status = "redeemed" if redemption["redeemed_at"] else "expired" if redemption["expires_at"] <= (stamp or now()) else "unused"
    return {
        "id": redemption["id"],
        "code": redemption["code"],
        "status": status,
        "amountMicros": redemption["amount_micros"],
        "createdAt": redemption["created_at"],
        "expiresAt": redemption["expires_at"],
        "redeemedAt": redemption["redeemed_at"],
        "redeemedBy": (
            {"id": redemption["redeemed_by_user_id"], "username": redemption["redeemed_by_username"]}
            if redemption["redeemed_by_user_id"]
            else None
        ),
        "createdBy": (
            {"id": redemption["created_by_user_id"], "username": redemption["created_by_username"]}
            if redemption["created_by_user_id"]
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
    with db() as conn:
        users = rows(conn, "SELECT * FROM users WHERE deleted_at IS NULL ORDER BY created_at DESC")
    return {"users": [user_json(user) for user in users]}


@router.get("/usage-logs")
def list_all_usage_logs(
    _: int = Depends(current_super_admin_id),
    search: Annotated[str, Query(max_length=64)] = "",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 20,
) -> dict[str, Any]:
    args: list[Any] = []
    where = ""
    if search.strip():
        where = " WHERE users.username LIKE ?"
        args.append(f"%{search.strip()}%")
    offset = (page - 1) * page_size
    with db() as conn:
        total = row(
            conn,
            f"SELECT COUNT(*) AS total FROM usage_logs JOIN users ON users.id=usage_logs.user_id{where}",
            tuple(args),
        )["total"]
        logs = rows(
            conn,
            f"""SELECT usage_logs.*, users.username
            FROM usage_logs JOIN users ON users.id=usage_logs.user_id
            {where}
            ORDER BY usage_logs.created_at DESC LIMIT ? OFFSET ?""",
            (*args, page_size, offset),
        )
    return {
        "usageLogs": [
            {**usage_log_json(item), "user": {"id": item["user_id"], "username": item["username"]}}
            for item in logs
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
    with db() as conn:
        try:
            cur = conn.execute(
                "INSERT INTO users (created_at, updated_at, username, password, role, is_disabled, level) VALUES (?, ?, ?, ?, ?, 0, ?)",
                (stamp, stamp, username, hashed, role, level),
            )
        except sqlite3.IntegrityError as exc:
            raise HTTPException(409, "username already exists") from exc
        user = row(conn, "SELECT * FROM users WHERE id=?", (cur.lastrowid,))
    return {"user": user_json(user)}


@router.patch("/users/{target_user_id}")
def update_user(target_user_id: int, payload: dict[str, Any], admin_id: int = Depends(current_super_admin_id)) -> dict[str, Any]:
    with db() as conn:
        editable_user(conn, target_user_id, admin_id)
        updates: dict[str, Any] = {}
        if "isDisabled" in payload:
            updates["is_disabled"] = 1 if payload["isDisabled"] else 0
        if "level" in payload:
            updates["level"] = user_level(payload["level"])
        if not updates:
            raise HTTPException(400, "no fields to update")
        conn.execute(
            f"UPDATE users SET {', '.join(f'{key}=?' for key in updates)}, updated_at=? WHERE id=?",
            (*updates.values(), now(), target_user_id),
        )
        user = row(conn, "SELECT * FROM users WHERE id=?", (target_user_id,))
    return {"user": user_json(user)}


@router.post("/users/{target_user_id}")
def reset_user_password(target_user_id: int, admin_id: int = Depends(current_super_admin_id)) -> dict[str, str]:
    password = secrets.token_urlsafe(12)
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    with db() as conn:
        editable_user(conn, target_user_id, admin_id)
        conn.execute("UPDATE users SET password=?, updated_at=? WHERE id=?", (hashed, now(), target_user_id))
    return {"password": password}


@router.delete("/users/{target_user_id}", status_code=204)
def delete_user(target_user_id: int, admin_id: int = Depends(current_super_admin_id)) -> None:
    with db() as conn:
        editable_user(conn, target_user_id, admin_id)
        conn.execute("UPDATE users SET deleted_at=?, updated_at=? WHERE id=?", (now(), now(), target_user_id))


@router.get("/invitation-codes")
def list_invitation_codes(
    _: int = Depends(current_super_admin_id),
    status: Annotated[str, Query(pattern="^(all|unused|used|expired)$")] = "all",
    search: Annotated[str, Query(max_length=64)] = "",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 10,
) -> dict[str, Any]:
    stamp = now()
    conditions = []
    args: list[Any] = []
    if status == "used":
        conditions.append("invitation_codes.used_at IS NOT NULL")
    elif status == "expired":
        conditions.append("invitation_codes.used_at IS NULL AND invitation_codes.expires_at<=?")
        args.append(stamp)
    elif status == "unused":
        conditions.append("invitation_codes.used_at IS NULL AND invitation_codes.expires_at>?")
        args.append(stamp)
    if search.strip():
        conditions.append("used_users.username LIKE ?")
        args.append(f"%{search.strip()}%")
    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    offset = (page - 1) * page_size
    with db() as conn:
        total = row(
            conn,
            f"""SELECT COUNT(*) AS total FROM invitation_codes
            LEFT JOIN users AS used_users ON used_users.id=invitation_codes.used_by_user_id{where}""",
            tuple(args),
        )["total"]
        invitations = rows(
            conn,
            f"""SELECT invitation_codes.*, used_users.username AS used_by_username,
            creator_users.username AS created_by_username
            FROM invitation_codes
            LEFT JOIN users AS used_users ON used_users.id=invitation_codes.used_by_user_id
            LEFT JOIN users AS creator_users ON creator_users.id=invitation_codes.created_by_user_id
            {where}
            ORDER BY invitation_codes.created_at DESC LIMIT ? OFFSET ?""",
            (*args, page_size, offset),
        )
    return {
        "invitationCodes": [invitation_code_json(invitation, stamp) for invitation in invitations],
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
    code = secrets.token_hex(6).upper()
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO invitation_codes (created_at, expires_at, code, created_by_user_id) VALUES (?, ?, ?, ?)",
            (created.isoformat(), (created + timedelta(days=days)).isoformat(), code, admin_id),
        )
        invitation = row(
            conn,
            """SELECT invitation_codes.*, NULL AS used_by_username, users.username AS created_by_username
            FROM invitation_codes LEFT JOIN users ON users.id=invitation_codes.created_by_user_id WHERE invitation_codes.id=?""",
            (cur.lastrowid,),
        )
    return {"invitationCode": invitation_code_json(invitation, created.isoformat())}


@router.get("/redemption-codes")
def list_redemption_codes(
    _: int = Depends(current_super_admin_id),
    status: Annotated[str, Query(pattern="^(all|unused|redeemed|expired)$")] = "all",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 10,
) -> dict[str, Any]:
    stamp = now()
    conditions = []
    args: list[Any] = []
    if status == "redeemed":
        conditions.append("redemption_codes.redeemed_at IS NOT NULL")
    elif status == "expired":
        conditions.append("redemption_codes.redeemed_at IS NULL AND redemption_codes.expires_at<=?")
        args.append(stamp)
    elif status == "unused":
        conditions.append("redemption_codes.redeemed_at IS NULL AND redemption_codes.expires_at>?")
        args.append(stamp)
    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    offset = (page - 1) * page_size
    with db() as conn:
        total = row(conn, f"SELECT COUNT(*) AS total FROM redemption_codes{where}", tuple(args))["total"]
        redemptions = rows(
            conn,
            f"""SELECT redemption_codes.*, redeemer_users.username AS redeemed_by_username,
            creator_users.username AS created_by_username
            FROM redemption_codes
            LEFT JOIN users AS redeemer_users ON redeemer_users.id=redemption_codes.redeemed_by_user_id
            LEFT JOIN users AS creator_users ON creator_users.id=redemption_codes.created_by_user_id
            {where}
            ORDER BY redemption_codes.created_at DESC LIMIT ? OFFSET ?""",
            (*args, page_size, offset),
        )
    return {
        "redemptionCodes": [redemption_code_json(item, stamp) for item in redemptions],
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
    code = "RC-" + secrets.token_hex(8).upper()
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO redemption_codes (created_at, expires_at, code, amount_micros, created_by_user_id) VALUES (?, ?, ?, ?, ?)",
            (created.isoformat(), (created + timedelta(days=days)).isoformat(), code, micros, admin_id),
        )
        redemption = row(
            conn,
            """SELECT redemption_codes.*, NULL AS redeemed_by_username, users.username AS created_by_username
            FROM redemption_codes LEFT JOIN users ON users.id=redemption_codes.created_by_user_id WHERE redemption_codes.id=?""",
            (cur.lastrowid,),
        )
    return {"redemptionCode": redemption_code_json(redemption, created.isoformat())}


@router.get("/default-models")
def list_default_models(_: int = Depends(current_super_admin_id)) -> dict[str, Any]:
    with db() as conn:
        configs = rows(conn, "SELECT * FROM model_configs WHERE source='official' AND deleted_at IS NULL ORDER BY updated_at DESC")
    return {"configs": [official_config_json(config) for config in configs]}


@router.patch("/model-configs/{config_id}")
async def update_model_config(
    config_id: int,
    payload: dict[str, Any],
    admin_id: int = Depends(current_super_admin_id),
) -> dict[str, Any]:
    with db() as conn:
        config = row(
            conn,
            "SELECT * FROM model_configs WHERE id=? AND deleted_at IS NULL AND (source='official' OR user_id=?)",
            (config_id, admin_id),
        )
    if not config:
        raise HTTPException(404, "config not found")
    target_source = str(payload.get("source", config["source"]))
    if target_source not in {"user", "official"}:
        raise HTTPException(400, "invalid config source")

    normalized = normalize_config_payload(payload, config)
    if normalized["needs_validation"]:
        await validate_provider(
            normalized["purpose"],
            normalized["provider"],
            normalized["model"],
            normalized["api_key"],
            normalized["base_url"],
        )
    updates = config_update_fields(payload, config, normalized)
    try:
        updates.update(pricing_updates(payload, config))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    source_changed = target_source != config["source"]
    if source_changed:
        updates.update(source=target_source, user_id=None if target_source == "official" else admin_id)
    if not updates:
        raise HTTPException(400, "no fields to update")

    stamp = now()
    with db() as conn:
        is_active = bool(updates.get("is_active", config["is_active"]))
        purpose = updates.get("purpose", config["purpose"])
        if is_active and target_source == "official":
            conn.execute(
                "UPDATE model_configs SET is_active=0, updated_at=? WHERE source='official' AND purpose=? AND id<>? AND deleted_at IS NULL",
                (stamp, purpose, config_id),
            )
        elif is_active:
            conn.execute(
                "UPDATE model_configs SET is_active=0, updated_at=? WHERE source='user' AND user_id=? AND purpose=? AND id<>? AND deleted_at IS NULL",
                (stamp, admin_id, purpose, config_id),
            )
            conn.execute(
                "DELETE FROM user_official_config_defaults WHERE user_id=? AND purpose=?",
                (admin_id, purpose),
            )
        if source_changed and target_source == "official":
            conn.execute(
                "UPDATE chat_sessions SET config_id=NULL, official_config_id=? WHERE user_id=? AND config_id=?",
                (config_id, admin_id, config_id),
            )
        elif source_changed:
            conn.execute("DELETE FROM user_official_config_defaults WHERE official_config_id=?", (config_id,))
            conn.execute(
                "UPDATE chat_sessions SET config_id=?, official_config_id=NULL WHERE user_id=? AND official_config_id=?",
                (config_id, admin_id, config_id),
            )
            conn.execute("UPDATE chat_sessions SET official_config_id=NULL WHERE official_config_id=?", (config_id,))
        conn.execute(
            f"UPDATE model_configs SET {', '.join(f'{key}=?' for key in updates)}, updated_at=? WHERE id=?",
            (*updates.values(), stamp, config_id),
        )
        config = row(conn, "SELECT * FROM model_configs WHERE id=?", (config_id,))
    return {"config": config_json(config)}


@router.post("/default-models", status_code=201)
async def create_default_model(payload: dict[str, Any], _: int = Depends(current_super_admin_id)) -> dict[str, Any]:
    normalized = normalize_config_payload(payload)
    is_verified = 0
    if normalized["api_key"] or payload.get("isActive"):
        await validate_provider(
            normalized["purpose"],
            normalized["provider"],
            normalized["model"],
            normalized["api_key"],
            normalized["base_url"],
        )
        is_verified = 1
    fields = config_create_fields(payload, normalized, is_verified)
    try:
        pricing = normalize_pricing(payload)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    stamp = now()
    with db() as conn:
        if bool(payload.get("isActive")):
            conn.execute("UPDATE model_configs SET is_active=0, updated_at=? WHERE source='official' AND purpose=? AND deleted_at IS NULL", (stamp, fields["purpose"]))
        cur = conn.execute(
            """INSERT INTO model_configs
            (created_at, updated_at, user_id, source, name, description, purpose, provider, base_url, model_name, encrypted_key, is_active, is_enabled, is_verified,
             pricing_multiplier, input_price_per_million, output_price_per_million, cache_read_price_per_million,
             cache_write_price_per_million, unit_price, unit_name)
            VALUES (?, ?, NULL, 'official', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                stamp,
                stamp,
                fields["name"],
                fields["description"],
                fields["purpose"],
                fields["provider"],
                fields["base_url"],
                fields["model_name"],
                fields["encrypted_key"],
                fields["is_active"],
                fields["is_enabled"],
                fields["is_verified"],
                pricing["pricing_multiplier"],
                pricing["input_price_per_million"],
                pricing["output_price_per_million"],
                pricing["cache_read_price_per_million"],
                pricing["cache_write_price_per_million"],
                pricing["unit_price"],
                pricing["unit_name"],
            ),
        )
        config = row(conn, "SELECT * FROM model_configs WHERE id=?", (cur.lastrowid,))
    return {"config": official_config_json(config)}


@router.patch("/default-models/{config_id}")
async def update_default_model(config_id: int, payload: dict[str, Any], _: int = Depends(current_super_admin_id)) -> dict[str, Any]:
    with db() as conn:
        config = row(conn, "SELECT * FROM model_configs WHERE id=? AND source='official' AND deleted_at IS NULL", (config_id,))
    if not config:
        raise HTTPException(404, "official config not found")

    normalized = normalize_config_payload(payload, config)
    if normalized["needs_validation"]:
        await validate_provider(
            normalized["purpose"],
            normalized["provider"],
            normalized["model"],
            normalized["api_key"],
            normalized["base_url"],
        )
    updates = config_update_fields(payload, config, normalized)
    try:
        updates.update(pricing_updates(payload, config))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if not updates:
        raise HTTPException(400, "no fields to update")

    stamp = now()
    with db() as conn:
        if payload.get("isActive"):
            conn.execute(
                "UPDATE model_configs SET is_active=0, updated_at=? WHERE source='official' AND purpose=? AND id<>? AND deleted_at IS NULL",
                (stamp, normalized["purpose"], config_id),
            )
        conn.execute(
            f"UPDATE model_configs SET {', '.join(f'{key}=?' for key in updates)}, updated_at=? WHERE id=? AND source='official'",
            (*updates.values(), stamp, config_id),
        )
        config = row(conn, "SELECT * FROM model_configs WHERE id=?", (config_id,))
    return {"config": official_config_json(config)}


@router.delete("/default-models/{config_id}", status_code=204)
def delete_default_model(config_id: int, _: int = Depends(current_super_admin_id)) -> None:
    with db() as conn:
        conn.execute(
            "UPDATE model_configs SET deleted_at=?, updated_at=? WHERE id=? AND source='official' AND deleted_at IS NULL",
            (now(), now(), config_id),
        )
