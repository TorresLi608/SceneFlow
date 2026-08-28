from __future__ import annotations

import json
from typing import Any

from app.models import (
    Character,
    Asset,
    CharacterState,
    ChatMessage,
    ChatSession,
    Episode,
    ModelConfig,
    Project,
    Prop,
    Scene,
    User,
    UserVoice,
    VoiceProfile,
)
from app.services.artifact_service import signed_url_for_stored
from app.services.config_service import video_capabilities
from app.services.reference_service import stored_generation_references


def user_json(user: User, *, request_count: int = 0, historical_cost_micros: int = 0) -> dict[str, Any]:
    return {
        "id": user.id,
        "username": user.username,
        "nickname": user.nickname or "",
        "email": user.email or "",
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
        "createdAt": config.created_at,
        "updatedAt": config.updated_at,
        "pricingMultiplier": price("pricing_multiplier", "1"),
        "inputPricePerMillion": price("input_price_per_million", "0"),
        "outputPricePerMillion": price("output_price_per_million", "0"),
        "cacheReadPricePerMillion": price("cache_read_price_per_million", "0"),
        "cacheWritePricePerMillion": price("cache_write_price_per_million", "0"),
        "unitPrice": price("unit_price", "0"),
        "unitName": config.unit_name,
        "imageMaxReferenceImages": config.image_max_reference_images if config.image_max_reference_images is not None else 4,
        "videoCapabilities": video_capabilities(config) if config.purpose == "video" else None,
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
    progress = lambda status: 100 if status == "success" else 20 if status == "generating" else 0
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
        "transition": scene.transition or "",
        "videoPrompt": scene.video_prompt or "",
        "imageReferences": [
            {"kind": kind, "id": asset_id}
            for kind, asset_id in stored_generation_references(scene.image_references_json)
        ],
        "videoReferences": [
            {"kind": kind, "id": asset_id}
            for kind, asset_id in stored_generation_references(scene.video_references_json)
        ],
        # 0 means undecided; the renderer falls back to the project's default shot length.
        "durationMs": scene.duration_ms or 0,
        "subtitleText": scene.subtitle_text or "",
        "isLocked": bool(scene.is_locked),
        # Carried so the client can key a row on "the server actually changed this" rather
        # than on a signed URL, which is freshly minted on every response and would remount
        # every row on every poll.
        "updatedAt": scene.updated_at,
        "image": {
            "url": scene_asset_url(scene.image_path, stem),
            "status": scene.image_status,
            "progress": progress(scene.image_status),
        },
        "audio": {
            "url": scene_asset_url(scene.audio_path, stem),
            "status": scene.audio_status,
            "progress": progress(scene.audio_status),
            "duration": scene.audio_duration or 0,
        },
        "video": {
            "url": scene_asset_url(scene.video_path, stem),
            "status": scene.video_status or "idle",
            "progress": progress(scene.video_status),
        },
        "errorMessage": scene.error_message or "",
    }


def asset_json(asset: Asset) -> dict[str, Any]:
    return {
        "id": asset.id,
        "projectId": asset.project_id,
        "name": asset.name,
        "description": asset.description or "",
        "kind": asset.kind,
        "mediaType": asset.media_type,
        "url": scene_asset_url(asset.path, f"asset-{asset.id}"),
        "createdAt": asset.created_at,
        "updatedAt": asset.updated_at,
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
        # Enough for a list row to show whether this episode has been anchored yet.
        "toneImageStatus": episode.tone_image_status or "idle",
        "toneImageUrl": scene_asset_url(episode.tone_image_path, f"episode-{episode.episode_number}-tone"),
        "errorMessage": episode.error_message or "",
        "updatedAt": episode.updated_at,
    }


def episode_json(episode: Episode, scenes: list[Scene], cast: dict[str, list[str]] | None = None) -> dict[str, Any]:
    stem = f"episode-{episode.episode_number}"
    return {
        **episode_summary_json(episode, len(scenes)),
        "sourceText": episode.source_text or "",
        # The style anchor the per-shot renders were matched against.
        "toneImageUrl": scene_asset_url(episode.tone_image_path, f"{stem}-tone"),
        "toneImageStatus": episode.tone_image_status or "idle",
        "videoUrl": scene_asset_url(episode.video_path, stem),
        "scenes": [scene_json(scene, (cast or {}).get(scene.id)) for scene in scenes],
    }


