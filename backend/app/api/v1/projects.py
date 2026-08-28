from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import update
from sqlmodel import Session, select

from app.core.database import db
from app.core.realtime import broadcast
from app.core import runs
from app.api.deps import current_user_id
from app.llms.registry import models
from app.models import Episode, Project, Scene
from app.schemas.requests import (
    CreateSceneRequest,
    CreateProjectRequest,
    GenerateCoverRequest,
    GenerateProjectRequest,
    GenerateVideoRequest,
    GenerationReferenceKind,
    OptimizeProjectRequest,
    ParseProjectRequest,
    ProductionSettingsRequest,
    ProjectModelConfigRequest,
    ReorderScenesRequest,
    SetProjectCoverRequest,
    UpdateProjectRequest,
    UpdateSceneRequest,
)
from app.schemas.serializers import episode_summary_json, project_json, scene_json
from app.services.artifact_service import decode_image_data_url, remove_stored_artifacts, store_artifact
from app.services.config_service import (
    PROJECT_CONFIG_COLUMNS,
    active_model_config,
    project_model_config,
)
from app.services.character_service import cast_for_episode, owned_character, scene_cast
from app.services.episode_service import (
    ensure_episode,
    episode_scenes,
    episodes_by_project,
    episodes_for,
    resolve_episode,
    scene_counts,
    touch_episode,
)
from app.services.generation_service import run_generation, run_video_generation
from app.services.job_service import list_project_jobs
from app.services.prompt_service import cover_prompt
from app.services.project_service import (
    IDLE_STATUSES,
    claim_project_status,
    owned_project,
    prepare_parse,
    production_settings,
    release_project_status,
    scenes_with_assets,
    selected_scenes,
)
from app.services.reference_service import clear_generation_reference, resolve_generation_references, stored_generation_references
from app.services.usage_service import record_usage, require_model_balance
from app.services.video_service import resolve_video_options, supported_video_defaults, validate_video_reference_counts
from app.utils.common import new_id, now


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _settings_payload(request: ProductionSettingsRequest) -> dict[str, Any]:
    """Only the fields the caller actually sent, so a PATCH keeps the rest untouched."""
    return request.model_dump(by_alias=True, exclude_unset=True, exclude_none=True)


def _model_settings_updates(request: ProjectModelConfigRequest) -> dict[str, Any]:
    """Column updates for the model panel, translating "clear" back into NULL.

    A config id of `0` is how a client returns a purpose to the account default: `null`
    already means "leave alone" in a PATCH, so the clear needs a value of its own.
    """
    sent = request.model_dump(exclude_unset=True, exclude_none=True)
    updates: dict[str, Any] = {}
    for column, value in sent.items():
        if column in PROJECT_CONFIG_COLUMNS.values():
            updates[column] = value or None
        else:
            updates[column] = value
    return updates


def _serialized(session: Session, project: Project, *, episode: Episode | None = None) -> dict[str, Any]:
    """Serialize a series around one episode: its shots, plus a summary of its siblings."""
    target = episode or ensure_episode(session, project.id)
    counts = scene_counts(session, [project.id])
    scenes = episode_scenes(session, target.id)
    cast = scene_cast(session, [scene.id for scene in scenes])
    return project_json(
        project,
        scenes,
        cast=cast,
        episodes=[episode_summary_json(item, counts.get(item.id, 0)) for item in episodes_for(session, project.id)],
        current_episode_id=target.id,
    )


def _scene_payloads(
    session: Session,
    project: Project,
    episode_number: int,
    scenes: list[Scene],
) -> list[dict[str, Any]]:
    """Scene rows plus the cast as it stands in this episode, ready for a background run.

    Resolved here rather than in the worker: variants depend on the episode number, the
    project's house style lives on a row the worker cannot read, and the task runs after
    this session closes.
    """
    cast = cast_for_episode(session, project.id, episode_number)
    links = scene_cast(session, [scene.id for scene in scenes])
    payloads = []
    for index, scene in enumerate(scenes):
        payload = scene.model_dump()
        payload["style_prompt"] = project.style_prompt
        payload["negative_prompt"] = project.negative_prompt
        payload["characters"] = [
            cast[character_id].as_payload() for character_id in links.get(scene.id, []) if character_id in cast
        ]
        # The speaker need not be on screen, so it is resolved independently of the cast.
        # When the editor has no speaker field, infer the common `角色：台词` form at
        # generation time; old rows and newly typed dialogue both keep working.
        speaker_id = scene.speaker_character_id
        if not speaker_id and scene.dialogue:
            match = re.match(r"^\s*([^：:]{1,40})\s*[：:]", scene.dialogue)
            if match:
                speaker_id = breakdown_service.resolve_speaker(session, project.id, match.group(1))
        speaker = cast.get(speaker_id or "")
        payload["speaker"] = speaker.as_payload() if speaker else None
        if index:
            previous = scenes[index - 1]
            payload["previous_video_prompt"] = str(
                previous.video_prompt or previous.visual_prompt or previous.narration or ""
            ).strip()
        payload["explicitImageReferences"] = bool(scene.image_references_explicit)
        payload["explicitVideoReferences"] = bool(scene.video_references_explicit)
        default_reference_items = [
            {"kind": "character", "id": character["id"], "label": character["name"], "media": "image"}
            for character in payload["characters"]
            if character.get("reference_image_path")
        ][:4]
        if not scene.image_references_explicit:
            payload["compiledImageReferenceItems"] = default_reference_items
        if not scene.video_references_explicit:
            video_defaults = list(default_reference_items)
            if scene.image_path:
                video_defaults.insert(0, {"kind": "sceneImage", "id": scene.id, "label": f"分镜 {scene.order_num}", "media": "image"})
            payload["compiledVideoReferenceItems"] = video_defaults
        payloads.append(payload)
    return payloads


