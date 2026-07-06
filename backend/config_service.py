from __future__ import annotations

import sqlite3
from typing import Any
from urllib.parse import urlparse

from fastapi import HTTPException

from database import row
from model import pick_model
from model_registry import models
from security import decrypt, encrypt


CONFIG_VALIDATION_KEYS = ("apiKey", "provider", "baseUrl", "modelSeries", "model", "purpose")


def normalize_purpose(value: str) -> str:
    return (value or "script").strip().lower() or "script"


def normalize_provider(value: str) -> str:
    provider = (value or "").strip().lower()
    return {
        "chatgpt": "openai",
        "claude": "anthropic",
        "claude-code": "anthropic",
        "claude code": "anthropic",
    }.get(provider, provider)


def normalize_base_url(value: str) -> str:
    value = (value or "").strip().rstrip("/")
    if not value:
        return ""
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(400, "baseUrl must be a valid http(s) URL")
    return value


def normalize_model(provider: str, value: str) -> str:
    value = (value or "").strip()
    return value.lower() if value and provider in {"qwen", "deepseek", "doubao", "openai", "gemini", "anthropic"} else value


def validate_config_fields(purpose: str, provider: str, model: str, base_url: str = "") -> None:
    if purpose not in {"general", "script", "image", "video"}:
        raise HTTPException(400, "invalid purpose")
    if provider == "custom":
        if purpose not in {"general", "script"}:
            raise HTTPException(400, "custom provider currently only supports general/script purpose")
        if not model.strip():
            raise HTTPException(400, "custom provider requires modelSeries")
        if not base_url:
            raise HTTPException(400, "custom provider requires baseUrl")
        return
    if purpose == "video":
        if provider != "seedance2.0":
            raise HTTPException(400, "video purpose only supports provider seedance2.0")
        if not model.strip():
            raise HTTPException(400, "video purpose requires modelSeries")
    elif purpose == "image":
        if provider != "openai":
            raise HTTPException(400, "image purpose currently only supports provider openai")
        if not model.strip():
            raise HTTPException(400, "image purpose requires modelSeries")
    elif provider not in {"qwen", "deepseek", "doubao", "openai", "gemini", "anthropic"}:
        raise HTTPException(400, "provider must be one of qwen/deepseek/doubao/openai/gemini/anthropic/custom")
    elif not model.strip():
        raise HTTPException(400, "general/script purpose requires modelSeries")


def normalize_config_payload(payload: dict[str, Any], current: sqlite3.Row | None = None) -> dict[str, Any]:
    purpose = normalize_purpose(str(payload.get("purpose", current["purpose"] if current else "")))
    provider = normalize_provider(str(payload.get("provider", current["provider"] if current else "")))
    base_url = normalize_base_url(str(payload.get("baseUrl", (current["base_url"] or "") if current else "")))
    model_value = payload.get("modelSeries") or payload.get("model") or ((current["model_name"] or "") if current else "")
    model = normalize_model(provider, str(model_value))
    api_key = str(payload["apiKey"]).strip() if "apiKey" in payload else decrypt(current["encrypted_key"]) if current else str(payload.get("apiKey", "")).strip()
    validate_config_fields(purpose, provider, model, base_url)
    return {
        "purpose": purpose,
        "provider": provider,
        "base_url": base_url,
        "model": model,
        "api_key": api_key,
        "needs_validation": any(key in payload for key in CONFIG_VALIDATION_KEYS) or bool(payload.get("isActive")),
    }


def config_create_fields(payload: dict[str, Any], normalized: dict[str, Any], is_verified: int) -> dict[str, Any]:
    is_enabled = 1 if payload.get("isEnabled", True) else 0
    if payload.get("isActive") and not is_enabled:
        raise HTTPException(400, "disabled config cannot be default")
    return {
        "name": str(payload.get("name", "")).strip()[:64],
        "description": str(payload.get("description", "")).strip()[:255],
        "purpose": normalized["purpose"],
        "provider": normalized["provider"],
        "base_url": normalized["base_url"],
        "model_name": normalized["model"],
        "encrypted_key": encrypt(normalized["api_key"]),
        "is_active": 1 if payload.get("isActive") else 0,
        "is_enabled": is_enabled,
        "is_verified": is_verified,
    }


