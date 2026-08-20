from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlmodel import select

from app.core.database import db
from app.api.deps import current_user_id
from app.models import ModelConfig, UserOfficialConfigDefault
from app.schemas.serializers import config_json, official_config_json
from app.services.config_service import config_api_key, config_create_fields, config_update_fields, normalize_base_url, normalize_config_payload, normalize_provider, validate_api_key
from app.llms.registry import models
from app.services.usage_service import normalize_pricing, pricing_snapshot, pricing_updates
from app.utils.common import now


router = APIRouter(prefix="/api/settings", tags=["settings"])

KNOWN_MODELS = {
    "qwen": [
        "wan2.7-image",
        "wan2.7-image-pro",
        "wan2.7-t2v",
        "wan2.7-i2v",
        "wan2.7-r2v",
        "wan-t2v",
        "wan-r2v",
        "kling-v3-omni-video-generation",
        "kling/kling-v3-omni-video-generation",
        "wan3.0-video",
    ],
    "doubao": [
        "doubao-seedance-2.0",
        "doubao-seedance-2.0-fast",
        "doubao-seedance-2.0-mini",
        "doubao-seedance-2.5",
    ],
    "edge": ["zh-CN-XiaoxiaoNeural"],
    "system": ["Tingting", "zh"],
}
QWEN_NATIVE_MEDIA_BASE_URL = "https://dashscope.aliyuncs.com/api/v1"


