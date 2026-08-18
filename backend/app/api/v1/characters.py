"""Character and state management: the series bible a user actually edits."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import select

from app.api.deps import current_user_id
from app.core.database import db
from app.core.realtime import broadcast
from app.models import Scene
from app.schemas.requests import (
    CreateCharacterRequest,
    CreateCharacterStateRequest,
    DraftPromptRequest,
    GenerateReferenceImageRequest,
    SetSceneCastRequest,
    UpdateCharacterRequest,
    UpdateCharacterStateRequest,
    UploadReferenceImageRequest,
)
from app.schemas.serializers import character_json, character_state_json, project_json
from app.services.artifact_service import decode_image_data_url, store_artifact
from app.services.character_service import (
    characters_for,
    create_character,
    create_state,
    delete_character,
    owned_character,
    owned_state,
    set_scene_cast,
    states_for,
)
from app.services.prompt_service import (
    CHARACTER_SHEET_SYSTEM,
    character_sheet_prompt,
    fallback_character_sheet_prompt,
)
from app.services.project_service import owned_project
from app.services.reference_service import (
    draft_prompt,
    draw_reference,
    image_config,
    script_config,
    store_sheet,
)
from app.services.voice_service import owned_voice_profile
from app.utils.common import now


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects", tags=["characters"])


def _episode_range(from_episode: int | None, to_episode: int | None) -> None:
    """A state that ends before it starts would never resolve for any episode."""
    if from_episode is not None and to_episode is not None and to_episode < from_episode:
        raise HTTPException(400, "toEpisode must not be earlier than fromEpisode")


def _character_payload(session, project_id: str, character_id: str) -> dict[str, Any]:
    character = owned_character(session, project_id, character_id)
    return character_json(character, states_for(session, [character_id]).get(character_id, []))


@router.get("/{project_id}/characters")
def list_characters(project_id: str, user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    with db() as session:
        owned_project(session, project_id, user_id)
        characters = characters_for(session, project_id)
        states = states_for(session, [character.id for character in characters])
        data = [character_json(character, states.get(character.id, [])) for character in characters]
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
        if "voice_profile_id" in updates:
            # "" is how a client says "unbind": a JSON null is indistinguishable from an
            # absent field above, so it would silently keep the old profile.
            profile_id = str(updates["voice_profile_id"]).strip()
            # A profile from another show would resolve to no voice at synthesis time.
            updates["voice_profile_id"] = (
                owned_voice_profile(session, project_id, profile_id).id if profile_id else None
            )
        for key, value in updates.items():
            setattr(character, key, value)
        character.updated_at = now()
        session.add(character)
        session.flush()
        data = character_json(character, states_for(session, [character_id]).get(character_id, []))
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


@router.post("/{project_id}/characters/{character_id}/states", status_code=201)
def add_state(
    project_id: str,
    character_id: str,
    body: CreateCharacterStateRequest,
    user_id: int = Depends(current_user_id),
) -> dict[str, Any]:
    _episode_range(body.from_episode, body.to_episode)
    with db() as session:
        owned_project(session, project_id, user_id)
        owned_character(session, project_id, character_id)
        state = create_state(
            session,
            character_id,
            name=body.name,
            description=body.description,
            appearance_prompt=body.appearance_prompt,
            system_prompt=body.system_prompt,
            final_prompt=body.final_prompt,
            voice_model=body.voice_model,
            order_num=body.order_num,
            from_episode=body.from_episode,
            to_episode=body.to_episode,
        )
        data = character_state_json(state)
    return {"state": data}


@router.patch("/{project_id}/characters/{character_id}/states/{state_id}")
def update_state(
    project_id: str,
    character_id: str,
    state_id: str,
    body: UpdateCharacterStateRequest,
    user_id: int = Depends(current_user_id),
) -> dict[str, Any]:
    updates = {key: value for key, value in body.model_dump(exclude_unset=True).items() if value is not None}
    if not updates:
        raise HTTPException(400, "no fields to update")

    with db() as session:
        owned_project(session, project_id, user_id)
        owned_character(session, project_id, character_id)
        state = owned_state(session, character_id, state_id)
        _episode_range(
            updates.get("from_episode", state.from_episode),
            updates.get("to_episode", state.to_episode),
        )
        for key, value in updates.items():
            setattr(state, key, value)
        state.updated_at = now()
        session.add(state)
        session.flush()
        data = character_state_json(state)
    return {"state": data}


@router.delete("/{project_id}/characters/{character_id}/states/{state_id}", status_code=204)
def remove_state(
    project_id: str,
    character_id: str,
    state_id: str,
    user_id: int = Depends(current_user_id),
) -> None:
    with db() as session:
        owned_project(session, project_id, user_id)
        owned_character(session, project_id, character_id)
        state = owned_state(session, character_id, state_id)
        stamp = now()
        state.deleted_at = stamp
        state.updated_at = stamp
        session.add(state)


@router.post("/{project_id}/characters/{character_id}/states/{state_id}/prompt")
async def draft_state_prompt(
    project_id: str,
    character_id: str,
    state_id: str,
    body: DraftPromptRequest,
    user_id: int = Depends(current_user_id),
) -> dict[str, Any]:
    """Draft the turnaround prompt from the character and the state, for review.

    Returned rather than saved: the user is meant to read and edit this before it draws
    anything, so writing it here would make the preview step decorative.
    """
    with db() as session:
        owned_project(session, project_id, user_id)
        character = owned_character(session, project_id, character_id)
        state = owned_state(session, character_id, state_id)
        # The dialog's unsaved edits win over the stored row; falling back keeps a plain
        # "draft it for me" click working without echoing the whole form back.
        user_text = character_sheet_prompt(
            character.name,
            character.description,
            character.appearance_prompt,
            body.name or state.name,
            body.description or state.description,
        )
        system = body.system_prompt or state.system_prompt or CHARACTER_SHEET_SYSTEM
        config = script_config(session, user_id, "角色状态提示词")

    prompt = await draft_prompt(config, user_id, system, user_text, body.model, "character_state_prompt")
    return {"stateId": state_id, "prompt": prompt}


@router.post("/{project_id}/characters/{character_id}/states/{state_id}/image")
async def generate_state_image(
    project_id: str,
    character_id: str,
    state_id: str,
    body: GenerateReferenceImageRequest,
    user_id: int = Depends(current_user_id),
) -> dict[str, Any]:
    """Draw the state's turnaround sheet from the approved prompt."""
    with db() as session:
        owned_project(session, project_id, user_id)
        character = owned_character(session, project_id, character_id)
        if character.is_locked:
            raise HTTPException(409, "character is locked, unlock it before regenerating its images")
        state = owned_state(session, character_id, state_id)
        prompt = (body.prompt or state.final_prompt).strip() or fallback_character_sheet_prompt(
            character.name,
            state.name,
            state.appearance_prompt or state.description or character.appearance_prompt or character.description,
        )
        config = image_config(session, user_id, "角色三面图")

    data, extension = await draw_reference(config, user_id, prompt, "character_state_image")
    stored = store_artifact("characters", project_id, f"{state_id}.{extension}", data)

    with db() as session:
        owned_project(session, project_id, user_id)
        state = owned_state(session, character_id, state_id)
        state.reference_image_path = stored
        # Remember what was actually drawn, so a reload shows the prompt behind the image.
        state.final_prompt = prompt[:4000]
        state.updated_at = now()
        session.add(state)
        character = owned_character(session, project_id, character_id)
        # Freeze what produced it: changing the account default later must not restyle a
        # character the rest of the series has already been matched against.
        character.image_provider = config["provider"]
        character.image_model = config["model"]
        character.image_base_url = config.get("baseUrl", "")
        character.updated_at = now()
        session.add(character)
        session.flush()
        data_json = _character_payload(session, project_id, character_id)
    await broadcast(project_id, {"type": "CHARACTER_UPDATE", "projectId": project_id, "data": data_json})
    return {"character": data_json}