def config_update_fields(payload: dict[str, Any], current: sqlite3.Row, normalized: dict[str, Any]) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    if "name" in payload:
        updates["name"] = str(payload["name"]).strip()[:64]
    if "description" in payload:
        updates["description"] = str(payload["description"]).strip()[:255]
    if "purpose" in payload:
        updates["purpose"] = normalized["purpose"]
    if "provider" in payload:
        updates["provider"] = normalized["provider"]
    if "baseUrl" in payload:
        updates["base_url"] = normalized["base_url"]
    if any(key in payload for key in ("modelSeries", "model")):
        updates["model_name"] = normalized["model"]
    if "apiKey" in payload:
        updates["encrypted_key"] = encrypt(normalized["api_key"])
    if normalized["needs_validation"]:
        updates["is_verified"] = 1
    if "isActive" in payload:
        if payload["isActive"] and not bool(payload.get("isEnabled", current["is_enabled"])):
            raise HTTPException(400, "disabled config cannot be default")
        updates["is_active"] = 1 if payload["isActive"] else 0
    if "isEnabled" in payload:
        updates["is_enabled"] = 1 if payload["isEnabled"] else 0
        if not payload["isEnabled"]:
            updates["is_active"] = 0
    if not updates:
        raise HTTPException(400, "no fields to update")
    return updates


async def validate_provider(purpose: str, provider: str, model: str, api_key: str, base_url: str = "") -> None:
    if not api_key.strip():
        raise HTTPException(400, "apiKey is required")
    if not 8 <= len(api_key) <= 512:
        raise HTTPException(400, "apiKey length must be between 8 and 512")
    if purpose == "video":
        return
    try:
        if purpose == "image":
            await models.validate_image_model(provider, api_key, model, base_url)
        else:
            await models.validate_chat_model(provider, api_key, model, base_url)
    except Exception as exc:
        raise HTTPException(400, f"model validation failed: {str(exc).strip()[:180]}") from exc


def _model_config(config: sqlite3.Row, purpose: str, stage: str, source: str) -> dict[str, str]:
    if not config:
        raise HTTPException(400, f"{stage}未配置可用的默认模型。请先使用官方配置或添加自定义配置。")
    provider = normalize_provider(config["provider"])
    model = pick_model(provider, normalize_model(provider, config["model_name"] or ""))
    base_url = normalize_base_url(config["base_url"] or "")
    validate_config_fields(purpose, provider, model, base_url)
    if not bool(config["is_verified"]):
        raise HTTPException(400, f"{stage}当前默认模型尚未通过校验。")
    api_key = decrypt(config["encrypted_key"]).strip()
    if not api_key:
        raise HTTPException(400, f"{stage}当前默认模型缺少 API Key。")
    return {"provider": provider, "model": model, "apiKey": api_key, "baseUrl": base_url, "source": source}


def official_model_config(conn: sqlite3.Connection, config_id: int, purpose: str, stage: str) -> dict[str, str]:
    config = row(
        conn,
        "SELECT * FROM official_model_configs WHERE id=? AND purpose=? AND is_enabled=1 AND deleted_at IS NULL",
        (config_id, purpose),
    )
    return _model_config(config, purpose, stage, "official")


def active_model_config(conn: sqlite3.Connection, user_id: int, purpose: str, stage: str) -> dict[str, str]:
    config = row(
        conn,
        "SELECT * FROM user_configs WHERE user_id=? AND purpose=? AND is_active=1 AND is_enabled=1 AND deleted_at IS NULL ORDER BY updated_at DESC LIMIT 1",
        (user_id, purpose),
    )
    if config:
        return _model_config(config, purpose, stage, "user")
    config = row(
        conn,
        """SELECT official_model_configs.*
        FROM user_official_config_defaults
        JOIN official_model_configs ON official_model_configs.id=user_official_config_defaults.official_config_id
        WHERE user_official_config_defaults.user_id=?
          AND user_official_config_defaults.purpose=?
          AND official_model_configs.is_enabled=1
          AND official_model_configs.is_verified=1
          AND official_model_configs.deleted_at IS NULL
        LIMIT 1""",
        (user_id, purpose),
    )
    if config:
        return _model_config(config, purpose, stage, "official")
    config = row(
        conn,
        "SELECT * FROM official_model_configs WHERE purpose=? AND is_active=1 AND is_enabled=1 AND is_verified=1 AND deleted_at IS NULL ORDER BY updated_at DESC LIMIT 1",
        (purpose,),
    )
    return _model_config(config, purpose, stage, "official")
