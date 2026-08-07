from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.core.database import db, row, rows
from app.api.deps import current_user_id
from app.schemas.serializers import config_json, official_config_json
from app.services.config_service import config_api_key, config_create_fields, config_update_fields, normalize_base_url, normalize_config_payload, normalize_provider, validate_api_key, validate_provider
from app.llms.registry import models
from app.services.usage_service import normalize_pricing, pricing_snapshot, pricing_updates
from app.utils.common import now


router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/keys")
def list_configs(user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    with db() as conn:
        configs = rows(conn, "SELECT * FROM model_configs WHERE source='user' AND user_id=? AND deleted_at IS NULL ORDER BY updated_at DESC", (user_id,))
        active_user_purposes = {config["purpose"] for config in configs if config["is_active"] and config["is_enabled"]}
        active_official = {
            config["purpose"]: config["official_config_id"]
            for config in rows(conn, "SELECT purpose, official_config_id FROM user_official_config_defaults WHERE user_id=?", (user_id,))
        }
        official_configs = rows(
            conn,
            "SELECT * FROM model_configs WHERE source='official' AND is_enabled=1 AND is_verified=1 AND deleted_at IS NULL ORDER BY purpose, updated_at DESC",
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


@router.post("/models")
async def discover_models(payload: dict[str, Any], _: int = Depends(current_user_id)) -> dict[str, list[str]]:
    provider = normalize_provider(str(payload.get("provider", "")))
    base_url = normalize_base_url(str(payload.get("baseUrl", "")))
    api_key = str(payload.get("apiKey", "")).strip()
    if provider not in {"qwen", "deepseek", "doubao", "openai", "gemini", "anthropic", "custom"}:
        raise HTTPException(400, "provider does not support model discovery")
    if provider == "custom" and not base_url:
        raise HTTPException(400, "custom provider requires baseUrl")
    if not 8 <= len(api_key) <= 512:
        raise HTTPException(400, "apiKey length must be between 8 and 512")
    try:
        model_names = await models.list_models(provider, api_key, base_url)
    except Exception as exc:
        raise HTTPException(400, f"failed to fetch model list: {str(exc).strip()[:180]}") from exc
    if not model_names:
        raise HTTPException(400, "provider returned no models")
    return {"models": model_names}


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
        config = row(conn, "SELECT * FROM model_configs WHERE id=? AND source='user' AND user_id=? AND deleted_at IS NULL", (config_id, user_id))
    if not config:
        raise HTTPException(404, "config not found")
    return {"config": config_json(config)}


@router.post("/keys/{config_id}/secret")
def get_config_secret(config_id: int, user_id: int = Depends(current_user_id)) -> dict[str, str]:
    with db() as conn:
        config = row(conn, "SELECT encrypted_key FROM model_configs WHERE id=? AND source='user' AND user_id=? AND deleted_at IS NULL", (config_id, user_id))
    if not config:
        raise HTTPException(404, "config not found")
    return {"apiKey": config_api_key(config)}


@router.post("/keys", status_code=201)
async def create_config(payload: dict[str, Any], user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    normalized = normalize_config_payload(payload)
    validate_api_key(normalized["provider"], normalized["api_key"])
    fields = config_create_fields(payload, normalized, 1)
    try:
        pricing = normalize_pricing(payload)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    stamp = now()
    with db() as conn:
        if bool(payload.get("isActive")):
            conn.execute("UPDATE model_configs SET is_active=0, updated_at=? WHERE source='user' AND user_id=? AND purpose=? AND deleted_at IS NULL", (stamp, user_id, fields["purpose"]))
            conn.execute("DELETE FROM user_official_config_defaults WHERE user_id=? AND purpose=?", (user_id, fields["purpose"]))
        cur = conn.execute(
            """INSERT INTO model_configs
            (created_at, updated_at, user_id, source, name, description, purpose, provider, base_url, model_name, encrypted_key, is_active, is_enabled, is_verified,
             pricing_multiplier, input_price_per_million, output_price_per_million, cache_read_price_per_million,
             cache_write_price_per_million, unit_price, unit_name, pricing_json)
            VALUES (?, ?, ?, 'user', ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
                pricing["pricing_multiplier"],
                pricing["input_price_per_million"],
                pricing["output_price_per_million"],
                pricing["cache_read_price_per_million"],
                pricing["cache_write_price_per_million"],
                pricing["unit_price"],
                pricing["unit_name"],
                pricing_snapshot(pricing),
            ),
        )
        config = row(conn, "SELECT * FROM model_configs WHERE id=?", (cur.lastrowid,))
    return {"config": config_json(config)}


@router.patch("/keys/{config_id}")
async def update_config(config_id: int, payload: dict[str, Any], user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    with db() as conn:
        config = row(conn, "SELECT * FROM model_configs WHERE id=? AND source='user' AND user_id=? AND deleted_at IS NULL", (config_id, user_id))
    if not config:
        raise HTTPException(404, "config not found")

    normalized = normalize_config_payload(payload, config)
    if normalized["needs_validation"]:
        validate_api_key(normalized["provider"], normalized["api_key"])
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
            conn.execute("UPDATE model_configs SET is_active=0, updated_at=? WHERE source='user' AND user_id=? AND purpose=? AND id<>? AND deleted_at IS NULL", (stamp, user_id, normalized["purpose"], config_id))
            conn.execute("DELETE FROM user_official_config_defaults WHERE user_id=? AND purpose=?", (user_id, normalized["purpose"]))
        conn.execute(
            f"UPDATE model_configs SET {', '.join(f'{key}=?' for key in updates)}, updated_at=? WHERE id=? AND source='user' AND user_id=?",
            (*updates.values(), stamp, config_id, user_id),
        )
        config = row(conn, "SELECT * FROM model_configs WHERE id=?", (config_id,))
    return {"config": config_json(config)}


@router.delete("/keys/{config_id}", status_code=204)
def delete_config(config_id: int, user_id: int = Depends(current_user_id)) -> None:
    with db() as conn:
        conn.execute("UPDATE model_configs SET deleted_at=?, updated_at=? WHERE id=? AND source='user' AND user_id=? AND deleted_at IS NULL", (now(), now(), config_id, user_id))


@router.post("/official/{config_id}/activate")
def activate_official_config(config_id: int, user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    stamp = now()
    with db() as conn:
        config = row(
            conn,
            "SELECT * FROM model_configs WHERE id=? AND source='official' AND is_enabled=1 AND is_verified=1 AND deleted_at IS NULL",
            (config_id,),
        )
        if not config:
            raise HTTPException(404, "official config not found")
        conn.execute(
            "UPDATE model_configs SET is_active=0, updated_at=? WHERE source='user' AND user_id=? AND purpose=? AND deleted_at IS NULL",
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
