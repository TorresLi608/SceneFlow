from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from config_service import normalize_base_url, normalize_model, normalize_provider, normalize_purpose, validate_config_fields, validate_provider
from database import db, row, rows
from security import current_super_admin_id, decrypt, encrypt
from serializers import official_config_json, user_json
from utils import now


router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/users")
def list_users(_: int = Depends(current_super_admin_id)) -> dict[str, Any]:
    with db() as conn:
        users = rows(conn, "SELECT * FROM users WHERE deleted_at IS NULL ORDER BY created_at DESC")
    return {"users": [user_json(user) for user in users]}


@router.patch("/users/{target_user_id}")
def update_user(target_user_id: int, payload: dict[str, Any], admin_id: int = Depends(current_super_admin_id)) -> dict[str, Any]:
    with db() as conn:
        user = row(conn, "SELECT * FROM users WHERE id=? AND deleted_at IS NULL", (target_user_id,))
        if not user:
            raise HTTPException(404, "user not found")
        if target_user_id == admin_id or user["role"] == "superAdmin":
            raise HTTPException(400, "cannot modify superAdmin")
        if "isDisabled" not in payload:
            raise HTTPException(400, "no fields to update")
        conn.execute(
            "UPDATE users SET is_disabled=?, updated_at=? WHERE id=?",
            (1 if payload["isDisabled"] else 0, now(), target_user_id),
        )
        user = row(conn, "SELECT * FROM users WHERE id=?", (target_user_id,))
    return {"user": user_json(user)}


@router.delete("/users/{target_user_id}", status_code=204)
def delete_user(target_user_id: int, admin_id: int = Depends(current_super_admin_id)) -> None:
    with db() as conn:
        user = row(conn, "SELECT * FROM users WHERE id=? AND deleted_at IS NULL", (target_user_id,))
        if not user:
            raise HTTPException(404, "user not found")
        if target_user_id == admin_id or user["role"] == "superAdmin":
            raise HTTPException(400, "cannot delete superAdmin")
        conn.execute("UPDATE users SET deleted_at=?, updated_at=? WHERE id=?", (now(), now(), target_user_id))


@router.get("/default-models")
def list_default_models(_: int = Depends(current_super_admin_id)) -> dict[str, Any]:
    with db() as conn:
        configs = rows(conn, "SELECT * FROM official_model_configs WHERE deleted_at IS NULL ORDER BY updated_at DESC")
    return {"configs": [official_config_json(config) for config in configs]}


@router.post("/default-models", status_code=201)
async def create_default_model(payload: dict[str, Any], _: int = Depends(current_super_admin_id)) -> dict[str, Any]:
    purpose = normalize_purpose(str(payload.get("purpose", "")))
    provider = normalize_provider(str(payload.get("provider", "")))
    base_url = normalize_base_url(str(payload.get("baseUrl", "")))
    model = normalize_model(provider, str(payload.get("modelSeries") or payload.get("model") or ""))
    api_key = str(payload.get("apiKey", "")).strip()
    validate_config_fields(purpose, provider, model, base_url)
    is_verified = 0
    if api_key or payload.get("isActive"):
        await validate_provider(purpose, provider, model, api_key, base_url)
        is_verified = 1
    stamp = now()
    with db() as conn:
        if bool(payload.get("isActive")):
            conn.execute("UPDATE official_model_configs SET is_active=0, updated_at=? WHERE purpose=? AND deleted_at IS NULL", (stamp, purpose))
        cur = conn.execute(
            """INSERT INTO official_model_configs
            (created_at, updated_at, name, description, purpose, provider, base_url, model_name, encrypted_key, is_active, is_verified)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                stamp,
                stamp,
                str(payload.get("name", "")).strip()[:64],
                str(payload.get("description", "")).strip()[:255],
                purpose,
                provider,
                base_url,
                model,
                encrypt(api_key),
                1 if payload.get("isActive") else 0,
                is_verified,
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

    purpose = normalize_purpose(str(payload.get("purpose", config["purpose"])))
    provider = normalize_provider(str(payload.get("provider", config["provider"])))
    base_url = normalize_base_url(str(payload.get("baseUrl", config["base_url"] or "")))
    model = normalize_model(provider, str(payload.get("modelSeries") or payload.get("model") or config["model_name"] or ""))
    validate_config_fields(purpose, provider, model, base_url)
    api_key = str(payload["apiKey"]).strip() if "apiKey" in payload else decrypt(config["encrypted_key"])
    needs_validation = any(key in payload for key in ("apiKey", "provider", "baseUrl", "modelSeries", "model", "purpose")) or payload.get("isActive")
    if needs_validation:
        await validate_provider(purpose, provider, model, api_key, base_url)

    updates: dict[str, Any] = {}
    if "name" in payload:
        updates["name"] = str(payload["name"]).strip()[:64]
    if "description" in payload:
        updates["description"] = str(payload["description"]).strip()[:255]
    if "purpose" in payload:
        updates["purpose"] = purpose
    if "provider" in payload:
        updates["provider"] = provider
    if "baseUrl" in payload:
        updates["base_url"] = base_url
    if any(key in payload for key in ("modelSeries", "model")):
        updates["model_name"] = model
    if "apiKey" in payload:
        updates["encrypted_key"] = encrypt(api_key)
    if needs_validation:
        updates["is_verified"] = 1
    if "isActive" in payload:
        updates["is_active"] = 1 if payload["isActive"] else 0
    if not updates:
        raise HTTPException(400, "no fields to update")

    stamp = now()
    with db() as conn:
        if payload.get("isActive"):
            conn.execute(
                "UPDATE official_model_configs SET is_active=0, updated_at=? WHERE purpose=? AND id<>? AND deleted_at IS NULL",
                (stamp, purpose, config_id),
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
