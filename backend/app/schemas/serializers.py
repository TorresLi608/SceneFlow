from __future__ import annotations

import json
from typing import Any

from app.models import (
    Character,
    CharacterVariant,
    ChatMessage,
    ChatSession,
    Episode,
    ModelConfig,
    Project,
    Scene,
    User,
)
from app.services.artifact_service import signed_url_for_stored


def user_json(user: User, *, request_count: int = 0, historical_cost_micros: int = 0) -> dict[str, Any]:
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role or "user",
        "isDisabled": bool(user.is_disabled),
        "balanceMicros": str(user.balance_micros),
        "level": user.level,
        "group": user.user_group,
        "historicalCostMicros": str(historical_cost_micros),
        "requestCount": request_count,
        "createdAt": user.created_at,
        "updatedAt": user.updated_at,
    }


def config_json(config: ModelConfig) -> dict[str, Any]:
    pricing: dict[str, Any] = {}
    if config.pricing_json:
        try:
            parsed = json.loads(config.pricing_json)
            pricing = parsed if isinstance(parsed, dict) else {}
        except (TypeError, ValueError):
            pass

    def price(name: str, default: str) -> str:
        value = pricing.get(name, getattr(config, name))
        return str(default if value is None else value)

    return {
        "id": config.id,
        "source": config.source,
        "name": config.name or "",
        "description": config.description or "",
        "purpose": config.purpose,
        "provider": config.provider,
        "baseUrl": config.base_url or "",
        "modelSeries": config.model_name or "",
        "model": config.model_name or "",
        "isActive": bool(config.is_active),
        "isEnabled": bool(config.is_enabled),
        "isVerified": bool(config.is_verified),
        "createdAt": config.created_at,
        "updatedAt": config.updated_at,
        "pricingMultiplier": price("pricing_multiplier", "1"),
        "inputPricePerMillion": price("input_price_per_million", "0"),
        "outputPricePerMillion": price("output_price_per_million", "0"),
        "cacheReadPricePerMillion": price("cache_read_price_per_million", "0"),
        "cacheWritePricePerMillion": price("cache_write_price_per_million", "0"),
        "unitPrice": price("unit_price", "0"),
        "unitName": config.unit_name,
    }


def official_config_json(config: ModelConfig, is_active: bool | None = None) -> dict[str, Any]:
    data = config_json(config)
    data["source"] = "official"
    if is_active is not None:
        data["isActive"] = is_active
    return data


def scene_asset_url(stored_path: str | None, download_stem: str) -> str | None:
    """Sign a short-lived link for an asset the row tracks by path.

    Returns None when the file is gone or the path is unreadable so the client renders
    "not generated yet" instead of a broken image.
    """
    if not stored_path:
        return None
    try:
        return signed_url_for_stored(stored_path, download_stem)
    except (ValueError, OSError):
        return None


def scene_json(scene: Scene, character_ids: list[str] | None = None) -> dict[str, Any]:
    stem = f"scene-{scene.order_num or 0}"
    return {
        "id": scene.id,
        "episodeId": scene.episode_id,
        "order": scene.order_num,
        "narration": scene.narration,
        "dialogue": scene.dialogue or "",
        "speakerCharacterId": scene.speaker_character_id,
        # Who appears in the shot. Empty when the caller did not load the cast.
        "characterIds": character_ids or [],
        "visualPrompt": scene.visual_prompt,
        "shotType": scene.shot_type or "",
        "cameraMove": scene.camera_move or "",
        # 0 means "follow the voice track"; the client shows the audio duration instead.
        "durationMs": scene.duration_ms or 0,
        "subtitleText": scene.subtitle_text or "",
        "isLocked": bool(scene.is_locked),
        "image": {
            "url": scene_asset_url(scene.image_path, stem),
            "status": scene.image_status,
            "progress": 0,
        },
        "audio": {
            "url": scene_asset_url(scene.audio_path, stem),
            "status": scene.audio_status,
            "progress": 0,
            "duration": scene.audio_duration or 0,
        },
        "video": {
            "url": scene_asset_url(scene.video_path, stem),
            "status": scene.video_status or "idle",
            "progress": 0,
        },
        "errorMessage": scene.error_message or "",
    }