@router.put("/{project_id}/characters/{character_id}/states/{state_id}/image")
async def upload_state_image(
    project_id: str,
    character_id: str,
    state_id: str,
    body: UploadReferenceImageRequest,
    user_id: int = Depends(current_user_id),
) -> dict[str, Any]:
    """Store a turnaround sheet the user drew themselves."""
    try:
        data, _, extension = decode_image_data_url(body.image_data)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    with db() as session:
        owned_project(session, project_id, user_id)
        owned_character(session, project_id, character_id)
        owned_state(session, character_id, state_id)
    stored = store_artifact("characters", project_id, f"{state_id}.{extension}", data)

    with db() as session:
        owned_project(session, project_id, user_id)
        state = owned_state(session, character_id, state_id)
        state.reference_image_path = stored
        state.updated_at = now()
        session.add(state)
        session.flush()
        data_json = _character_payload(session, project_id, character_id)
    await broadcast(project_id, {"type": "CHARACTER_UPDATE", "projectId": project_id, "data": data_json})
    return {"character": data_json}


@router.post("/{project_id}/characters/{character_id}/sheet")
async def merge_character_sheet(
    project_id: str,
    character_id: str,
    user_id: int = Depends(current_user_id),
) -> dict[str, Any]:
    """Tile one character's states into a single labelled sheet."""
    with db() as session:
        owned_project(session, project_id, user_id)
        character = owned_character(session, project_id, character_id)
        entries = [
            (state.reference_image_path, f"{character.name} · {state.name}")
            for state in states_for(session, [character_id]).get(character_id, [])
        ]
        # A character whose card has a portrait but no states still merges to something.
        if not any(stored for stored, _ in entries) and character.reference_image_path:
            entries = [(character.reference_image_path, character.name)]

    stored = store_sheet("characters", project_id, f"{character_id}-sheet.jpg", entries)

    with db() as session:
        owned_project(session, project_id, user_id)
        character = owned_character(session, project_id, character_id)
        character.sheet_image_path = stored
        character.updated_at = now()
        session.add(character)
        session.flush()
        data = _character_payload(session, project_id, character_id)
    await broadcast(project_id, {"type": "CHARACTER_UPDATE", "projectId": project_id, "data": data})
    return {"character": data}