@router.get("")
def list_projects(user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    """Every series, each carrying its current episode's shots and a summary of the rest.

    Batched rather than serialized one project at a time: a list of series would otherwise
    run two queries per row. A project with no episode yet reads as empty here — creating
    one is a write, and a GET has no business doing that.
    """
    with db() as session:
        projects = list(
            session.exec(
                select(Project)
                .where(Project.user_id == user_id, Project.deleted_at.is_(None))
                .order_by(Project.updated_at.desc())
            ).all()
        )
        project_ids = [project.id for project in projects]
        grouped = episodes_by_project(session, project_ids)
        counts = scene_counts(session, project_ids)
        # Episodes come back ascending, so the last one is the current episode.
        current = {project_id: (items[-1] if items else None) for project_id, items in grouped.items()}
        shots: dict[str, list[Scene]] = {}
        current_ids = [episode.id for episode in current.values() if episode]
        if current_ids:
            for scene in session.exec(
                select(Scene)
                .where(Scene.episode_id.in_(current_ids), Scene.deleted_at.is_(None))
                .order_by(Scene.order_num.asc())
            ).all():
                shots.setdefault(scene.episode_id, []).append(scene)
        cast = scene_cast(session, [scene.id for episode_shots in shots.values() for scene in episode_shots])
        data = [
            project_json(
                project,
                shots.get(current[project.id].id, []) if current.get(project.id) else [],
                cast=cast,
                episodes=[
                    episode_summary_json(episode, counts.get(episode.id, 0))
                    for episode in grouped.get(project.id, [])
                ],
                current_episode_id=current[project.id].id if current.get(project.id) else None,
            )
            for project in projects
        ]
    return {"projects": data}


@router.post("", status_code=201)
def create_project(body: CreateProjectRequest, user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    stamp = now()
    settings = production_settings(_settings_payload(body.production_settings), defaults=True)
    with db() as session:
        project = Project(
            id=new_id("proj"),
            created_at=stamp,
            updated_at=stamp,
            user_id=user_id,
            title=body.title or "新项目",
            description=body.description,
            cover_prompt=body.cover_prompt,
            original_script=body.original_script,
            status="idle",
            video_status="idle",
            video_progress=0,
            **settings,
        )
        session.add(project)
        session.flush()
        # A series with no episode can hold no shots, so episode 1 exists from the start
        # rather than appearing on whichever write happens to need it first.
        episode = ensure_episode(session, project.id)
        return {"project": _serialized(session, project, episode=episode)}


@router.patch("/{project_id}")
async def update_project(project_id: str, body: UpdateProjectRequest, user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    broadcast_data: dict[str, Any] = {}
    if body.title is not None:
        updates["title"] = body.title or "未命名项目"
        broadcast_data["title"] = updates["title"]
    if body.description is not None:
        updates["description"] = body.description
        broadcast_data["description"] = body.description
    if body.cover_prompt is not None:
        updates["cover_prompt"] = body.cover_prompt
        broadcast_data["coverPrompt"] = body.cover_prompt
    if body.original_script is not None:
        updates["original_script"] = body.original_script
        broadcast_data["originalScript"] = body.original_script
    if body.series_bible is not None:
        updates["series_bible"] = body.series_bible
        broadcast_data["seriesBible"] = body.series_bible
    if body.model_settings is not None:
        updates.update(_model_settings_updates(body.model_settings))
    if not updates:
        raise HTTPException(400, "no fields to update")

    stamp = now()
    with db() as session:
        project = owned_project(session, project_id, user_id)
        for key, value in updates.items():
            setattr(project, key, value)
        project.updated_at = stamp
        session.add(project)
        session.flush()
        data = _serialized(session, project)
    if body.model_settings is not None:
        # The whole block rather than the changed keys: the panel re-reads it as one unit,
        # and a partial payload would leave the other fields showing stale values.
        broadcast_data["modelSettings"] = data["modelSettings"]
    # camelCase on the wire: every other realtime payload is camelCase, and the client reads it directly.
    await broadcast(project_id, {"type": "PROJECT_UPDATE", "projectId": project_id, "data": {**broadcast_data, "updatedAt": stamp}})
    return {"project": data}


@router.patch("/{project_id}/production-settings")
async def update_production_settings(
    project_id: str,
    body: ProductionSettingsRequest,
    user_id: int = Depends(current_user_id),
) -> dict[str, Any]:
    payload = _settings_payload(body)
    if not payload:
        raise HTTPException(400, "no production settings to update")
    stamp = now()
    with db() as session:
        project = owned_project(session, project_id, user_id)
        updates = production_settings(
            {
                "mode": project.mode,
                "aspectRatio": project.aspect_ratio,
                "width": project.width,
                "height": project.height,
                "fps": project.fps,
                "targetDurationMs": project.target_duration_ms,
                "language": project.language,
                "stylePrompt": project.style_prompt,
                "negativePrompt": project.negative_prompt,
                "currentStage": project.current_stage,
                **payload,
            },
            defaults=True,
        )
        for key, value in updates.items():
            setattr(project, key, value)
        project.updated_at = stamp
        session.add(project)
        session.flush()
        serialized = _serialized(session, project)
    data = {
        "productionSettings": serialized["productionSettings"],
        "currentStage": serialized["currentStage"],
        "updatedAt": stamp,
    }
    await broadcast(project_id, {"type": "PROJECT_UPDATE", "projectId": project_id, "data": data})
    return {"project": serialized}


# This literal path must stay above the `/{project_id}/...` routes below. FastAPI matches
# in declaration order, so moving it down would let `/{project_id}/generate` swallow it
# with project_id="cover".
@router.post("/cover/generate")
async def generate_cover(body: GenerateCoverRequest, user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    """Draw a cover and hand the bytes back as a data URL, without touching any project.

    Synchronous like the character portrait it mirrors: it is one image, and the dialog the
    user is looking at is the only thing waiting on it.

    Driven by the user's own description of the picture. It used to be drawn from the title
    and synopsis, which meant the only way to change the cover was to rewrite the story.
    """
    if not body.prompt.strip():
        raise HTTPException(400, "describe the cover before generating it")
    with db() as session:
        config = active_model_config(session, user_id, "image", "项目封面")
        require_model_balance(session, user_id, config)
    if config["provider"] not in {"openai", "gemini", "qwen"}:
        raise HTTPException(400, "image generation currently only supports provider openai/gemini/qwen")

    started_at = time.monotonic()
    try:
        image = await models.generate_image(
            config["apiKey"],
            config["model"],
            cover_prompt(body.prompt, body.title, body.style_prompt),
            base_url=config.get("baseUrl", ""),
            provider=config["provider"],
        )
    except Exception as exc:
        logger.warning("cover generation failed user=%s: %s", user_id, exc)
        raise HTTPException(502, f"failed to generate cover: {str(exc)[:220]}") from exc
    record_usage(user_id, config, "project_cover", started_at, quantity=1)
    extension = (image.format or "png").lower()
    media_type = "image/jpeg" if extension in {"jpg", "jpeg"} else f"image/{extension}"
    encoded = base64.b64encode(image.data).decode("ascii")
    return {"imageData": f"data:{media_type};base64,{encoded}"}


@router.put("/{project_id}/cover")
async def set_project_cover(
    project_id: str,
    body: SetProjectCoverRequest,
    user_id: int = Depends(current_user_id),
) -> dict[str, Any]:
    """Store a cover, whether the user uploaded it or `POST /cover/generate` drew it."""
    with db() as session:
        owned_project(session, project_id, user_id)
    try:
        data, _, extension = decode_image_data_url(body.image_data)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    stored = store_artifact("covers", project_id, f"{project_id}.{extension}", data)
    stamp = now()
    with db() as session:
        project = owned_project(session, project_id, user_id)
        project.cover_image_path = stored
        project.updated_at = stamp
        session.add(project)
        session.flush()
        serialized = _serialized(session, project)
    await broadcast(
        project_id,
        {
            "type": "PROJECT_UPDATE",
            "projectId": project_id,
            "data": {"coverImageUrl": serialized["coverImageUrl"], "updatedAt": stamp},
        },
    )
    return {"project": serialized}


@router.delete("/{project_id}/cover")
async def clear_project_cover(project_id: str, user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    """Drop the cover so the card falls back to the placeholder. The file is left on disk."""
    stamp = now()
    with db() as session:
        project = owned_project(session, project_id, user_id)
        project.cover_image_path = None
        project.updated_at = stamp
        session.add(project)
        session.flush()
        data = _serialized(session, project)
    await broadcast(
        project_id,
        {"type": "PROJECT_UPDATE", "projectId": project_id, "data": {"coverImageUrl": None, "updatedAt": stamp}},
    )
    return {"project": data}


@router.get("/{project_id}/jobs")
def list_jobs(project_id: str, user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    with db() as session:
        jobs = list_project_jobs(session, user_id, project_id)
    return {"jobs": jobs}


# What the UI needs to show a model picker and enforce its limits, per purpose. Resolution
# is the same one generation uses, so what the panel displays is what a render will do.
MODEL_PURPOSES = (("text", "script"), ("image", "image"), ("video", "video"), ("audio", "audio"))
# The ratios and resolutions the image path accepts. Video carries its own declared
# capabilities per config; images only vary by how many references the model takes.
IMAGE_RESOLUTIONS = ("1K", "2K", "4K")
IMAGE_RATIOS = ("auto", "1:1", "2:3", "3:2", "3:4", "4:3", "16:9", "9:16", "21:9", "9:21")


def _model_summary(config: dict[str, Any] | None, purpose: str) -> dict[str, Any] | None:
    """One resolved model, with its limits and without its credentials."""
    if config is None:
        return None
    summary: dict[str, Any] = {
        "provider": config["provider"],
        "model": config["model"],
        "source": config.get("source", ""),
        "configId": config.get("configId") or config.get("officialConfigId"),
        "isProjectPick": bool(config.get("isProjectPick")),
    }
    if purpose == "image":
        summary["capabilities"] = {
            "maxReferenceImages": config.get("imageMaxReferenceImages", 4),
            "resolutions": list(IMAGE_RESOLUTIONS),
            "ratios": list(IMAGE_RATIOS),
        }
    elif purpose == "video":
        summary["capabilities"] = config.get("videoCapabilities")
    return summary


@router.get("/{project_id}/models")
def project_models(project_id: str, user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    """The four models this series will actually use, and what each one accepts.

    Resolved rather than merely echoed back: a project that has pinned nothing still needs
    the panel to say which account default it is falling through to, and a pinned config
    that was since deleted needs to show the fallback rather than a dangling id.

    A purpose with nothing configured anywhere resolves to `null` instead of raising — the
    panel exists partly to tell the user that, and a 400 would leave it blank instead.
    """
    with db() as session:
        project = owned_project(session, project_id, user_id)
        resolved: dict[str, Any] = {}
        for key, purpose in MODEL_PURPOSES:
            try:
                config = project_model_config(session, user_id, project, purpose, "项目模型配置")
            except HTTPException:
                config = None
            resolved[key] = _model_summary(config, purpose)
        settings = _serialized(session, project)["modelSettings"]
    return {"models": resolved, "modelSettings": settings}


@router.post("/{project_id}/cancel")
async def cancel_project_run(project_id: str, user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    """Ask whatever this project is rendering to stop after the shot in flight.

    Cooperative rather than an interrupt: the run polls the flag between shots, so work the
    provider has already been paid for is kept and the run still reports a terminal status.
    See `app/core/runs.py`.

    Releasing the busy lock is left to the run itself. Clearing it here would let a second
    render start while the first is still unwinding, and both would write the same rows.
    """
    with db() as session:
        project = owned_project(session, project_id, user_id)
        status = project.status or "idle"
    requested = runs.cancel(project_id)
    if not requested and status in IDLE_STATUSES:
        # Nothing to stop. Not an error: the user clicked 停止 on a run that just finished.
        return {"projectId": project_id, "canceled": False, "status": status}
    return {"projectId": project_id, "canceled": requested, "status": status}


@router.patch("/{project_id}/scenes/reorder")
async def reorder_project_scenes(project_id: str, body: ReorderScenesRequest, user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    scene_ids = [item.strip() for item in body.scene_ids if item.strip()]
    if not scene_ids:
        raise HTTPException(400, "sceneIds is required")
    stamp = now()
    with db() as session:
        project = owned_project(session, project_id, user_id)
        episode = resolve_episode(session, project_id, body.episode_id)
        by_id = {scene.id: scene for scene in episode_scenes(session, episode.id)}
        # Order numbers restart each episode, so a partial list would renumber shots the
        # caller never saw. The set has to match the episode exactly.
        if set(scene_ids) != set(by_id):
            raise HTTPException(400, "sceneIds must match the episode's current scenes")
        for index, scene_id in enumerate(scene_ids, start=1):
            scene = by_id[scene_id]
            scene.order_num = index
            scene.updated_at = stamp
            session.add(scene)
        project.updated_at = stamp
        session.add(project)
        session.flush()
        data = _serialized(session, project, episode=episode)
    await broadcast(project_id, {"type": "PROJECT_UPDATE", "projectId": project_id, "data": {"updatedAt": stamp}})
    return {"project": data}


# Request field -> column, for the fields a client may edit directly. Anything absent here
# is owned by the pipeline (asset paths, statuses) and is not writable over PATCH.
_SCENE_COLUMNS = (
    ("narration", "narration"),
    ("dialogue", "dialogue"),
    ("speaker_character_id", "speaker_character_id"),
    ("visual_prompt", "visual_prompt"),
    ("shot_type", "shot_type"),
    ("camera_move", "camera_move"),
    ("transition", "transition"),
    ("video_prompt", "video_prompt"),
    ("duration_ms", "duration_ms"),
    ("subtitle_text", "subtitle_text"),
    ("is_locked", "is_locked"),
)


@router.patch("/{project_id}/scenes/{scene_id}")
async def update_project_scene(project_id: str, scene_id: str, body: UpdateSceneRequest, user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    # exclude_unset, not "is not None": clearing a field to "" or unlocking a shot are both
    # real edits, and only an absent key means "leave it alone".
    sent = body.model_dump(exclude_unset=True)
    updates = {column: sent[field] for field, column in _SCENE_COLUMNS if field in sent and sent[field] is not None}
    for field, column in (("image_references", "image_references_json"), ("video_references", "video_references_json")):
        if field in sent and sent[field] is not None:
            updates[column] = json.dumps(
                [{"kind": item["kind"], "id": item["id"]} for item in sent[field]], separators=(",", ":")
            )
            updates[f"{field}_explicit"] = True
    if not updates:
        raise HTTPException(400, "no fields to update")
    # "Nobody in particular" arrives as an empty string, because a JSON null would be
    # indistinguishable from an absent field above. The column stores it as NULL.
    if updates.get("speaker_character_id") == "":
        updates["speaker_character_id"] = None

    stamp = now()
    with db() as session:
        project = owned_project(session, project_id, user_id)
        scene = session.exec(
            select(Scene).where(Scene.id == scene_id, Scene.project_id == project_id, Scene.deleted_at.is_(None))
        ).first()
        if not scene:
            raise HTTPException(404, "scene not found")
        for field in ("image_references", "video_references"):
            if field not in sent or sent[field] is None:
                continue
            resolved = resolve_generation_references(
                session, project_id, [(item["kind"], item["id"]) for item in sent[field]]
            )
            if field == "image_references" and (resolved["videos"] or resolved["audios"]):
                raise HTTPException(400, "image prompts only accept image references")
        speaker_id = updates.get("speaker_character_id")
        if speaker_id:
            # A speaker from another show would silently resolve to no voice at render time.
            owned_character(session, project_id, speaker_id)
        for key, value in updates.items():
            setattr(scene, key, value)
        scene.updated_at = stamp
        project.updated_at = stamp
        session.add(scene)
        session.add(project)
        session.flush()
        data = scene_json(scene)
    await broadcast(
        project_id,
        {
            "type": "SCENE_UPDATE",
            "projectId": project_id,
            "sceneId": scene_id,
            # Only what changed, in the same camelCase shape the serializer uses.
            "data": {key: data[key] for key in body.model_dump(by_alias=True, exclude_unset=True) if key in data},
        },
    )
    return {"scene": data}


@router.post("/{project_id}/scenes", status_code=201)
async def create_project_scene(
    project_id: str,
    body: CreateSceneRequest,
    user_id: int = Depends(current_user_id),
) -> dict[str, Any]:
    stamp = now()
    with db() as session:
        project = owned_project(session, project_id, user_id)
        if (project.status or "idle") not in IDLE_STATUSES:
            raise HTTPException(409, "project is busy, cannot add a scene right now")
        episode = resolve_episode(session, project_id, body.episode_id)
        if body.speaker_character_id:
            owned_character(session, project_id, body.speaker_character_id)
        scene = Scene(
            id=new_id("scene"),
            created_at=stamp,
            updated_at=stamp,
            project_id=project_id,
            episode_id=episode.id,
            order_num=len(episode_scenes(session, episode.id)) + 1,
            narration=body.narration or "",
            dialogue=body.dialogue or "",
            speaker_character_id=body.speaker_character_id or None,
            visual_prompt=body.visual_prompt or "",
            shot_type=body.shot_type or "",
            camera_move=body.camera_move or "",
            transition=body.transition or "",
            video_prompt=body.video_prompt or "",
            image_references_json=json.dumps(
                [{"kind": item.kind, "id": item.id} for item in body.image_references or []], separators=(",", ":")
            ),
            video_references_json=json.dumps(
                [{"kind": item.kind, "id": item.id} for item in body.video_references or []], separators=(",", ":")
            ),
            image_references_explicit=body.image_references is not None,
            video_references_explicit=body.video_references is not None,
            duration_ms=body.duration_ms or 0,
            subtitle_text=body.subtitle_text or "",
            is_locked=bool(body.is_locked),
        )
        for references, image_only in ((body.image_references, True), (body.video_references, False)):
            if references is None:
                continue
            resolved = resolve_generation_references(
                session, project_id, [(item.kind, item.id) for item in references]
            )
            if image_only and (resolved["videos"] or resolved["audios"]):
                raise HTTPException(400, "image prompts only accept image references")
        session.add(scene)
        touch_episode(session, episode, status="storyboard")
        project.updated_at = stamp
        session.add(project)
        session.flush()
        data = scene_json(scene)
    await broadcast(project_id, {"type": "SCENE_UPDATE", "projectId": project_id, "sceneId": scene.id, "data": data})
    return {"scene": data}


@router.delete("/{project_id}/scenes/{scene_id}", status_code=204)
async def delete_project_scene(project_id: str, scene_id: str, user_id: int = Depends(current_user_id)) -> None:
    stamp = now()
    with db() as session:
        project = owned_project(session, project_id, user_id)
        if (project.status or "idle") not in IDLE_STATUSES:
            raise HTTPException(409, "project is busy, cannot delete a scene right now")
        scene = session.exec(
            select(Scene).where(Scene.id == scene_id, Scene.project_id == project_id, Scene.deleted_at.is_(None))
        ).first()
        if not scene:
            return
        scene.deleted_at = stamp
        scene.updated_at = stamp
        session.add(scene)
        session.flush()
        for index, sibling in enumerate(episode_scenes(session, scene.episode_id or ""), start=1):
            sibling.order_num = index
            sibling.updated_at = stamp
            session.add(sibling)
        project.updated_at = stamp
        session.add(project)
    await broadcast(project_id, {"type": "SCENE_DELETED", "projectId": project_id, "sceneId": scene_id})


@router.delete("/{project_id}/references/{kind}/{asset_id}", status_code=204)
async def delete_generation_reference(
    project_id: str,
    kind: GenerationReferenceKind,
    asset_id: str,
    user_id: int = Depends(current_user_id),
) -> None:
    with db() as session:
        project = owned_project(session, project_id, user_id)
        if (project.status or "idle") not in IDLE_STATUSES:
            raise HTTPException(409, "project is busy, cannot delete reference media right now")
        paths = clear_generation_reference(session, project_id, kind, asset_id)
    remove_stored_artifacts(paths)
    await broadcast(
        project_id,
        {"type": "REFERENCE_DELETED", "projectId": project_id, "kind": kind, "assetId": asset_id},
    )


def _replace_scenes(project_id: str, episode_id: str, drafts: list[Any], source_text: str) -> list[Scene]:
    """Swap one episode's storyboard for a freshly parsed one.

    Scoped to the episode, so the rest of the series is untouched. Any render of this
    episode describes shots that no longer exist, so it is cleared along with them.
    """
    stamp = now()
    with db() as session:
        session.execute(
            update(Project)
            .where(Project.id == project_id)
            .values(status="idle", video_status="idle", video_progress=0, video_url=None, updated_at=stamp),
            execution_options={"synchronize_session": False},
        )
        session.execute(
            update(Episode)
            .where(Episode.id == episode_id)
            .values(
                status="storyboard",
                source_text=source_text,
                video_status="idle",
                video_progress=0,
                video_path=None,
                updated_at=stamp,
            ),
            execution_options={"synchronize_session": False},
        )
        session.execute(
            update(Scene)
            .where(Scene.episode_id == episode_id, Scene.deleted_at.is_(None))
            .values(deleted_at=stamp, updated_at=stamp),
            execution_options={"synchronize_session": False},
        )
        scene_rows = [
            Scene(
                id=new_id("scene"),
                created_at=stamp,
                updated_at=stamp,
                project_id=project_id,
                episode_id=episode_id,
                order_num=index,
                narration=draft.narration,
                visual_prompt=draft.visualPrompt,
                image_status="idle",
                audio_status="idle",
            )
            for index, draft in enumerate(drafts, start=1)
        ]
        session.add_all(scene_rows)
        session.flush()
    return scene_rows


@router.post("/{project_id}/parse")
async def parse_project(project_id: str, body: ParseProjectRequest, user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    if not project_id.strip():
        raise HTTPException(400, "invalid project id")
    with db() as session:
        config = prepare_parse(session, user_id, project_id, body.script)

    await broadcast(project_id, {"type": "PROJECT_UPDATE", "projectId": project_id, "data": {"status": "parsing"}})
    started_at = time.monotonic()
    try:
        result = await models.parse_script(
            config["provider"],
            config["apiKey"],
            body.model or config["model"],
            body.script,
            config.get("baseUrl", ""),
        )
    except Exception as exc:
        logger.warning("script parse failed project=%s: %s", project_id, exc)
        release_project_status(project_id)
        raise HTTPException(502, "failed to parse script: " + str(exc)) from exc
    record_usage(user_id, config, "script_parse", started_at, result.usage)

    with db() as session:
        owned_project(session, project_id, user_id)
        episode = resolve_episode(session, project_id, body.episode_id)
        episode_id = episode.id
        existing = episode_scenes(session, episode_id)
        at_risk = scenes_with_assets(existing)
        # Serialized inside the session: the rows are detached once it closes.
        existing_payload = [scene_json(scene) for scene in existing]

    # Reparsing is destructive: the old flow silently deleted every generated image and voice
    # track. When there is something to lose, hand back a preview and let the user decide.
    if at_risk and not body.replace_all:
        release_project_status(project_id)
        return {
            "projectId": project_id,
            "episodeId": episode_id,
            "status": "idle",
            "source": result.source,
            "warning": result.warning,
            "applied": False,
            "discardsGeneratedScenes": len(at_risk),
            "pendingScenes": [
                {"order": index, "narration": draft.narration, "visualPrompt": draft.visualPrompt}
                for index, draft in enumerate(result.scenes, start=1)
            ],
            "scenes": existing_payload,
        }

    scene_rows = _replace_scenes(project_id, episode_id, result.scenes, body.script)
    for scene in scene_rows:
        await broadcast(
            project_id,
            {
                "type": "SCENE_UPDATE",
                "projectId": project_id,
                "sceneId": scene.id,
                "data": {
                    "episodeId": episode_id,
                    "order": scene.order_num,
                    "narration": scene.narration,
                    "visualPrompt": scene.visual_prompt,
                    "parseStatus": "ready",
                },
            },
        )
    await broadcast(
        project_id,
        {
            "type": "PROJECT_UPDATE",
            "projectId": project_id,
            "data": {
                "status": "idle",
                "episodeId": episode_id,
                "sceneCount": len(scene_rows),
                "source": result.source,
                "warning": result.warning,
            },
        },
    )
    return {
        "projectId": project_id,
        "episodeId": episode_id,
        "status": "idle",
        "source": result.source,
        "warning": result.warning,
        "applied": True,
        "discardsGeneratedScenes": 0,
        "pendingScenes": [],
        "scenes": [scene_json(scene) for scene in scene_rows],
    }


@router.post("/{project_id}/optimize")
async def optimize_project(project_id: str, body: OptimizeProjectRequest, user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    with db() as session:
        project = owned_project(session, project_id, user_id)
        script = (body.script or project.original_script or "").strip()
        if not script:
            raise HTTPException(400, "script is required")
        config = active_model_config(session, user_id, "script", "故事生成/剧本优化")
        require_model_balance(session, user_id, config)
    started_at = time.monotonic()
    try:
        result = await models.optimize_script(
            config["provider"],
            config["apiKey"],
            body.model or config["model"],
            script,
            config.get("baseUrl", ""),
        )
    except Exception as exc:
        logger.warning("script optimize failed project=%s: %s", project_id, exc)
        raise HTTPException(502, "failed to optimize script: " + str(exc)) from exc
    record_usage(user_id, config, "script_optimize", started_at, result.usage)
    with db() as session:
        session.execute(
            update(Project)
            .where(Project.id == project_id)
            .values(original_script=result.optimizedScript, updated_at=now()),
            execution_options={"synchronize_session": False},
        )
    await broadcast(
        project_id,
        {
            "type": "PROJECT_UPDATE",
            "projectId": project_id,
            "data": {"optimizedScript": result.optimizedScript, "warning": result.warning},
        },
    )
    return {
        "projectId": project_id,
        "optimizedScript": result.optimizedScript,
        "tips": result.tips,
        "source": result.source,
        "warning": result.warning,
        "appliedToProject": True,
    }


@router.post("/{project_id}/generate", status_code=202)
async def generate_project(project_id: str, body: GenerateProjectRequest, user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    with db() as session:
        project = owned_project(session, project_id, user_id)
        episode = resolve_episode(session, project_id, body.episode_id)
        scenes = episode_scenes(session, episode.id)
        if not scenes:
            raise HTTPException(400, "no scenes available, parse script first")
        # A locked shot is one the user approved; a batch rerun leaves it alone.
        pending = selected_scenes(
            scenes, body.scene_ids, status_column="image_status", pending_only=body.pending_only
        )
        config = project_model_config(session, user_id, project, "image", "分镜图片生成")
        require_model_balance(session, user_id, config)
        # The lock stays on the project: one run owns the series, so a second episode
        # cannot start rendering into the same worker pool while this one is going.
        claim_project_status(session, project_id, allowed_from=IDLE_STATUSES, to="generating")
        episode_id = episode.id
        touch_episode(session, episode, status="generating")
        scene_payloads = _scene_payloads(session, project, episode.episode_number, pending)
        maximum = max(0, int(config.get("imageMaxReferenceImages", 4)))
        for payload in scene_payloads:
            pairs = stored_generation_references(payload.get("image_references_json"))
            if not pairs:
                continue
            resolved = resolve_generation_references(session, project_id, pairs)
            if resolved["videos"] or resolved["audios"]:
                raise HTTPException(400, "image prompts only accept image references")
            if len(resolved["images"]) > maximum:
                raise HTTPException(400, f"selected image model accepts at most {maximum} reference images")
            payload["referenceImagePaths"] = [stored for stored, _ in resolved["images"]]
            payload["compiledImageReferenceItems"] = resolved["items"]
            payload["explicitReferences"] = True
    await broadcast(
        project_id,
        {"type": "PROJECT_UPDATE", "projectId": project_id, "data": {"status": "generating", "episodeId": episode_id}},
    )
    cancellation = runs.register(project_id)
    task = asyncio.create_task(
        run_generation(project_id, scene_payloads, config, user_id, episode_id=episode_id, cancellation=cancellation)
    )
    runs.attach_task(project_id, cancellation, task)
    return {
        "projectId": project_id,
        "episodeId": episode_id,
        "status": "generating",
        "model": body.model or config["model"],
        "provider": config["provider"],
        "sceneCount": len(scene_payloads),
    }


@router.post("/{project_id}/generate-video", status_code=202)
async def generate_video(project_id: str, body: GenerateVideoRequest, user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    with db() as session:
        project = owned_project(session, project_id, user_id)
        episode = resolve_episode(session, project_id, body.episode_id)
        scenes = episode_scenes(session, episode.id)
        if not scenes:
            raise HTTPException(400, "no scenes available, parse script first")
        config = project_model_config(session, user_id, project, "video", "视频生成")
        require_model_balance(session, user_id, config)
        model = (body.model or config["model"]).strip()
        if model != config["model"]:
            raise HTTPException(400, "selected video model is not the active video configuration")
        try:
            # A project can outlive its selected model. Keep only saved defaults the current
            # model supports; explicit request values still go through strict validation.
            capabilities = config["videoCapabilities"]
            quality, aspect_ratio, fps, duration, prompt_extend = resolve_video_options(
                {
                    **supported_video_defaults(
                        {
                            "quality": project.video_quality,
                            "aspectRatio": project.video_aspect_ratio,
                            "fps": project.video_fps,
                            "duration": project.video_duration,
                            "promptExtend": project.video_prompt_extend,
                        },
                        capabilities,
                    ),
                    **body.model_dump(by_alias=True, exclude_none=True, exclude_unset=True),
                },
                capabilities,
            )
        except (TypeError, ValueError) as exc:
            raise HTTPException(400, str(exc)[:220]) from exc
        pending = selected_scenes(
            scenes, body.scene_ids, status_column="video_status", pending_only=body.pending_only
        )
        if any(not scene.image_path for scene in pending):
            raise HTTPException(400, "generate the storyboard image before generating its video")
        resolved_references = (
            resolve_generation_references(
                session, project_id, [(reference.kind, reference.id) for reference in body.references]
            )
            if body.references is not None
            else {"images": [], "videos": [], "audios": []}
        )
        voice_sheet_path = None
        # An unset `withAudio` means "whatever the project is configured for", and that
        # default must not be able to fail a render: a series that predates the audio
        # panel has the column on but no merged voice sheet. An explicit `true` is still
        # refused rather than downgraded — the user opted into a costlier render for a
        # reason, and silently dropping the audio would bill them for something else.
        explicit_audio = body.with_audio is not None
        with_audio = body.with_audio if explicit_audio else project.video_audio_enabled
        audio_param = capabilities.get("audioParam")
        if with_audio and audio_param is None:
            if explicit_audio:
                raise HTTPException(400, "selected video model does not accept audio, turn withAudio off")
            with_audio = False
        if with_audio and audio_param == "reference_voice":
            if not capabilities["referenceAudio"]:
                if explicit_audio:
                    raise HTTPException(400, "selected video model does not accept audio, turn withAudio off")
                with_audio = False
            elif not project.voice_sheet_path:
                if explicit_audio:
                    raise HTTPException(400, "merge the project's voices before rendering with audio")
                with_audio = False
            else:
                voice_sheet_path = project.voice_sheet_path
        if body.references is not None:
            try:
                for scene in pending:
                    automatic_image = int(bool(capabilities["referenceImages"] and scene.image_path))
                    validate_video_reference_counts(
                        capabilities,
                        automatic_image + len(resolved_references["images"]),
                        len(resolved_references["videos"]),
                        len(resolved_references["audios"]) + int(bool(voice_sheet_path)),
                    )
            except ValueError as exc:
                raise HTTPException(400, str(exc)[:220]) from exc
        scene_payloads = _scene_payloads(session, project, episode.episode_number, pending)
        if body.references is None:
            for payload in scene_payloads:
                pairs = stored_generation_references(payload.get("video_references_json"))
                if not pairs:
                    continue
                resolved = resolve_generation_references(session, project_id, pairs)
                automatic_image = int(bool(capabilities["referenceImages"] and payload.get("image_path")))
                try:
                    validate_video_reference_counts(
                        capabilities,
                        automatic_image + len(resolved["images"]),
                        len(resolved["videos"]),
                        len(resolved["audios"]) + int(bool(voice_sheet_path)),
                    )
                except ValueError as exc:
                    raise HTTPException(400, str(exc)[:220]) from exc
                payload["referenceImagePaths"] = [stored for stored, _ in resolved["images"]]
                payload["referenceVideoPaths"] = resolved["videos"]
                payload["referenceAudioPaths"] = resolved["audios"]
                payload["compiledVideoReferenceItems"] = resolved["items"]
                payload["explicitReferences"] = True
        claim_project_status(
            session,
            project_id,
            allowed_from=IDLE_STATUSES,
            to="video_generating",
            video_status="generating",
            video_progress=0,
        )
        touch_episode(session, episode, status="generating", video_status="generating", video_progress=0)
        episode_id = episode.id
    await broadcast(
        project_id,
        {
            "type": "PROJECT_UPDATE",
            "projectId": project_id,
            "data": {"status": "video_generating", "videoStatus": "generating", "videoModel": model},
        },
    )
    cancellation = runs.register(project_id)
    task = asyncio.create_task(
        run_video_generation(
            project_id,
            scene_payloads,
            config,
            user_id,
            episode_id,
            {
                "quality": quality,
                "aspectRatio": aspect_ratio,
                "fps": fps,
                "duration": duration,
                "promptExtend": prompt_extend,
                "outputAudio": bool(with_audio),
                "voiceSheetPath": voice_sheet_path,
                "referenceImagePaths": [stored for stored, _ in resolved_references["images"]],
                "referenceVideoPaths": resolved_references["videos"],
                "referenceAudioPaths": resolved_references["audios"],
                # Batch references replace the per-shot ones, so the labels compiled into
                # the prompt have to come from the same list.
                "compiledVideoReferenceItems": resolved_references.get("items", []),
                "explicitReferences": body.references is not None,
            },
            cancellation=cancellation,
        )
    )
    runs.attach_task(project_id, cancellation, task)
    return {
        "projectId": project_id,
        "episodeId": episode_id,
        "status": "video_generating",
        "model": model,
        "sceneCount": len(scene_payloads),
        "withAudio": bool(with_audio),
    }


@router.delete("/{project_id}", status_code=204)
async def delete_project(project_id: str, user_id: int = Depends(current_user_id)) -> None:
    with db() as session:
        project = session.exec(select(Project).where(Project.id == project_id, Project.deleted_at.is_(None))).first()
        if not project:
            return
        if project.user_id != user_id:
            raise HTTPException(403, "project does not belong to current user")
        stamp = now()
        project.deleted_at = stamp
        project.updated_at = stamp
        session.add(project)
    await broadcast(project_id, {"type": "PROJECT_DELETED", "projectId": project_id})
