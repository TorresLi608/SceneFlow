from __future__ import annotations

import json
from ipaddress import ip_address
from typing import Any, Sequence
from urllib.parse import urlparse

from fastapi import HTTPException
from sqlalchemy import and_, or_
from sqlmodel import Session, select

from app.core.security import decrypt, encrypt
from app.llms.router import pick_model
from app.models import ModelConfig, Project, UserOfficialConfigDefault


VIDEO_QUALITIES = ("480p", "720p", "1080p", "2K", "4K")
VIDEO_FPS = (24, 30, 60)
VIDEO_ASPECT_RATIOS = ("21:9", "16:9", "4:3", "1:1", "3:4", "9:16", "adaptive")

# How a model is asked for sound. `with_audio` / `audio` make the model generate a track;
# `reference_voice` only feeds it a timbre to imitate, which is why that one needs the
# project's merged voice sheet and the other two do not.
AUDIO_PARAMS = ("with_audio", "audio", "reference_voice")

# Kept in code: these are provider contract facts, not user data. Admins may still
# override the normalized capability JSON for relay/model revisions. `catalog` marks the
# entries the admin picker offers — superseded revisions stay here so an existing config
# pinned to one still resolves its capabilities.
VIDEO_MODEL_CAPABILITIES: dict[str, dict[str, Any]] = {
    "doubao-seedance-2.0": {"provider": "doubao", "catalog": True, "qualities": ["720p", "1080p"], "aspectRatios": ["16:9", "9:16", "1:1", "4:3", "3:4", "21:9"], "minDuration": 2, "maxDuration": 12, "maxReferenceImages": 4, "audioParam": "with_audio", "audioDefault": True},
    "doubao-seedance-2.0-fast": {"provider": "doubao", "catalog": True, "qualities": ["720p", "1080p"], "aspectRatios": ["16:9", "9:16", "1:1", "4:3", "3:4", "21:9"], "minDuration": 2, "maxDuration": 12, "maxReferenceImages": 4, "audioParam": "with_audio", "audioDefault": True},
    "doubao-seedance-2.0-mini": {"provider": "doubao", "catalog": True, "qualities": ["720p"], "aspectRatios": ["16:9", "9:16", "1:1", "4:3", "3:4"], "minDuration": 2, "maxDuration": 10, "maxReferenceImages": 4, "audioParam": "with_audio", "audioDefault": True},
    "doubao-seedance-2.5": {"provider": "doubao", "catalog": True, "qualities": ["720p", "1080p"], "aspectRatios": ["16:9", "9:16", "1:1", "4:3", "3:4", "21:9"], "minDuration": 2, "maxDuration": 12, "maxReferenceImages": 5, "audioParam": "with_audio", "audioDefault": True},
    "wan2.7": {"provider": "qwen", "catalog": False, "qualities": ["720p", "1080p"], "aspectRatios": ["16:9", "9:16", "1:1", "4:3", "3:4"], "minDuration": 2, "maxDuration": 15, "maxReferenceImages": 5, "maxReferenceVideos": 1, "maxReferenceAudios": 1, "audioParam": "reference_voice", "audioDefault": False},
    "wan2.7-r2v": {"provider": "qwen", "catalog": True, "qualities": ["720p", "1080p"], "aspectRatios": ["16:9", "9:16", "1:1", "4:3", "3:4"], "minDuration": 2, "maxDuration": 15, "maxReferenceImages": 5, "maxReferenceVideos": 1, "maxReferenceAudios": 1, "audioParam": "reference_voice", "audioDefault": False},
    "wan2.7-r2v-2026-06-12": {"provider": "qwen", "catalog": False, "qualities": ["720p", "1080p"], "aspectRatios": ["16:9", "9:16", "1:1", "4:3", "3:4"], "minDuration": 2, "maxDuration": 15, "maxReferenceImages": 5, "maxReferenceVideos": 1, "maxReferenceAudios": 1, "audioParam": "reference_voice", "audioDefault": False},
    "wan3.0-video": {"provider": "qwen", "catalog": True, "qualities": ["480p", "720p", "1080p"], "aspectRatios": ["adaptive", "16:9", "4:3", "1:1", "3:4", "9:16"], "minDuration": 2, "maxDuration": 30, "maxReferenceImages": 10, "maxReferenceVideos": 5, "maxReferenceAudios": 5, "audioParam": "audio", "audioDefault": True},
    "wan3.0-video-prime": {"provider": "qwen", "catalog": True, "qualities": ["480p", "720p", "1080p"], "aspectRatios": ["adaptive", "16:9", "4:3", "1:1", "3:4", "9:16"], "minDuration": 2, "maxDuration": 30, "maxReferenceImages": 10, "maxReferenceVideos": 5, "maxReferenceAudios": 5, "audioParam": "audio", "audioDefault": True},
}


