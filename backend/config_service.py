from __future__ import annotations

import sqlite3
from urllib.parse import urlparse

from fastapi import HTTPException

from database import row
from model import pick_model
from model_registry import models
from security import decrypt


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
    if purpose not in {"script", "image", "video"}:
        raise HTTPException(400, "invalid purpose")
    if provider == "custom":
        if purpose != "script":
            raise HTTPException(400, "custom provider currently only supports script purpose")
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
        raise HTTPException(400, "script purpose requires modelSeries")


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
        "SELECT * FROM official_model_configs WHERE id=? AND purpose=? AND is_active=1 AND deleted_at IS NULL",
        (config_id, purpose),
    )
    return _model_config(config, purpose, stage, "official")


def active_model_config(conn: sqlite3.Connection, user_id: int, purpose: str, stage: str) -> dict[str, str]:
    config = row(
        conn,
        "SELECT * FROM user_configs WHERE user_id=? AND purpose=? AND is_active=1 AND deleted_at IS NULL ORDER BY updated_at DESC LIMIT 1",
        (user_id, purpose),
    )
    if config:
        return _model_config(config, purpose, stage, "user")
    config = row(
        conn,
        "SELECT * FROM official_model_configs WHERE purpose=? AND is_active=1 AND is_verified=1 AND deleted_at IS NULL ORDER BY updated_at DESC LIMIT 1",
        (purpose,),
    )
    return _model_config(config, purpose, stage, "official")
