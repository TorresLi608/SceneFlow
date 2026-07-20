from __future__ import annotations

import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
from fastapi import APIRouter, Depends, HTTPException

from config_service import config_create_fields, config_update_fields, normalize_config_payload, validate_provider
from database import db, row, rows
from security import current_super_admin_id
from serializers import official_config_json, user_json
from usage_service import normalize_pricing, pricing_updates
from utils import now


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
    }


@router.get("/users")
def list_users(_: int = Depends(current_super_admin_id)) -> dict[str, Any]:
    with db() as conn:
        users = rows(conn, "SELECT * FROM users WHERE deleted_at IS NULL ORDER BY created_at DESC")
    return {"users": [user_json(user) for user in users]}


@router.post("/users", status_code=201)
def create_user(payload: dict[str, Any], _: int = Depends(current_super_admin_id)) -> dict[str, Any]:
    username = str(payload.get("username", "")).strip()
    password = str(payload.get("password", ""))
    if not 3 <= len(username) <= 64 or not 6 <= len(password) <= 128:
        raise HTTPException(400, "invalid username or password length")
    stamp = now()
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    with db() as conn:
        try:
            cur = conn.execute(
                "INSERT INTO users (created_at, updated_at, username, password, role, is_disabled) VALUES (?, ?, ?, ?, 'user', 0)",
                (stamp, stamp, username, hashed),
            )
        except sqlite3.IntegrityError as exc:
            raise HTTPException(409, "username already exists") from exc
        user = row(conn, "SELECT * FROM users WHERE id=?", (cur.lastrowid,))
    return {"user": user_json(user)}


@router.patch("/users/{target_user_id}")
def update_user(target_user_id: int, payload: dict[str, Any], admin_id: int = Depends(current_super_admin_id)) -> dict[str, Any]:
    with db() as conn:
        editable_user(conn, target_user_id, admin_id)
        if "isDisabled" not in payload:
            raise HTTPException(400, "no fields to update")
        conn.execute(
            "UPDATE users SET is_disabled=?, updated_at=? WHERE id=?",
            (1 if payload["isDisabled"] else 0, now(), target_user_id),
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
def list_invitation_codes(_: int = Depends(current_super_admin_id)) -> dict[str, Any]:
    stamp = now()
    with db() as conn:
        invitations = rows(
            conn,
            """SELECT invitation_codes.*, users.username AS used_by_username
            FROM invitation_codes
            LEFT JOIN users ON users.id=invitation_codes.used_by_user_id
            ORDER BY invitation_codes.created_at DESC""",
        )
    return {"invitationCodes": [invitation_code_json(invitation, stamp) for invitation in invitations]}


@router.post("/invitation-codes", status_code=201)
def create_invitation_code(payload: dict[str, Any], _: int = Depends(current_super_admin_id)) -> dict[str, Any]:
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
            "INSERT INTO invitation_codes (created_at, expires_at, code) VALUES (?, ?, ?)",
            (created.isoformat(), (created + timedelta(days=days)).isoformat(), code),
        )
        invitation = row(
            conn,
            """SELECT invitation_codes.*, NULL AS used_by_username
            FROM invitation_codes WHERE id=?""",
            (cur.lastrowid,),
        )
    return {"invitationCode": invitation_code_json(invitation, created.isoformat())}


@router.get("/default-models")
def list_default_models(_: int = Depends(current_super_admin_id)) -> dict[str, Any]:
    with db() as conn:
        configs = rows(conn, "SELECT * FROM official_model_configs WHERE deleted_at IS NULL ORDER BY updated_at DESC")
    return {"configs": [official_config_json(config) for config in configs]}


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
            conn.execute("UPDATE official_model_configs SET is_active=0, updated_at=? WHERE purpose=? AND deleted_at IS NULL", (stamp, fields["purpose"]))
        cur = conn.execute(
            """INSERT INTO official_model_configs
            (created_at, updated_at, name, description, purpose, provider, base_url, model_name, encrypted_key, is_active, is_enabled, is_verified,
             pricing_multiplier, input_price_per_million, output_price_per_million, cache_read_price_per_million,
             cache_write_price_per_million, unit_price, unit_name)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
        config = row(conn, "SELECT * FROM official_model_configs WHERE id=?", (cur.lastrowid,))
    return {"config": official_config_json(config)}


@router.patch("/default-models/{config_id}")
async def update_default_model(config_id: int, payload: dict[str, Any], _: int = Depends(current_super_admin_id)) -> dict[str, Any]:
    with db() as conn:
        config = row(conn, "SELECT * FROM official_model_configs WHERE id=? AND deleted_at IS NULL", (config_id,))
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

    stamp = now()
    with db() as conn:
        if payload.get("isActive"):
            conn.execute(
                "UPDATE official_model_configs SET is_active=0, updated_at=? WHERE purpose=? AND id<>? AND deleted_at IS NULL",
                (stamp, normalized["purpose"], config_id),
            )
        conn.execute(
            f"UPDATE official_model_configs SET {', '.join(f'{key}=?' for key in updates)}, updated_at=? WHERE id=?",
            (*updates.values(), stamp, config_id),
        )
        config = row(conn, "SELECT * FROM official_model_configs WHERE id=?", (config_id,))
    return {"config": official_config_json(config)}


@router.delete("/default-models/{config_id}", status_code=204)
def delete_default_model(config_id: int, _: int = Depends(current_super_admin_id)) -> None:
    with db() as conn:
        conn.execute(
            "UPDATE official_model_configs SET deleted_at=?, updated_at=? WHERE id=? AND deleted_at IS NULL",
            (now(), now(), config_id),
        )