def default_video_capabilities(provider: str, model: str = "") -> dict[str, Any]:
    known = VIDEO_MODEL_CAPABILITIES.get(model.strip().lower())
    if known:
        return {
            "qualities": list(known["qualities"]), "fps": [], "aspectRatios": list(known["aspectRatios"]),
            "promptExtend": True, "minDuration": known["minDuration"], "maxDuration": known["maxDuration"],
            "referenceImages": known.get("maxReferenceImages", 0) > 0, "referenceImagesRequired": False,
            "maxReferenceImages": known.get("maxReferenceImages", 0), "referenceVideo": known.get("maxReferenceVideos", 0) > 0,
            "maxReferenceVideos": known.get("maxReferenceVideos", 0), "referenceVideosRequired": False,
            "referenceAudio": known.get("maxReferenceAudios", 0) > 0, "maxReferenceAudios": known.get("maxReferenceAudios", 0),
            "referenceAudiosRequired": False, "audioParam": known.get("audioParam"), "audioDefault": known.get("audioDefault", True),
        }
    if normalize_provider(provider) == "qwen":
        is_i2v = "-i2v" in model.lower()
        is_r2v = "-r2v" in model.lower()
        is_video_edit = "videoedit" in model.lower()
        return {
            "qualities": list(VIDEO_QUALITIES),
            "fps": [],
            "aspectRatios": list(VIDEO_ASPECT_RATIOS),
            "promptExtend": is_i2v,
            "minDuration": 2 if is_i2v else 3,
            "maxDuration": 15,
            "referenceImages": is_i2v or is_r2v,
            "referenceImagesRequired": is_i2v or is_r2v,
            "maxReferenceImages": 5 if is_r2v else (1 if is_i2v or is_video_edit else 0),
            "referenceVideo": is_video_edit,
            "maxReferenceVideos": 1 if is_video_edit else 0,
            "referenceVideosRequired": False,
            "referenceAudio": is_i2v,
            "maxReferenceAudios": 1 if is_i2v else 0,
            "referenceAudiosRequired": False,
            # Legacy i2v took a driving track but never generated one, so the switch stays
            # off unless the user asks: defaulting it on would demand a voice sheet from
            # every series that predates the audio panel.
            "audioParam": "reference_voice" if is_i2v else None,
            "audioDefault": False,
        }
    return {
        "qualities": list(VIDEO_QUALITIES),
        "fps": [24],
        "aspectRatios": [value for value in VIDEO_ASPECT_RATIOS if provider != "gemini" or value != "1:1"],
        "promptExtend": False,
        "minDuration": 3,
        "maxDuration": 15,
        "referenceImages": False,
        "referenceImagesRequired": False,
        "maxReferenceImages": 0,
        "referenceVideo": False,
        "maxReferenceVideos": 0,
        "referenceVideosRequired": False,
        "referenceAudio": False,
        "maxReferenceAudios": 0,
        "referenceAudiosRequired": False,
        "audioParam": None,
        "audioDefault": False,
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
    def limit(name: str, supported: bool, maximum: int | None = 9) -> int:
        try:
            result = int(value.get(name, 0))
        except (TypeError, ValueError) as exc:
            raise HTTPException(400, f"videoCapabilities.{name} must be an integer") from exc
        if isinstance(value.get(name), bool) or result < 0 or (maximum is not None and result > maximum):
            if maximum is None:
                raise HTTPException(400, f"videoCapabilities.{name} must be 0 or greater")
            raise HTTPException(400, f"videoCapabilities.{name} must be between 0 and {maximum}")
        if supported and result == 0:
            raise HTTPException(400, f"videoCapabilities.{name} must be greater than 0 when supported")
        return result if supported else 0

    def flag(name: str, default: bool = False) -> bool:
        result = value.get(name, default)
        if not isinstance(result, bool):
            raise HTTPException(400, f"videoCapabilities.{name} must be boolean")
        return result

    reference_images = flag("referenceImages", bool(value.get("maxReferenceImages", 0)))
    max_reference_images = limit("maxReferenceImages", reference_images, None)
    reference_images_required = flag("referenceImagesRequired")
    reference_video = flag("referenceVideo")
    legacy_reference_audio = flag("drivingAudio") if "referenceAudio" not in value else False
    value = {
        **value,
        "maxReferenceVideos": value.get("maxReferenceVideos", 1 if reference_video else 0),
        "maxReferenceAudios": value.get("maxReferenceAudios", 1 if legacy_reference_audio else 0),
    }
    max_reference_videos = limit("maxReferenceVideos", reference_video)
    reference_videos_required = flag("referenceVideosRequired")
    reference_audio = flag("referenceAudio", legacy_reference_audio)
    max_reference_audios = limit("maxReferenceAudios", reference_audio)
    reference_audios_required = flag("referenceAudiosRequired")
    if reference_images_required and not reference_images:
        raise HTTPException(400, "required reference images need referenceImages enabled")
    if reference_images_required and max_reference_images == 0:
        raise HTTPException(400, "required reference images need maxReferenceImages greater than 0")
    if reference_videos_required and not reference_video:
        raise HTTPException(400, "required reference videos need referenceVideo enabled")
    if reference_videos_required and max_reference_videos == 0:
        raise HTTPException(400, "required reference videos need maxReferenceVideos greater than 0")
    if reference_audios_required and not reference_audio:
        raise HTTPException(400, "required reference audios need referenceAudio enabled")
    if reference_audios_required and max_reference_audios == 0:
        raise HTTPException(400, "required reference audios need maxReferenceAudios greater than 0")
    raw_aspect_ratios = value.get("aspectRatios")
    if raw_aspect_ratios is None and isinstance(value.get("resolutions"), list):
        aspect_by_resolution = {
            "1280x720": "16:9",
            "720x1280": "9:16",
            "1024x1024": "1:1",
            "1920x1080": "16:9",
        }
        raw_aspect_ratios = [aspect_by_resolution[item] for item in value["resolutions"] if item in aspect_by_resolution]
    if raw_aspect_ratios is None:
        normalized_aspect_ratios = choices("aspectRatios", VIDEO_ASPECT_RATIOS)
    elif not isinstance(raw_aspect_ratios, list) or any(item not in VIDEO_ASPECT_RATIOS for item in raw_aspect_ratios):
        raise HTTPException(400, "videoCapabilities.aspectRatios contains an unsupported value")
    else:
        normalized_aspect_ratios = [item for item in VIDEO_ASPECT_RATIOS if item in raw_aspect_ratios]
    # Audio defaults come from the model catalog rather than the stored JSON: configs saved
    # before the audio switch existed have no such keys, and falling back to the catalog is
    # what lets an existing seedance config pick up `with_audio` without being re-saved.
    catalog = default_video_capabilities(provider, model)
    audio_param = catalog.get("audioParam")
    if "audioParam" in value:
        audio_param = value["audioParam"] if value["audioParam"] in AUDIO_PARAMS else None
    return {
        "qualities": choices("qualities", VIDEO_QUALITIES),
        "fps": choices("fps", VIDEO_FPS),
        "aspectRatios": normalized_aspect_ratios,
        "promptExtend": prompt_extend,
        "minDuration": minimum,
        "maxDuration": maximum,
        "referenceImages": reference_images,
        "referenceImagesRequired": reference_images_required,
        "maxReferenceImages": max_reference_images,
        "referenceVideo": reference_video,
        "maxReferenceVideos": max_reference_videos,
        "referenceVideosRequired": reference_videos_required,
        "referenceAudio": reference_audio,
        "maxReferenceAudios": max_reference_audios,
        "referenceAudiosRequired": reference_audios_required,
        "audioParam": audio_param,
        "audioDefault": flag("audioDefault", bool(catalog.get("audioDefault"))) if audio_param else False,
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
        if provider != "qwen":
            raise HTTPException(400, "audio purpose only supports provider qwen")
        if not model.strip():
            raise HTTPException(400, "audio purpose requires modelSeries")
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
    raw_image_limit = payload.get(
        "imageMaxReferenceImages",
        current.image_max_reference_images if current and current.image_max_reference_images is not None else 4,
    )
    try:
        image_max_reference_images = int(raw_image_limit)
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, "imageMaxReferenceImages must be an integer") from exc
    if isinstance(raw_image_limit, bool) or image_max_reference_images < 0:
        raise HTTPException(400, "imageMaxReferenceImages must be 0 or greater")
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
        "image_max_reference_images": image_max_reference_images,
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
        "image_max_reference_images": normalized["image_max_reference_images"],
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
    if "imageMaxReferenceImages" in payload or ("purpose" in payload and normalized["purpose"] != current.purpose):
        updates["image_max_reference_images"] = normalized["image_max_reference_images"]
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
        "imageMaxReferenceImages": config.image_max_reference_images if config.image_max_reference_images is not None else 4,
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


# Which column on `projects` holds the pick for each kind of work. The keys are the
# `purpose` values the rest of the codebase already speaks, so callers never translate.
PROJECT_CONFIG_COLUMNS = {
    "script": "text_config_id",
    "image": "image_config_id",
    "video": "video_config_id",
    "audio": "audio_config_id",
}


def project_config_id(project: Project | None, purpose: str) -> int | None:
    """The config this project pinned for `purpose`, or None when it follows the account."""
    column = PROJECT_CONFIG_COLUMNS.get(purpose)
    if not column or project is None:
        return None
    # 0 is how a client clears the pick — `null` in a PATCH means "leave alone", so the
    # clear has to be a real value. Treat it the same as never having been set.
    return getattr(project, column, None) or None


def project_model_config(
    session: Session,
    user_id: int,
    project: Project | None,
    purpose: str,
    stage: str,
) -> dict[str, Any]:
    """The model this project uses for `purpose`, falling back to the account's default.

    Project-first rather than project-only: a series created before the model panel
    existed has every pick unset, and demanding one before it can render would strand it.
    A pick that no longer resolves — the config was deleted, disabled, or belongs to
    someone else — falls back the same way, so losing a config degrades to the account
    default instead of failing the render.
    """
    config_id = project_config_id(project, purpose)
    if config_id:
        config = session.exec(
            select(ModelConfig).where(
                ModelConfig.id == config_id,
                ModelConfig.purpose == purpose,
                ModelConfig.is_enabled.is_(True),
                ModelConfig.deleted_at.is_(None),
                or_(
                    ModelConfig.source == "official",
                    and_(ModelConfig.source == "user", ModelConfig.user_id == user_id),
                ),
            )
        ).first()
        if config:
            resolved = _model_config(config, purpose, stage, config.source or "user")
            resolved["isProjectPick"] = True
            return resolved
    resolved = active_model_config(session, user_id, purpose, stage)
    resolved["isProjectPick"] = False
    return resolved