def episode_summary_json(episode: Episode, scene_count: int = 0) -> dict[str, Any]:
    """An episode without its script or shots, for switchers and series lists.

    `source_text` is a full script and there is one per episode, so a series list that
    inlined it would ship megabytes to render a dropdown.
    """
    return {
        "id": episode.id,
        "projectId": episode.project_id,
        "episodeNumber": episode.episode_number,
        "title": episode.title or f"第 {episode.episode_number} 集",
        "synopsis": episode.synopsis or "",
        "status": episode.status or "draft",
        "videoStatus": episode.video_status or "idle",
        "videoProgress": episode.video_progress or 0,
        "durationMs": episode.duration_ms or 0,
        "sceneCount": scene_count,
        "errorMessage": episode.error_message or "",
        "updatedAt": episode.updated_at,
    }


def episode_json(episode: Episode, scenes: list[Scene], cast: dict[str, list[str]] | None = None) -> dict[str, Any]:
    stem = f"episode-{episode.episode_number}"
    return {
        **episode_summary_json(episode, len(scenes)),
        "sourceText": episode.source_text or "",
        "videoUrl": scene_asset_url(episode.video_path, stem),
        "scenes": [scene_json(scene, (cast or {}).get(scene.id)) for scene in scenes],
    }


def character_variant_json(variant: CharacterVariant) -> dict[str, Any]:
    return {
        "id": variant.id,
        "characterId": variant.character_id,
        "name": variant.name,
        "appearancePrompt": variant.appearance_prompt or "",
        "referenceImageUrl": scene_asset_url(variant.reference_image_path, f"variant-{variant.id}"),
        "voiceModel": variant.voice_model or "",
        "fromEpisode": variant.from_episode,
        # Null means the variant stays in effect for every later episode.
        "toEpisode": variant.to_episode,
        "updatedAt": variant.updated_at,
    }


def character_json(character: Character, variants: list[CharacterVariant] | None = None) -> dict[str, Any]:
    return {
        "id": character.id,
        "projectId": character.project_id,
        "name": character.name,
        "aliases": character.aliases or "",
        "description": character.description or "",
        "appearancePrompt": character.appearance_prompt or "",
        "referenceImageUrl": scene_asset_url(character.reference_image_path, f"character-{character.id}"),
        "imageProvider": character.image_provider or "",
        "imageModel": character.image_model or "",
        "voiceProvider": character.voice_provider or "",
        "voiceModel": character.voice_model or "",
        "isLocked": bool(character.is_locked),
        "orderNum": character.order_num or 0,
        "variants": [character_variant_json(variant) for variant in variants or []],
        "updatedAt": character.updated_at,
    }


def project_json(
    project: Project,
    scenes: list[Scene],
    *,
    cast: dict[str, list[str]] | None = None,
    episodes: list[dict[str, Any]] | None = None,
    current_episode_id: str | None = None,
) -> dict[str, Any]:
    """Serialize a series.

    `scenes` is one episode's ordered shots, not the whole series': order numbers restart
    each episode, so a merged list would be meaningless. Callers pass the current
    episode's shots and use `episodes` for everything else.
    """
    return {
        "id": project.id,
        "title": project.title or "未命名项目",
        "originalScript": project.original_script or "",
        "seriesBible": project.series_bible or "",
        "status": project.status or "idle",
        "videoStatus": project.video_status or "idle",
        "videoProgress": project.video_progress or 0,
        "videoUrl": project.video_url or None,
        "productionSettings": {
            "mode": project.mode,
            "aspectRatio": project.aspect_ratio,
            "width": project.width,
            "height": project.height,
            "fps": project.fps,
            "targetDurationMs": project.target_duration_ms,
            "language": project.language,
            "stylePrompt": project.style_prompt,
            "negativePrompt": project.negative_prompt,
        },
        "currentStage": project.current_stage,
        "currentEpisodeId": current_episode_id,
        "episodes": episodes or [],
        "updatedAt": project.updated_at,
        "scenes": [scene_json(scene, (cast or {}).get(scene.id)) for scene in scenes],
    }


def chat_session_json(session: ChatSession) -> dict[str, Any]:
    return {
        "id": session.id,
        "title": session.title,
        "configId": session.config_id,
        "officialConfigId": session.official_config_id,
        "provider": session.provider or "",
        "model": session.model_name or "",
        "createdAt": session.created_at,
        "updatedAt": session.updated_at,
    }


def chat_message_json(message: ChatMessage) -> dict[str, Any]:
    attachments = []
    if message.attachments:
        try:
            attachments = json.loads(message.attachments)
        except json.JSONDecodeError:
            attachments = []
    return {
        "id": message.id,
        "sessionId": message.session_id,
        "role": message.role,
        "content": message.content,
        "attachments": attachments,
        "reasoning": message.reasoning or "",
        "provider": message.provider or "",
        "model": message.model_name or "",
        "createdAt": message.created_at,
    }
