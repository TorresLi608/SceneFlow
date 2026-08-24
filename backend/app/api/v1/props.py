"""Prop management: the objects a series has to draw the same way every time.

Mirrors `characters.py` step for step — draft a prompt, review it, draw the reference, tile
the results into one sheet — because it is the same problem one level down.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import current_user_id
from app.core.database import db
from app.core.realtime import broadcast
from app.schemas.requests import (
    CreatePropRequest,
    DraftPromptRequest,
    GenerateReferenceImageRequest,
    UpdatePropRequest,
    UploadReferenceImageRequest,
)
from app.schemas.serializers import project_json, prop_json
from app.services.artifact_service import decode_image_data_url, store_artifact
from app.services.character_service import characters_for
from app.services.project_service import owned_project
from app.services.prompt_service import PROP_SYSTEM, fallback_prop_prompt, prop_prompt
from app.services.prop_service import create_prop, delete_prop, owned_prop, props_for
from app.services.reference_service import (
    draft_prompt,
    draw_reference,
    image_config,
    image_options,
    script_config,
    store_sheet,
)
from app.utils.common import now


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects", tags=["props"])


def _owner_names(session, project_id: str) -> dict[str, str]:
    """Character id to name, so a prop card can show whose it is without a second request."""
    return {character.id: character.name for character in characters_for(session, project_id)}


def _prop_payload(session, project_id: str, prop) -> dict[str, Any]:
    return prop_json(prop, _owner_names(session, project_id).get(prop.owner_character_id or "", ""))


@router.get("/{project_id}/props")
def list_props(project_id: str, user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    with db() as session:
        owned_project(session, project_id, user_id)
        owners = _owner_names(session, project_id)
        data = [
            prop_json(prop, owners.get(prop.owner_character_id or "", ""))
            for prop in props_for(session, project_id)
        ]
    return {"props": data}


@router.post("/{project_id}/props", status_code=201)
async def add_prop(
    project_id: str,
    body: CreatePropRequest,
    user_id: int = Depends(current_user_id),
) -> dict[str, Any]:
    with db() as session:
        owned_project(session, project_id, user_id)
        prop = create_prop(
            session,
            project_id,
            name=body.name,
            description=body.description,
            owner_character_id=body.owner_character_id or None,
            final_prompt=body.final_prompt,
            order_num=body.order_num,
        )
        data = _prop_payload(session, project_id, prop)
    await broadcast(project_id, {"type": "PROP_UPDATE", "projectId": project_id, "data": data})
    return {"prop": data}


@router.patch("/{project_id}/props/{prop_id}")
async def update_prop(
    project_id: str,
    prop_id: str,
    body: UpdatePropRequest,
    user_id: int = Depends(current_user_id),
) -> dict[str, Any]:
    # exclude_unset, not "is not None": clearing a prompt is a real edit, and only an absent
    # key means "leave it alone".
    updates = {key: value for key, value in body.model_dump(exclude_unset=True).items() if value is not None}
    if not updates:
        raise HTTPException(400, "no fields to update")

    with db() as session:
        owned_project(session, project_id, user_id)
        prop = owned_prop(session, project_id, prop_id)
        for key, value in updates.items():
            # "" is how a client unbinds the owner; storing it verbatim would leave a
            # falsy-but-present id that never resolves to a name.
            setattr(prop, key, None if key == "owner_character_id" and not value else value)
        prop.updated_at = now()
        session.add(prop)
        session.flush()
        data = _prop_payload(session, project_id, prop)
    await broadcast(project_id, {"type": "PROP_UPDATE", "projectId": project_id, "data": data})
    return {"prop": data}


@router.delete("/{project_id}/props/{prop_id}", status_code=204)
async def remove_prop(project_id: str, prop_id: str, user_id: int = Depends(current_user_id)) -> None:
    with db() as session:
        owned_project(session, project_id, user_id)
        prop = owned_prop(session, project_id, prop_id)
        delete_prop(session, prop)
    await broadcast(project_id, {"type": "PROP_DELETED", "projectId": project_id, "propId": prop_id})


@router.post("/{project_id}/props/{prop_id}/prompt")
async def draft_prop_prompt(
    project_id: str,
    prop_id: str,
    body: DraftPromptRequest,
    user_id: int = Depends(current_user_id),
) -> dict[str, Any]:
    """Draft the image prompt for review. Returned, not saved."""
    with db() as session:
        project = owned_project(session, project_id, user_id)
        prop = owned_prop(session, project_id, prop_id)
        user_text = prop_prompt(
            body.name or prop.name,
            body.description or prop.description,
            _owner_names(session, project_id).get(prop.owner_character_id or "", ""),
            body.preset,
        )
        config = script_config(session, user_id, "道具提示词", project)

    prompt = await draft_prompt(config, user_id, PROP_SYSTEM, user_text, body.model, "prop_prompt")
    return {"propId": prop_id, "prompt": prompt}


@router.post("/{project_id}/props/{prop_id}/image")
async def generate_prop_image(
    project_id: str,
    prop_id: str,
    body: GenerateReferenceImageRequest,
    user_id: int = Depends(current_user_id),
) -> dict[str, Any]:
    with db() as session:
        project = owned_project(session, project_id, user_id)
        prop = owned_prop(session, project_id, prop_id)
        prompt = (body.prompt or prop.final_prompt).strip() or fallback_prop_prompt(
            prop.name,
            prop.description,
            _owner_names(session, project_id).get(prop.owner_character_id or "", ""),
        )
        config = image_config(session, user_id, "道具参考图", project)
        size, quality = image_options(project)

    data, extension = await draw_reference(config, user_id, prompt, "prop_image", size, quality)
    stored = store_artifact("props", project_id, f"{prop_id}.{extension}", data)

    with db() as session:
        owned_project(session, project_id, user_id)
        prop = owned_prop(session, project_id, prop_id)
        prop.image_path = stored
        # Remember what was actually drawn, so a reload shows the prompt behind the image.
        prop.final_prompt = prompt[:4000]
        prop.updated_at = now()
        session.add(prop)
        session.flush()
        data_json = _prop_payload(session, project_id, prop)
    await broadcast(project_id, {"type": "PROP_UPDATE", "projectId": project_id, "data": data_json})
    return {"prop": data_json}


@router.put("/{project_id}/props/{prop_id}/image")
async def upload_prop_image(
    project_id: str,
    prop_id: str,
    body: UploadReferenceImageRequest,
    user_id: int = Depends(current_user_id),
) -> dict[str, Any]:
    try:
        data, _, extension = decode_image_data_url(body.image_data)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    with db() as session:
        owned_project(session, project_id, user_id)
        owned_prop(session, project_id, prop_id)
    stored = store_artifact("props", project_id, f"{prop_id}.{extension}", data)

    with db() as session:
        owned_project(session, project_id, user_id)
        prop = owned_prop(session, project_id, prop_id)
        prop.image_path = stored
        prop.updated_at = now()
        session.add(prop)
        session.flush()
        data_json = _prop_payload(session, project_id, prop)
    await broadcast(project_id, {"type": "PROP_UPDATE", "projectId": project_id, "data": data_json})
    return {"prop": data_json}


@router.post("/{project_id}/props/sheet")
async def merge_prop_sheet(project_id: str, user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    """Tile every prop into one labelled sheet the storyboard render carries."""
    with db() as session:
        owned_project(session, project_id, user_id)
        owners = _owner_names(session, project_id)
        # Labelled with the owner where there is one: an unattributed object in a shared
        # sheet is exactly the ambiguity the owner column exists to remove.
        entries = [
            (
                prop.image_path,
                f"{prop.name} · {owners[prop.owner_character_id]}"
                if prop.owner_character_id in owners
                else prop.name,
            )
            for prop in props_for(session, project_id)
        ]

    stored = store_sheet("props", project_id, f"{project_id}-props.jpg", entries)

    with db() as session:
        project = owned_project(session, project_id, user_id)
        project.prop_sheet_path = stored
        project.updated_at = now()
        session.add(project)
        session.flush()
        data = project_json(project, [])
    await broadcast(
        project_id,
        {
            "type": "PROJECT_UPDATE",
            "projectId": project_id,
            "data": {"propSheetUrl": data["propSheetUrl"], "updatedAt": data["updatedAt"]},
        },
    )
    return {"propSheetUrl": data["propSheetUrl"]}
