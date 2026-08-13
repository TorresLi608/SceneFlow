from __future__ import annotations

import json
from ipaddress import ip_address
from typing import Any, Sequence
from urllib.parse import urlparse

from fastapi import HTTPException
from sqlmodel import Session, select

from app.core.security import decrypt, encrypt
from app.llms.router import pick_model
from app.models import ModelConfig, UserOfficialConfigDefault


VIDEO_QUALITIES = ("480p", "720p", "1080p")
VIDEO_FPS = (24, 30, 60)
VIDEO_RESOLUTIONS = ("1280x720", "720x1280", "1024x1024", "1920x1080")


def default_video_capabilities(provider: str, model: str = "") -> dict[str, Any]:
    if normalize_provider(provider) == "qwen":
        is_i2v = "-i2v" in model.lower()
        is_r2v = "-r2v" in model.lower()
        is_video_edit = "videoedit" in model.lower()
        return {
            "qualities": list(VIDEO_QUALITIES),
            "fps": [],
            "resolutions": [],
            "promptExtend": is_i2v,
            "minDuration": 2 if is_i2v else 3,
            "maxDuration": 15,
            "referenceImagesRequired": is_i2v or is_r2v,
            "maxReferenceImages": 5 if is_r2v else (1 if is_i2v or is_video_edit else 0),
            "referenceVideo": is_video_edit,
            "drivingAudio": is_i2v,
        }
    resolutions = [value for value in VIDEO_RESOLUTIONS if provider != "gemini" or value != "1024x1024"]
    return {
        "qualities": [],
        "fps": [24],
        "resolutions": resolutions,
        "promptExtend": False,
        "minDuration": 3,
        "maxDuration": 15,
        "referenceImagesRequired": False,
        "maxReferenceImages": 1,
        "referenceVideo": False,
        "drivingAudio": False,
    }


def normalize_video_capabilities(value: Any, provider: str, model: str = "") -> dict[str, Any]:
    if value is None:
        return default_video_capabilities(provider, model)
    if not isinstance(value, dict):
        raise HTTPException(400, "videoCapabilities must be an object")

    def choices(name: str, allowed: tuple[Any, ...]) -> list[Any]:
        selected = value.get(name, [])
        if not isinstance(selected, list) or any(item not in allowed for item in selected):
            raise HTTPException(400, f"videoCapabilities.{name} contains an unsupported value")
        return [item for item in allowed if item in selected]

    try:
        minimum = int(value.get("minDuration", 3))
        maximum = int(value.get("maxDuration", 15))
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, "video duration limits must be integers") from exc
    if isinstance(value.get("minDuration"), bool) or isinstance(value.get("maxDuration"), bool) or not 1 <= minimum <= maximum <= 60:
        raise HTTPException(400, "video duration limits must satisfy 1 <= minDuration <= maxDuration <= 60")
    prompt_extend = value.get("promptExtend", False)
    if not isinstance(prompt_extend, bool):
        raise HTTPException(400, "videoCapabilities.promptExtend must be boolean")
    try:
        max_reference_images = int(value.get("maxReferenceImages", 0))
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, "videoCapabilities.maxReferenceImages must be an integer") from exc
    if isinstance(value.get("maxReferenceImages"), bool) or not 0 <= max_reference_images <= 9:
        raise HTTPException(400, "videoCapabilities.maxReferenceImages must be between 0 and 9")
    required = value.get("referenceImagesRequired", False)
    reference_video = value.get("referenceVideo", False)
    driving_audio = value.get("drivingAudio", False)
    if not all(isinstance(item, bool) for item in (required, reference_video, driving_audio)):
        raise HTTPException(400, "video input capability flags must be boolean")
    if required and max_reference_images == 0:
        raise HTTPException(400, "required reference images need maxReferenceImages greater than 0")
    return {
        "qualities": choices("qualities", VIDEO_QUALITIES),
        "fps": choices("fps", VIDEO_FPS),
        "resolutions": choices("resolutions", VIDEO_RESOLUTIONS),
        "promptExtend": prompt_extend,
        "minDuration": minimum,
        "maxDuration": maximum,
        "referenceImagesRequired": required,
        "maxReferenceImages": max_reference_images,
        "referenceVideo": reference_video,
        "drivingAudio": driving_audio,
    }