@router.get("/keys")
def list_configs(user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    with db() as session:
        configs = session.exec(
            select(ModelConfig)
            .where(ModelConfig.source == "user", ModelConfig.user_id == user_id, ModelConfig.deleted_at.is_(None))
            .order_by(ModelConfig.updated_at.desc())
        ).all()
        active_official = dict(
            session.exec(
                select(UserOfficialConfigDefault.purpose, UserOfficialConfigDefault.official_config_id).where(
                    UserOfficialConfigDefault.user_id == user_id
                )
            ).all()
        )
        official_configs = session.exec(
            select(ModelConfig)
            .where(
                ModelConfig.source == "official",
                ModelConfig.is_enabled.is_(True),
                ModelConfig.deleted_at.is_(None),
            )
            .order_by(ModelConfig.purpose, ModelConfig.updated_at.desc())
        ).all()

    # `isActive` reports the *effective* default so at most one config per purpose is active across
    # both lists, mirroring app.services.config_service.active_model_config. An override whose target
    # is gone or unusable does not count, which is what lets the personal config take over again.
    usable_official_ids = {config.id for config in official_configs}
    overridden = {purpose for purpose, config_id in active_official.items() if config_id in usable_official_ids}
    active_user_purposes = {
        config.purpose for config in configs if config.is_active and config.is_enabled and config.purpose not in overridden
    }

    def official_is_active(config: ModelConfig) -> bool | None:
        if config.purpose in overridden:
            return active_official[config.purpose] == config.id
        if config.purpose in active_user_purposes:
            return False
        return None  # no user-level choice for this purpose: the system-wide default flag decides

    return {
        "configs": [
            {**config_json(config), "isActive": bool(config.is_active) and config.purpose not in overridden}
            for config in configs
        ],
        "officialConfigs": [official_config_json(config, official_is_active(config)) for config in official_configs],
    }


@router.post("/models")
async def discover_models(payload: dict[str, Any], _: int = Depends(current_user_id)) -> dict[str, list[str]]:
    provider = normalize_provider(str(payload.get("provider", "")))
    base_url = normalize_base_url(str(payload.get("baseUrl", "")))
    api_key = str(payload.get("apiKey", "")).strip()
    known_models = KNOWN_MODELS.get(provider)
    if known_models and (
        provider in {"edge", "system"}
        or not base_url
        or (provider == "qwen" and base_url == QWEN_NATIVE_MEDIA_BASE_URL)
        or (provider == "doubao" and base_url == "https://ark.cn-beijing.volces.com/api/v3")
    ):
        return {"models": known_models}
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


def _own_config(session, config_id: int, user_id: int) -> ModelConfig | None:
    return session.exec(
        select(ModelConfig).where(
            ModelConfig.id == config_id,
            ModelConfig.source == "user",
            ModelConfig.user_id == user_id,
            ModelConfig.deleted_at.is_(None),
        )
    ).first()


@router.get("/keys/{config_id}")
def get_config(config_id: int, user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    with db() as session:
        config = _own_config(session, config_id, user_id)
    if not config:
        raise HTTPException(404, "config not found")
    return {"config": config_json(config)}


@router.post("/keys/{config_id}/secret")
def get_config_secret(config_id: int, user_id: int = Depends(current_user_id)) -> dict[str, str]:
    with db() as session:
        config = _own_config(session, config_id, user_id)
    if not config:
        raise HTTPException(404, "config not found")
    return {"apiKey": config_api_key(config)}


@router.post("/keys", status_code=201)
async def create_config(payload: dict[str, Any], user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    normalized = normalize_config_payload(payload)
    validate_api_key(normalized["provider"], normalized["api_key"])
    fields = config_create_fields(payload, normalized)
    try:
        pricing = normalize_pricing(payload)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    stamp = now()
    with db() as session:
        if bool(payload.get("isActive")):
            session.execute(
                update(ModelConfig)
                .where(
                    ModelConfig.source == "user",
                    ModelConfig.user_id == user_id,
                    ModelConfig.purpose == fields["purpose"],
                    ModelConfig.deleted_at.is_(None),
                )
                .values(is_active=0, updated_at=stamp),
                execution_options={"synchronize_session": False},
            )
            session.execute(
                delete(UserOfficialConfigDefault).where(
                    UserOfficialConfigDefault.user_id == user_id,
                    UserOfficialConfigDefault.purpose == fields["purpose"],
                ),
                execution_options={"synchronize_session": False},
            )
        config = ModelConfig(
            created_at=stamp,
            updated_at=stamp,
            user_id=user_id,
            source="user",
            **fields,
            **pricing,
            pricing_json=pricing_snapshot(pricing),
        )
        session.add(config)
        session.flush()
        session.refresh(config)
        return {"config": config_json(config)}


@router.patch("/keys/{config_id}")
async def update_config(config_id: int, payload: dict[str, Any], user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    with db() as session:
        config = _own_config(session, config_id, user_id)
    if not config:
        raise HTTPException(404, "config not found")

    normalized = normalize_config_payload(payload, config)
    if bool(payload.get("isEnabled", config.is_enabled)):
        validate_api_key(normalized["provider"], normalized["api_key"])
    updates = config_update_fields(payload, config, normalized)
    try:
        updates.update(pricing_updates(payload, config))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if not updates:
        raise HTTPException(400, "no fields to update")

    stamp = now()
    with db() as session:
        if payload.get("isActive"):
            session.execute(
                update(ModelConfig)
                .where(
                    ModelConfig.source == "user",
                    ModelConfig.user_id == user_id,
                    ModelConfig.purpose == normalized["purpose"],
                    ModelConfig.id != config_id,
                    ModelConfig.deleted_at.is_(None),
                )
                .values(is_active=0, updated_at=stamp),
                execution_options={"synchronize_session": False},
            )
            session.execute(
                delete(UserOfficialConfigDefault).where(
                    UserOfficialConfigDefault.user_id == user_id,
                    UserOfficialConfigDefault.purpose == normalized["purpose"],
                ),
                execution_options={"synchronize_session": False},
            )
        session.execute(
            update(ModelConfig)
            .where(ModelConfig.id == config_id, ModelConfig.source == "user", ModelConfig.user_id == user_id)
            .values(**updates, updated_at=stamp),
            execution_options={"synchronize_session": False},
        )
        updated = session.exec(select(ModelConfig).where(ModelConfig.id == config_id)).first()
        return {"config": config_json(updated)}


@router.delete("/keys/{config_id}", status_code=204)
def delete_config(config_id: int, user_id: int = Depends(current_user_id)) -> None:
    with db() as session:
        session.execute(
            update(ModelConfig)
            .where(
                ModelConfig.id == config_id,
                ModelConfig.source == "user",
                ModelConfig.user_id == user_id,
                ModelConfig.deleted_at.is_(None),
            )
            .values(deleted_at=now(), updated_at=now()),
            execution_options={"synchronize_session": False},
        )


@router.post("/official/{config_id}/activate")
def activate_official_config(config_id: int, user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    stamp = now()
    with db() as session:
        config = session.exec(
            select(ModelConfig).where(
                ModelConfig.id == config_id,
                ModelConfig.source == "official",
                ModelConfig.is_enabled.is_(True),
                ModelConfig.deleted_at.is_(None),
            )
        ).first()
        if not config:
            raise HTTPException(404, "official config not found")
        # The user's personal is_active flags are left untouched: the override below outranks them,
        # so removing the override (or losing the official config) restores the previous choice.
        upsert = sqlite_insert(UserOfficialConfigDefault).values(
            user_id=user_id,
            purpose=config.purpose,
            official_config_id=config_id,
            created_at=stamp,
            updated_at=stamp,
        )
        session.execute(
            upsert.on_conflict_do_update(
                index_elements=["user_id", "purpose"],
                set_={"official_config_id": upsert.excluded.official_config_id, "updated_at": upsert.excluded.updated_at},
            )
        )
        return {"config": official_config_json(config, True)}


@router.delete("/official/{config_id}/activate", status_code=204)
def deactivate_official_config(config_id: int, user_id: int = Depends(current_user_id)) -> None:
    with db() as session:
        session.execute(
            delete(UserOfficialConfigDefault).where(
                UserOfficialConfigDefault.user_id == user_id,
                UserOfficialConfigDefault.official_config_id == config_id,
            ),
            execution_options={"synchronize_session": False},
        )