def character_state_json(state: CharacterState) -> dict[str, Any]:
    return {
        "id": state.id,
        "characterId": state.character_id,
        "name": state.name,
        "description": state.description or "",
        "appearancePrompt": state.appearance_prompt or "",
        "finalPrompt": state.final_prompt or "",
        # The state's turnaround sheet: front, three-quarter, and profile in one image.
        "referenceImageUrl": scene_asset_url(state.reference_image_path, f"state-{state.id}"),
        "voiceModel": state.voice_model or "",
        "orderNum": state.order_num or 0,
        # Null on either means the state is not pinned to an episode range at all: it is one
        # of several parallel looks rather than a change at a point in the timeline.
        "fromEpisode": state.from_episode,
        "toEpisode": state.to_episode,
        "updatedAt": state.updated_at,
    }


def character_json(character: Character, states: list[CharacterState] | None = None) -> dict[str, Any]:
    return {
        "id": character.id,
        "projectId": character.project_id,
        "name": character.name,
        "aliases": character.aliases or "",
        "description": character.description or "",
        "appearancePrompt": character.appearance_prompt or "",
        "referenceImageUrl": scene_asset_url(character.reference_image_path, f"character-{character.id}"),
        # Every state of this character tiled into one image.
        "sheetImageUrl": scene_asset_url(character.sheet_image_path, f"character-sheet-{character.id}"),
        "imageProvider": character.image_provider or "",
        "imageModel": character.image_model or "",
        "voiceProvider": character.voice_provider or "",
        "voiceModel": character.voice_model or "",
        "voiceProfileId": character.voice_profile_id,
        "isLocked": bool(character.is_locked),
        "orderNum": character.order_num or 0,
        "states": [character_state_json(state) for state in states or []],
        "updatedAt": character.updated_at,
    }


def voice_profile_json(profile: VoiceProfile) -> dict[str, Any]:
    return {
        "id": profile.id,
        "projectId": profile.project_id,
        "name": profile.name,
        "note": profile.note or "",
        "voiceProvider": profile.voice_provider or "",
        "voiceModel": profile.voice_model or "",
        "sampleText": profile.sample_text or "",
        "audioUrl": scene_asset_url(profile.audio_path, f"voice-{profile.id}"),
        "orderNum": profile.order_num or 0,
        "updatedAt": profile.updated_at,
    }


def user_voice_json(voice: UserVoice) -> dict[str, Any]:
    return {
        "id": voice.id,
        "voiceId": voice.voice_id,
        "targetModel": voice.target_model,
        "name": voice.name or "",
        "voicePrompt": voice.voice_prompt or "",
        "previewText": voice.preview_text or "",
        "previewAudioUrl": scene_asset_url(voice.preview_audio_path, f"voice-{voice.id}"),
        "createdAt": voice.created_at,
        "updatedAt": voice.updated_at,
    }


def prop_json(prop: Prop, owner_name: str = "") -> dict[str, Any]:
    return {
        "id": prop.id,
        "projectId": prop.project_id,
        "name": prop.name,
        "description": prop.description or "",
        "ownerCharacterId": prop.owner_character_id,
        # Resolved by the caller when it has the cast loaded; the id alone cannot render.
        "ownerName": owner_name,
        "finalPrompt": prop.final_prompt or "",
        "imageUrl": scene_asset_url(prop.image_path, f"prop-{prop.id}"),
        "orderNum": prop.order_num or 0,
        "updatedAt": prop.updated_at,
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
        "description": project.description or "",
        "coverPrompt": project.cover_prompt or "",
        # Minted per response like every other asset: the row stores a path, not a URL.
        "coverImageUrl": scene_asset_url(project.cover_image_path, f"cover-{project.id}"),
        "originalScript": project.original_script or "",
        "seriesBible": project.series_bible or "",
        # The whole cast and every prop, each tiled into one sheet the renderer carries.
        "characterSheetUrl": scene_asset_url(project.character_sheet_path, f"cast-{project.id}"),
        "propSheetUrl": scene_asset_url(project.prop_sheet_path, f"props-{project.id}"),
        # Every voice introducing itself, concatenated; a timbre reference for the video model.
        "voiceSheetUrl": scene_asset_url(project.voice_sheet_path, f"voices-{project.id}"),
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
        # Which model this series pinned per purpose, and the parameters every render in it
        # starts from. `null` means the purpose follows the account default.
        "modelSettings": {
            "textConfigId": project.text_config_id,
            "imageConfigId": project.image_config_id,
            "videoConfigId": project.video_config_id,
            "audioConfigId": project.audio_config_id,
            "imageResolution": project.image_resolution or "2K",
            "imageRatio": project.image_ratio or "auto",
            "videoQuality": project.video_quality or "720p",
            "videoAspectRatio": project.video_aspect_ratio or "9:16",
            "videoDuration": project.video_duration or 5,
            "videoFps": project.video_fps or 24,
            "videoPromptExtend": bool(project.video_prompt_extend),
            "videoAudioEnabled": bool(project.video_audio_enabled),
        },
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