def video_capabilities(config: ModelConfig) -> dict[str, Any]:
    if config.video_capabilities_json:
        try:
            return normalize_video_capabilities(json.loads(config.video_capabilities_json), config.provider, config.model_name or "")
        except (TypeError, ValueError, HTTPException):
            pass
    return default_video_capabilities(config.provider, config.model_name or "")


def normalize_purpose(value: str) -> str:
    return (value or "script").strip().lower() or "script"


def config_api_key(config: ModelConfig) -> str:
    try:
        return decrypt(config.encrypted_key)
    except Exception as exc:
        raise HTTPException(400, "stored API key cannot be decrypted") from exc


def normalize_provider(value: str) -> str:
    provider = (value or "").strip().lower()
    return {
        "chatgpt": "openai",
        "claude": "anthropic",
        "claude-code": "anthropic",
        "claude code": "anthropic",
        "seedance2.0": "doubao",
        "seedance-2.0": "doubao",
    }.get(provider, provider)


def normalize_base_url(value: str) -> str:
    value = (value or "").strip().rstrip("/")
    if not value:
        return ""
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise HTTPException(400, "baseUrl must be a valid http(s) URL")
    hostname = (parsed.hostname or "").lower()
    if hostname == "localhost" or hostname.endswith(".localhost"):
        raise HTTPException(400, "baseUrl must not target a private network")
    try:
        address = ip_address(hostname)
    except ValueError:
        pass
    else:
        if not address.is_global:
            raise HTTPException(400, "baseUrl must not target a private network")
    return value


def normalize_model(provider: str, value: str) -> str:
    value = (value or "").strip()
    return value.lower() if value and provider in {"deepseek", "doubao", "openai", "gemini", "anthropic"} else value


def validate_config_fields(purpose: str, provider: str, model: str, base_url: str = "") -> None:
    if purpose not in {"general", "script", "image", "video", "audio"}:
        raise HTTPException(400, "invalid purpose")
    if purpose == "audio":
        if provider not in {"edge", "system", "openai", "qwen"}:
            raise HTTPException(400, "audio purpose only supports provider edge/system/openai/qwen")
        if not model.strip():
            raise HTTPException(400, "audio purpose requires a voice or modelSeries")
        if provider == "qwen" and ":" not in model:
            raise HTTPException(400, "Qwen audio modelSeries must use model:voice")
        return
    if provider == "custom":
        if purpose not in {"general", "script"}:
            raise HTTPException(400, "custom provider currently only supports general/script purpose")
        if not model.strip():
            raise HTTPException(400, "custom provider requires modelSeries")
        if not base_url:
            raise HTTPException(400, "custom provider requires baseUrl")
        return
    if purpose == "video":
        if provider not in {"doubao", "gemini", "qwen"}:
            raise HTTPException(400, "video purpose only supports provider doubao/gemini/qwen")
        if not model.strip():
            raise HTTPException(400, "video purpose requires modelSeries")
    elif purpose == "image":
        if provider not in {"openai", "gemini", "qwen"}:
            raise HTTPException(400, "image purpose currently only supports provider openai/gemini/qwen")
        if not model.strip():
            raise HTTPException(400, "image purpose requires modelSeries")
    elif provider not in {"qwen", "deepseek", "doubao", "openai", "gemini", "anthropic"}:
        raise HTTPException(400, "provider must be one of qwen/deepseek/doubao/openai/gemini/anthropic/custom")
    elif not model.strip():
        raise HTTPException(400, "general/script purpose requires modelSeries")


