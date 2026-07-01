from __future__ import annotations

import sqlite3

from fastapi import HTTPException

from database import row
from model import pick_model
from model_registry import models
from security import decrypt


def normalize_purpose(value: str) -> str:
    return (value or "script").strip().lower() or "script"


def normalize_provider(value: str) -> str:
    return (value or "").strip().lower()


def normalize_model(provider: str, value: str) -> str:
    value = (value or "").strip()
    return value.lower() if value and provider in {"qwen", "deepseek", "doubao", "openai"} else value


def validate_config_fields(purpose: str, provider: str, model: str) -> None:
    if purpose not in {"script", "image", "video"}:
        raise HTTPException(400, "invalid purpose")
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
    elif provider not in {"qwen", "deepseek", "doubao", "openai"}:
        raise HTTPException(400, "provider must be one of qwen/deepseek/doubao/openai")


async def validate_provider(purpose: str, provider: str, model: str, api_key: str) -> None:
    if not api_key.strip():
        raise HTTPException(400, "apiKey is required")
    if not 8 <= len(api_key) <= 512:
        raise HTTPException(400, "apiKey length must be between 8 and 512")
    if purpose == "video":
        return
    try:
        if purpose == "image":
            await models.validate_image_model(provider, api_key, model)
        else:
            await models.validate_chat_model(provider, api_key, model)
    except Exception as exc:
        raise HTTPException(400, f"model validation failed: {str(exc).strip()[:180]}") from exc


def active_model_config(conn: sqlite3.Connection, user_id: int, purpose: str, stage: str) -> dict[str, str]:
    config = row(
        conn,
        "SELECT * FROM user_configs WHERE user_id=? AND purpose=? AND is_active=1 AND deleted_at IS NULL ORDER BY updated_at DESC LIMIT 1",
        (user_id, purpose),
    )
    if not config:
        raise HTTPException(400, f"{stage}未配置可用的默认模型。请前往设置，为“{purpose}”完成校验并激活默认配置后重试。")
    provider = normalize_provider(config["provider"])
    model = pick_model(provider, normalize_model(provider, config["model_name"] or ""))
    validate_config_fields(purpose, provider, model)
    if not bool(config["is_verified"]):
        raise HTTPException(400, f"{stage}当前默认模型尚未通过校验。请前往设置重新验证并激活配置后重试。")
    api_key = decrypt(config["encrypted_key"]).strip()
    if not api_key:
        raise HTTPException(400, f"{stage}当前默认模型缺少 API Key。")
    return {"provider": provider, "model": model, "apiKey": api_key}