@router.post("/{project_id}/characters/sheet")
async def merge_cast_sheet(project_id: str, user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    """Tile every character and state in the series into one sheet.

    This is the image a storyboard render actually carries: providers cap how many
    reference images one request may hold, so a cast of any size has to arrive as one.
    """
    with db() as session:
        owned_project(session, project_id, user_id)
        characters = characters_for(session, project_id)
        states = states_for(session, [character.id for character in characters])
        entries: list[tuple[str | None, str]] = []
        for character in characters:
            character_states = states.get(character.id, [])
            drawn = [state for state in character_states if state.reference_image_path]
            if drawn:
                entries.extend((state.reference_image_path, f"{character.name} · {state.name}") for state in drawn)
            elif character.reference_image_path:
                entries.append((character.reference_image_path, character.name))

    stored = store_sheet("characters", project_id, f"{project_id}-cast.jpg", entries)

    with db() as session:
        project = owned_project(session, project_id, user_id)
        project.character_sheet_path = stored
        project.updated_at = now()
        session.add(project)
        session.flush()
        data = project_json(project, [])
    await broadcast(
        project_id,
        {
            "type": "PROJECT_UPDATE",
            "projectId": project_id,
            "data": {"characterSheetUrl": data["characterSheetUrl"], "updatedAt": data["updatedAt"]},
        },
    )
    return {"characterSheetUrl": data["characterSheetUrl"]}


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