def normalize_config_payload(payload: dict[str, Any], current: ModelConfig | None = None) -> dict[str, Any]:
    current_api_key = decrypt(current.encrypted_key) if current else ""
    purpose = normalize_purpose(str(payload.get("purpose", current.purpose if current else "")))
    provider = normalize_provider(str(payload.get("provider", current.provider if current else "")))
    base_url = normalize_base_url(str(payload.get("baseUrl", (current.base_url or "") if current else "")))
    model_value = payload.get("modelSeries") or payload.get("model") or ((current.model_name or "") if current else "")
    model = normalize_model(provider, str(model_value))
    if "apiKey" in payload:
        api_key = str(payload["apiKey"]).strip()
    elif current:
        api_key = current_api_key
    else:
        api_key = str(payload.get("apiKey", "")).strip()
    validate_config_fields(purpose, provider, model, base_url)
    capabilities = None
    if purpose == "video":
        existing_capabilities = (
            video_capabilities(current)
            if current and purpose == current.purpose and provider == normalize_provider(current.provider) and model == (current.model_name or "")
            else None
        )
        capabilities = normalize_video_capabilities(
            payload.get("videoCapabilities") if "videoCapabilities" in payload else existing_capabilities,
            provider,
            model,
        )
    return {
        "purpose": purpose,
        "provider": provider,
        "base_url": base_url,
        "model": model,
        "api_key": api_key,
        "video_capabilities": capabilities,
    }


def config_create_fields(payload: dict[str, Any], normalized: dict[str, Any]) -> dict[str, Any]:
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
        "video_capabilities_json": json.dumps(normalized["video_capabilities"], separators=(",", ":")) if normalized["video_capabilities"] else None,
    }


def config_update_fields(payload: dict[str, Any], current: ModelConfig, normalized: dict[str, Any]) -> dict[str, Any]:
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
    if "isActive" in payload:
        if payload["isActive"] and not bool(payload.get("isEnabled", current.is_enabled)):
            raise HTTPException(400, "disabled config cannot be default")
        updates["is_active"] = 1 if payload["isActive"] else 0
    if "isEnabled" in payload:
        updates["is_enabled"] = 1 if payload["isEnabled"] else 0
        if not payload["isEnabled"]:
            updates["is_active"] = 0
    if (
        "videoCapabilities" in payload
        or ("purpose" in payload and normalized["purpose"] != current.purpose)
        or ("provider" in payload and normalized["provider"] != normalize_provider(current.provider))
        or (any(key in payload for key in ("modelSeries", "model")) and normalized["model"] != (current.model_name or ""))
    ):
        updates["video_capabilities_json"] = (
            json.dumps(normalized["video_capabilities"], separators=(",", ":")) if normalized["video_capabilities"] else None
        )
    return updates


def validate_api_key(provider: str, api_key: str) -> None:
    if provider in {"edge", "system"}:
        return
    if not api_key.strip():
        raise HTTPException(400, "apiKey is required")
    if not 8 <= len(api_key) <= 512:
        raise HTTPException(400, "apiKey length must be between 8 and 512")


def _model_config(config: ModelConfig | None, purpose: str, stage: str, source: str) -> dict[str, Any]:
    if not config:
        raise HTTPException(400, f"{stage}未配置可用的默认模型。请先使用官方配置或添加自定义配置。")
    provider = normalize_provider(config.provider)
    model = pick_model(provider, normalize_model(provider, config.model_name or ""))
    base_url = normalize_base_url(config.base_url or "")
    validate_config_fields(purpose, provider, model, base_url)
    api_key = decrypt(config.encrypted_key).strip()
    if not api_key and provider not in {"edge", "system"}:
        raise HTTPException(400, f"{stage}当前默认模型缺少 API Key。")
    return {
        "provider": provider,
        "model": model,
        "apiKey": api_key,
        "baseUrl": base_url,
        "source": source,
        "configId": config.id if source == "user" else None,
        "officialConfigId": config.id if source == "official" else None,
        "videoCapabilities": video_capabilities(config) if purpose == "video" else None,
    }


