"""Character and variant management: the series bible a user actually edits."""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import select

from app.api.deps import current_user_id
from app.core.database import db
from app.core.realtime import broadcast
from app.llms.registry import models
from app.models import Scene
from app.schemas.requests import (
    CreateCharacterRequest,
    CreateCharacterVariantRequest,
    SetSceneCastRequest,
    UpdateCharacterRequest,
    UpdateCharacterVariantRequest,
)
from app.schemas.serializers import character_json, character_variant_json
from app.services.character_service import (
    characters_for,
    create_character,
    create_variant,
    delete_character,
    owned_character,
    owned_variant,
    set_scene_cast,
    variants_for,
)
from app.services.config_service import active_model_config
from app.services.generation_service import build_portrait_prompt, persist_character_portrait
from app.services.project_service import owned_project
from app.services.usage_service import record_usage, require_model_balance
from app.utils.common import now


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects", tags=["characters"])


def _episode_range(from_episode: int | None, to_episode: int | None) -> None:
    """A variant that ends before it starts would never resolve for any episode."""
    if from_episode is not None and to_episode is not None and to_episode < from_episode:
        raise HTTPException(400, "toEpisode must not be earlier than fromEpisode")


@router.get("/{project_id}/characters")
def list_characters(project_id: str, user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    with db() as session:
        owned_project(session, project_id, user_id)
        characters = characters_for(session, project_id)
        variants = variants_for(session, [character.id for character in characters])
        data = [character_json(character, variants.get(character.id, [])) for character in characters]
    return {"characters": data}


@router.post("/{project_id}/characters", status_code=201)
async def add_character(
    project_id: str,
    body: CreateCharacterRequest,
    user_id: int = Depends(current_user_id),
) -> dict[str, Any]:
    with db() as session:
        owned_project(session, project_id, user_id)
        character = create_character(
            session,
            project_id,
            name=body.name,
            aliases=body.aliases,
            description=body.description,
            appearance_prompt=body.appearance_prompt,
            voice_provider=body.voice_provider,
            voice_model=body.voice_model,
            order_num=body.order_num,
        )
        data = character_json(character, [])
    await broadcast(project_id, {"type": "CHARACTER_UPDATE", "projectId": project_id, "data": data})
    return {"character": data}


@router.patch("/{project_id}/characters/{character_id}")
async def update_character(
    project_id: str,
    character_id: str,
    body: UpdateCharacterRequest,
    user_id: int = Depends(current_user_id),
) -> dict[str, Any]:
    # exclude_unset, not "is not None": unlocking a card and clearing a prompt are both
    # real edits, and only an absent key means "leave it alone".
    updates = {key: value for key, value in body.model_dump(exclude_unset=True).items() if value is not None}
    if not updates:
        raise HTTPException(400, "no fields to update")

    with db() as session:
        owned_project(session, project_id, user_id)
        character = owned_character(session, project_id, character_id)
        for key, value in updates.items():
            setattr(character, key, value)
        character.updated_at = now()
        session.add(character)
        session.flush()
        data = character_json(character, variants_for(session, [character_id]).get(character_id, []))
    await broadcast(project_id, {"type": "CHARACTER_UPDATE", "projectId": project_id, "data": data})
    return {"character": data}


@router.delete("/{project_id}/characters/{character_id}", status_code=204)
async def remove_character(
    project_id: str,
    character_id: str,
    user_id: int = Depends(current_user_id),
) -> None:
    with db() as session:
        owned_project(session, project_id, user_id)
        character = owned_character(session, project_id, character_id)
        delete_character(session, character)
    await broadcast(
        project_id,
        {"type": "CHARACTER_DELETED", "projectId": project_id, "characterId": character_id},
    )


@router.post("/{project_id}/characters/{character_id}/variants", status_code=201)
def add_variant(
    project_id: str,
    character_id: str,
    body: CreateCharacterVariantRequest,
    user_id: int = Depends(current_user_id),
) -> dict[str, Any]:
    _episode_range(body.from_episode, body.to_episode)
    with db() as session:
        owned_project(session, project_id, user_id)
        owned_character(session, project_id, character_id)
        variant = create_variant(
            session,
            character_id,
            name=body.name,
            appearance_prompt=body.appearance_prompt,
            voice_model=body.voice_model,
            from_episode=body.from_episode,
            to_episode=body.to_episode,
        )
        data = character_variant_json(variant)
    return {"variant": data}


@router.patch("/{project_id}/characters/{character_id}/variants/{variant_id}")
def update_variant(
    project_id: str,
    character_id: str,
    variant_id: str,
    body: UpdateCharacterVariantRequest,
    user_id: int = Depends(current_user_id),
) -> dict[str, Any]:
    updates = {key: value for key, value in body.model_dump(exclude_unset=True).items() if value is not None}
    if not updates:
        raise HTTPException(400, "no fields to update")

    with db() as session:
        owned_project(session, project_id, user_id)
        owned_character(session, project_id, character_id)
        variant = owned_variant(session, character_id, variant_id)
        _episode_range(
            updates.get("from_episode", variant.from_episode),
            updates.get("to_episode", variant.to_episode),
        )
        for key, value in updates.items():
            setattr(variant, key, value)
        variant.updated_at = now()
        session.add(variant)
        session.flush()
        data = character_variant_json(variant)
    return {"variant": data}


@router.delete("/{project_id}/characters/{character_id}/variants/{variant_id}", status_code=204)
def remove_variant(
    project_id: str,
    character_id: str,
    variant_id: str,
    user_id: int = Depends(current_user_id),
) -> None:
    with db() as session:
        owned_project(session, project_id, user_id)
        owned_character(session, project_id, character_id)
        variant = owned_variant(session, character_id, variant_id)
        stamp = now()
        variant.deleted_at = stamp
        variant.updated_at = stamp
        session.add(variant)


@router.post("/{project_id}/characters/{character_id}/portrait")
async def generate_portrait(
    project_id: str,
    character_id: str,
    user_id: int = Depends(current_user_id),
) -> dict[str, Any]:
    """Render the reference portrait later shots are matched against.

    Synchronous rather than a background job: it is one image and the card the user is
    looking at is the only thing waiting on it.
    """
    with db() as session:
        owned_project(session, project_id, user_id)
        character = owned_character(session, project_id, character_id)
        if character.is_locked:
            raise HTTPException(409, "character is locked, unlock it before regenerating the portrait")
        if not (character.appearance_prompt or character.description).strip():
            raise HTTPException(400, "describe the character before generating a portrait")
        config = active_model_config(session, user_id, "image", "角色定妆图")
        require_model_balance(session, user_id, config)
        prompt = build_portrait_prompt(character.name, character.appearance_prompt, character.description)

    if config["provider"] not in {"openai", "gemini", "qwen"}:
        raise HTTPException(400, "image generation currently only supports provider openai/gemini/qwen")
    started_at = time.monotonic()
    try:
        image = await models.generate_image(
            config["apiKey"],
            config["model"],
            prompt,
            base_url=config.get("baseUrl", ""),
            provider=config["provider"],
        )
    except Exception as exc:
        logger.warning("portrait generation failed project=%s character=%s: %s", project_id, character_id, exc)
        raise HTTPException(502, f"failed to generate portrait: {str(exc)[:220]}") from exc
    record_usage(user_id, config, "character_portrait", started_at, quantity=1)
    stored = persist_character_portrait(project_id, character_id, image.data, image.format)

    with db() as session:
        character = owned_character(session, project_id, character_id)
        character.reference_image_path = stored
        # Freeze what produced it: changing the account default later must not restyle a
        # character that the rest of the series has already been matched against.
        character.image_provider = config["provider"]
        character.image_model = config["model"]
        character.image_base_url = config.get("baseUrl", "")
        character.updated_at = now()
        session.add(character)
        session.flush()
        data = character_json(character, variants_for(session, [character_id]).get(character_id, []))
    await broadcast(project_id, {"type": "CHARACTER_UPDATE", "projectId": project_id, "data": data})
    return {"character": data}


@router.put("/{project_id}/scenes/{scene_id}/characters")
async def set_cast(
    project_id: str,
    scene_id: str,
    body: SetSceneCastRequest,
    user_id: int = Depends(current_user_id),
) -> dict[str, Any]:
    """Replace which characters appear in a shot. An empty list clears the cast."""
    with db() as session:
        owned_project(session, project_id, user_id)
        scene = session.exec(
            select(Scene).where(Scene.id == scene_id, Scene.project_id == project_id, Scene.deleted_at.is_(None))
        ).first()
        if not scene:
            raise HTTPException(404, "scene not found")
        character_ids = set_scene_cast(session, scene, body.character_ids)
    await broadcast(
        project_id,
        {
            "type": "SCENE_UPDATE",
            "projectId": project_id,
            "sceneId": scene_id,
            "data": {"characterIds": character_ids},
        },
    )
    return {"sceneId": scene_id, "characterIds": character_ids}
