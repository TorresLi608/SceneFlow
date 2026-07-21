from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from services.config_service import config_create_fields, config_update_fields, normalize_config_payload, validate_provider
from database import db, row, rows
from security import current_user_id
from serializers import config_json, official_config_json
from lib.utils import now


router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/keys")
def list_configs(user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    with db() as conn:
        configs = rows(conn, "SELECT * FROM user_configs WHERE user_id=? AND deleted_at IS NULL ORDER BY updated_at DESC", (user_id,))
        active_user_purposes = {config["purpose"] for config in configs if config["is_active"] and config["is_enabled"]}
        active_official = {
            config["purpose"]: config["official_config_id"]
            for config in rows(conn, "SELECT purpose, official_config_id FROM user_official_config_defaults WHERE user_id=?", (user_id,))
        }
        official_configs = rows(
            conn,
            "SELECT * FROM official_model_configs WHERE is_enabled=1 AND is_verified=1 AND deleted_at IS NULL ORDER BY purpose, updated_at DESC",
        )
    return {
        "configs": [config_json(config) for config in configs],
        "officialConfigs": [
            official_config_json(
                config,
                False
                if config["purpose"] in active_user_purposes
                else active_official.get(config["purpose"]) == config["id"]
                if config["purpose"] in active_official
                else None,
            )
            for config in official_configs
        ],
    }


@router.post("/keys/validate")
async def validate_config(payload: dict[str, Any], user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    normalized = normalize_config_payload(payload)
    await validate_provider(
        normalized["purpose"],
        normalized["provider"],
        normalized["model"],
        normalized["api_key"],
        normalized["base_url"],
    )
    return {
        "valid": True,
        "purpose": normalized["purpose"],
        "provider": normalized["provider"],
        "baseUrl": normalized["base_url"],
        "modelSeries": normalized["model"],
        "model": normalized["model"],
    }


@router.get("/keys/{config_id}")
def get_config(config_id: int, user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    with db() as conn:
        config = row(conn, "SELECT * FROM user_configs WHERE id=? AND user_id=? AND deleted_at IS NULL", (config_id, user_id))
    if not config:
        raise HTTPException(404, "config not found")
    return {"config": config_json(config)}


@router.post("/keys", status_code=201)
async def create_config(payload: dict[str, Any], user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    normalized = normalize_config_payload(payload)
    await validate_provider(
        normalized["purpose"],
        normalized["provider"],
        normalized["model"],
        normalized["api_key"],
        normalized["base_url"],
    )
    fields = config_create_fields(payload, normalized, 1)
    stamp = now()
    with db() as conn:
        if bool(payload.get("isActive")):
            conn.execute("UPDATE user_configs SET is_active=0, updated_at=? WHERE user_id=? AND purpose=? AND deleted_at IS NULL", (stamp, user_id, fields["purpose"]))
            conn.execute("DELETE FROM user_official_config_defaults WHERE user_id=? AND purpose=?", (user_id, fields["purpose"]))
        cur = conn.execute(
            """INSERT INTO user_configs
            (created_at, updated_at, user_id, name, description, purpose, provider, base_url, model_name, encrypted_key, is_active, is_enabled, is_verified)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
            (
                stamp,
                stamp,
                user_id,
                fields["name"],
                fields["description"],
                fields["purpose"],
                fields["provider"],
                fields["base_url"],
                fields["model_name"],
                fields["encrypted_key"],
                fields["is_active"],
                fields["is_enabled"],
            ),
        )
        config = row(conn, "SELECT * FROM user_configs WHERE id=?", (cur.lastrowid,))
    return {"config": config_json(config)}


@router.patch("/keys/{config_id}")
async def update_config(config_id: int, payload: dict[str, Any], user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    with db() as conn:
        config = row(conn, "SELECT * FROM user_configs WHERE id=? AND user_id=? AND deleted_at IS NULL", (config_id, user_id))
    if not config:
        raise HTTPException(404, "config not found")

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

    stamp = now()
    with db() as conn:
        if payload.get("isActive"):
            conn.execute("UPDATE user_configs SET is_active=0, updated_at=? WHERE user_id=? AND purpose=? AND id<>? AND deleted_at IS NULL", (stamp, user_id, normalized["purpose"], config_id))
            conn.execute("DELETE FROM user_official_config_defaults WHERE user_id=? AND purpose=?", (user_id, normalized["purpose"]))
        conn.execute(
            f"UPDATE user_configs SET {', '.join(f'{key}=?' for key in updates)}, updated_at=? WHERE id=? AND user_id=?",
            (*updates.values(), stamp, config_id, user_id),
        )
        config = row(conn, "SELECT * FROM user_configs WHERE id=?", (config_id,))
    return {"config": config_json(config)}


@router.delete("/keys/{config_id}", status_code=204)
def delete_config(config_id: int, user_id: int = Depends(current_user_id)) -> None:
    with db() as conn:
        conn.execute("UPDATE user_configs SET deleted_at=?, updated_at=? WHERE id=? AND user_id=? AND deleted_at IS NULL", (now(), now(), config_id, user_id))


@router.post("/official/{config_id}/activate")
def activate_official_config(config_id: int, user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    stamp = now()
    with db() as conn:
        config = row(
            conn,
            "SELECT * FROM official_model_configs WHERE id=? AND is_enabled=1 AND is_verified=1 AND deleted_at IS NULL",
            (config_id,),
        )
        if not config:
            raise HTTPException(404, "official config not found")
        conn.execute(
            "UPDATE user_configs SET is_active=0, updated_at=? WHERE user_id=? AND purpose=? AND deleted_at IS NULL",
            (stamp, user_id, config["purpose"]),
        )
        conn.execute(
            """INSERT INTO user_official_config_defaults (user_id, purpose, official_config_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id, purpose) DO UPDATE SET official_config_id=excluded.official_config_id, updated_at=excluded.updated_at""",
            (user_id, config["purpose"], config_id, stamp, stamp),
        )
    return {"config": official_config_json(config, True)}


@router.delete("/official/{config_id}/activate", status_code=204)
def deactivate_official_config(config_id: int, user_id: int = Depends(current_user_id)) -> None:
    with db() as conn:
        conn.execute(
            "DELETE FROM user_official_config_defaults WHERE user_id=? AND official_config_id=?",
            (user_id, config_id),
        )