def official_model_config(session: Session, config_id: int, purpose: str, stage: str) -> dict[str, str]:
    config = session.exec(
        select(ModelConfig).where(
            ModelConfig.id == config_id,
            ModelConfig.source == "official",
            ModelConfig.purpose == purpose,
            ModelConfig.is_enabled.is_(True),
            ModelConfig.deleted_at.is_(None),
        )
    ).first()
    return _model_config(config, purpose, stage, "official")


def user_model_config(session: Session, user_id: int, config_id: int, purpose: str, stage: str) -> dict[str, str]:
    config = session.exec(
        select(ModelConfig).where(
            ModelConfig.id == config_id,
            ModelConfig.source == "user",
            ModelConfig.user_id == user_id,
            ModelConfig.purpose == purpose,
            ModelConfig.is_enabled.is_(True),
            ModelConfig.deleted_at.is_(None),
        )
    ).first()
    return _model_config(config, purpose, stage, "user")


def official_model_config_any(session: Session, config_id: int, purposes: Sequence[str], stage: str) -> dict[str, str]:
    config = session.exec(
        select(ModelConfig).where(
            ModelConfig.id == config_id,
            ModelConfig.source == "official",
            ModelConfig.purpose.in_(purposes),
            ModelConfig.is_enabled.is_(True),
            ModelConfig.deleted_at.is_(None),
        )
    ).first()
    return _model_config(config, config.purpose if config else "", stage, "official")


def user_model_config_any(session: Session, user_id: int, config_id: int, purposes: Sequence[str], stage: str) -> dict[str, str]:
    config = session.exec(
        select(ModelConfig).where(
            ModelConfig.id == config_id,
            ModelConfig.source == "user",
            ModelConfig.user_id == user_id,
            ModelConfig.purpose.in_(purposes),
            ModelConfig.is_enabled.is_(True),
            ModelConfig.deleted_at.is_(None),
        )
    ).first()
    return _model_config(config, config.purpose if config else "", stage, "user")


def active_model_config(session: Session, user_id: int, purpose: str, stage: str) -> dict[str, str]:
    # Precedence: the user's explicit official default overrides their own active config, which in
    # turn overrides the system-wide official default. Because picking an official default no longer
    # clears `is_active`, dropping the override restores whatever personal config was active before.
    config = session.exec(
        select(ModelConfig)
        .join(UserOfficialConfigDefault, UserOfficialConfigDefault.official_config_id == ModelConfig.id)
        .where(
            UserOfficialConfigDefault.user_id == user_id,
            UserOfficialConfigDefault.purpose == purpose,
            ModelConfig.source == "official",
            ModelConfig.is_enabled.is_(True),
            ModelConfig.deleted_at.is_(None),
        )
        .limit(1)
    ).first()
    if config:
        return _model_config(config, purpose, stage, "official")
    config = session.exec(
        select(ModelConfig)
        .where(
            ModelConfig.source == "user",
            ModelConfig.user_id == user_id,
            ModelConfig.purpose == purpose,
            ModelConfig.is_active.is_(True),
            ModelConfig.is_enabled.is_(True),
            ModelConfig.deleted_at.is_(None),
        )
        .order_by(ModelConfig.updated_at.desc())
        .limit(1)
    ).first()
    if config:
        return _model_config(config, purpose, stage, "user")
    config = session.exec(
        select(ModelConfig)
        .where(
            ModelConfig.source == "official",
            ModelConfig.purpose == purpose,
            ModelConfig.is_active.is_(True),
            ModelConfig.is_enabled.is_(True),
            ModelConfig.deleted_at.is_(None),
        )
        .order_by(ModelConfig.updated_at.desc())
        .limit(1)
    ).first()
    return _model_config(config, purpose, stage, "official")
