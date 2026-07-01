from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from config_service import normalize_model, normalize_provider, normalize_purpose, validate_config_fields, validate_provider
from database import db, row, rows
from security import current_user_id, decrypt, encrypt
from serializers import config_json
from utils import now


router = APIRouter(prefix="/api/settings/keys", tags=["settings"])


@router.get("")
def list_configs(user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    with db() as conn:
        configs = rows(conn, "SELECT * FROM user_configs WHERE user_id=? AND deleted_at IS NULL ORDER BY updated_at DESC", (user_id,))
    return {"configs": [config_json(config) for config in configs]}


@router.post("/validate")
async def validate_config(payload: dict[str, Any], user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    purpose = normalize_purpose(str(payload.get("purpose", "")))
    provider = normalize_provider(str(payload.get("provider", "")))
    model = normalize_model(provider, str(payload.get("modelSeries") or payload.get("model") or ""))
    api_key = str(payload.get("apiKey", "")).strip()
    validate_config_fields(purpose, provider, model)
    await validate_provider(purpose, provider, model, api_key)
    return {"valid": True, "purpose": purpose, "provider": provider, "modelSeries": model, "model": model}


@router.get("/{config_id}")
def get_config(config_id: int, user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    with db() as conn:
        config = row(conn, "SELECT * FROM user_configs WHERE id=? AND user_id=? AND deleted_at IS NULL", (config_id, user_id))
    if not config:
        raise HTTPException(404, "config not found")
    return {"config": config_json(config)}


@router.post("", status_code=201)
async def create_config(payload: dict[str, Any], user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    purpose = normalize_purpose(str(payload.get("purpose", "")))
    provider = normalize_provider(str(payload.get("provider", "")))
    model = normalize_model(provider, str(payload.get("modelSeries") or payload.get("model") or ""))
    api_key = str(payload.get("apiKey", "")).strip()
    validate_config_fields(purpose, provider, model)
    await validate_provider(purpose, provider, model, api_key)
    stamp = now()
    with db() as conn:
        if bool(payload.get("isActive")):
            conn.execute("UPDATE user_configs SET is_active=0, updated_at=? WHERE user_id=? AND purpose=? AND deleted_at IS NULL", (stamp, user_id, purpose))
        cur = conn.execute(
            """INSERT INTO user_configs
            (created_at, updated_at, user_id, name, description, purpose, provider, model_name, encrypted_key, is_active, is_verified)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
            (
                stamp,
                stamp,
                user_id,
                str(payload.get("name", "")).strip()[:64],
                str(payload.get("description", "")).strip()[:255],
                purpose,
                provider,
                model,
                encrypt(api_key),
                1 if payload.get("isActive") else 0,
            ),
        )
        config = row(conn, "SELECT * FROM user_configs WHERE id=?", (cur.lastrowid,))
    return {"config": config_json(config)}


@router.patch("/{config_id}")
async def update_config(config_id: int, payload: dict[str, Any], user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    with db() as conn:
        config = row(conn, "SELECT * FROM user_configs WHERE id=? AND user_id=? AND deleted_at IS NULL", (config_id, user_id))
    if not config:
        raise HTTPException(404, "config not found")

    purpose = normalize_purpose(str(payload.get("purpose", config["purpose"])))
    provider = normalize_provider(str(payload.get("provider", config["provider"])))
    model = normalize_model(provider, str(payload.get("modelSeries") or payload.get("model") or config["model_name"] or ""))
    validate_config_fields(purpose, provider, model)
    api_key = str(payload["apiKey"]).strip() if "apiKey" in payload else decrypt(config["encrypted_key"])
    needs_validation = any(key in payload for key in ("apiKey", "provider", "modelSeries", "model", "purpose")) or payload.get("isActive")
    if needs_validation:
        await validate_provider(purpose, provider, model, api_key)

    updates: dict[str, Any] = {}
    if "name" in payload:
        updates["name"] = str(payload["name"]).strip()[:64]
    if "description" in payload:
        updates["description"] = str(payload["description"]).strip()[:255]
    if "purpose" in payload:
        updates["purpose"] = purpose
    if "provider" in payload:
        updates["provider"] = provider
    if any(key in payload for key in ("modelSeries", "model")):
        updates["model_name"] = model
    if "apiKey" in payload:
        if not 8 <= len(str(payload["apiKey"])) <= 512:
            raise HTTPException(400, "apiKey length must be between 8 and 512")
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
            conn.execute("UPDATE user_configs SET is_active=0, updated_at=? WHERE user_id=? AND purpose=? AND id<>? AND deleted_at IS NULL", (stamp, user_id, purpose, config_id))
        conn.execute(
            f"UPDATE user_configs SET {', '.join(f'{key}=?' for key in updates)}, updated_at=? WHERE id=? AND user_id=?",
            (*updates.values(), stamp, config_id, user_id),
        )
        config = row(conn, "SELECT * FROM user_configs WHERE id=?", (config_id,))
    return {"config": config_json(config)}


@router.delete("/{config_id}", status_code=204)
def delete_config(config_id: int, user_id: int = Depends(current_user_id)) -> None:
    with db() as conn:
        conn.execute("UPDATE user_configs SET deleted_at=?, updated_at=? WHERE id=? AND user_id=? AND deleted_at IS NULL", (now(), now(), config_id, user_id))
