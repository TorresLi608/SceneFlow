from __future__ import annotations

import asyncio
import base64
import logging
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import update
from sqlmodel import Session, select

from app.core.database import db
from app.core.realtime import broadcast
from app.api.deps import current_user_id
from app.llms.registry import models
from app.models import Episode, Project, Scene
from app.schemas.requests import (
    CreateSceneRequest,
    CreateProjectRequest,
    GenerateCoverRequest,
    GenerateProjectRequest,
    GenerateVideoRequest,
    OptimizeDescriptionRequest,
    OptimizeProjectRequest,
    ParseProjectRequest,
    ProductionSettingsRequest,
    ReorderScenesRequest,
    SetProjectCoverRequest,
    UpdateProjectRequest,
    UpdateSceneRequest,
)
from app.schemas.serializers import episode_summary_json, project_json, scene_json
from app.services.artifact_service import decode_image_data_url, store_artifact
from app.services.config_service import active_model_config
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
from app.services.prompt_service import SYNOPSIS_SYSTEM, cover_prompt, synopsis_prompt
from app.services.project_service import (
    IDLE_STATUSES,
    claim_project_status,
    owned_project,
    prepare_parse,
    production_settings,
    release_project_status,
    scenes_with_assets,
)
from app.services.usage_service import record_usage, require_model_balance
from app.services.video_service import resolve_video_options
from app.utils.common import new_id, now


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _settings_payload(request: ProductionSettingsRequest) -> dict[str, Any]:
    """Only the fields the caller actually sent, so a PATCH keeps the rest untouched."""
    return request.model_dump(by_alias=True, exclude_unset=True, exclude_none=True)


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
    for scene in scenes:
        payload = scene.model_dump()
        payload["style_prompt"] = project.style_prompt
        payload["negative_prompt"] = project.negative_prompt
        payload["characters"] = [
            cast[character_id].as_payload() for character_id in links.get(scene.id, []) if character_id in cast
        ]
        # The speaker need not be on screen, so it is resolved independently of the cast.
        speaker = cast.get(scene.speaker_character_id or "")
        payload["speaker"] = speaker.as_payload() if speaker else None
        payloads.append(payload)
    return payloads


def _selected_scenes(scenes: list[Scene], scene_ids: list[str] | None) -> list[Scene]:
    if scene_ids is None:
        return [scene for scene in scenes if not scene.is_locked]
    requested = {scene_id.strip() for scene_id in scene_ids if scene_id.strip()}
    selected = [scene for scene in scenes if scene.id in requested]
    if len(selected) != len(requested):
        raise HTTPException(400, "sceneIds must belong to the selected episode")
    if any(scene.is_locked for scene in selected):
        raise HTTPException(400, "unlock selected scenes before generating them")
    return selected


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
    if body.original_script is not None:
        updates["original_script"] = body.original_script
        broadcast_data["originalScript"] = body.original_script
    if body.series_bible is not None:
        updates["series_bible"] = body.series_bible
        broadcast_data["seriesBible"] = body.series_bible
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


# These two literal paths must stay above the `/{project_id}/...` routes below. FastAPI
# matches in declaration order, so moving them down would let `/{project_id}/generate` and
# `/{project_id}/optimize` swallow them with project_id="cover"/"description".
@router.post("/cover/generate")
async def generate_cover(body: GenerateCoverRequest, user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    """Draw a cover and hand the bytes back as a data URL, without touching any project.

    Synchronous like the character portrait it mirrors: it is one image, and the dialog the
    user is looking at is the only thing waiting on it.
    """
    if not (body.title.strip() or body.description.strip()):
        raise HTTPException(400, "name the project or write a synopsis before generating a cover")
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
            cover_prompt(body.title, body.description, body.style_prompt),
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


@router.post("/description/optimize")
async def optimize_description(
    body: OptimizeDescriptionRequest,
    user_id: int = Depends(current_user_id),
) -> dict[str, Any]:
    """Polish a synopsis and return it. Never saved — the user confirms the rewrite first."""
    with db() as session:
        config = active_model_config(session, user_id, "script", "项目简介优化")
        require_model_balance(session, user_id, config)
    started_at = time.monotonic()
    try:
        result = await models.complete_text(
            config["provider"],
            config["apiKey"],
            body.model or config["model"],
            SYNOPSIS_SYSTEM,
            synopsis_prompt(body.title, body.description),
            config.get("baseUrl", ""),
        )
    except Exception as exc:
        logger.warning("description optimize failed user=%s: %s", user_id, exc)
        raise HTTPException(502, f"failed to optimize description: {str(exc)[:220]}") from exc
    record_usage(user_id, config, "description_optimize", started_at, result.usage)
    return {"description": result.text[:4000]}


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
            duration_ms=body.duration_ms or 0,
            subtitle_text=body.subtitle_text or "",
            is_locked=bool(body.is_locked),
        )
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
        pending = _selected_scenes(scenes, body.scene_ids)
        if not pending:
            raise HTTPException(400, "every scene in this episode is locked, unlock one to regenerate")
        config = active_model_config(session, user_id, "image", "分镜图片生成")
        require_model_balance(session, user_id, config)
        # The lock stays on the project: one run owns the series, so a second episode
        # cannot start rendering into the same worker pool while this one is going.
        claim_project_status(session, project_id, allowed_from=IDLE_STATUSES, to="generating")
        episode_id = episode.id
        touch_episode(session, episode, status="generating")
        scene_payloads = _scene_payloads(session, project, episode.episode_number, pending)
    await broadcast(
        project_id,
        {"type": "PROJECT_UPDATE", "projectId": project_id, "data": {"status": "generating", "episodeId": episode_id}},
    )
    asyncio.create_task(run_generation(project_id, scene_payloads, config, user_id, episode_id=episode_id))
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
        config = active_model_config(session, user_id, "video", "视频生成")
        require_model_balance(session, user_id, config)
        model = (body.model or config["model"]).strip()
        if model != config["model"]:
            raise HTTPException(400, "selected video model is not the active video configuration")
        try:
            quality, resolution, fps, duration, prompt_extend = resolve_video_options(
                body.model_dump(by_alias=True, exclude_none=True), config["videoCapabilities"]
            )
        except (TypeError, ValueError) as exc:
            raise HTTPException(400, str(exc)[:220]) from exc
        pending = _selected_scenes(scenes, body.scene_ids)
        if not pending:
            raise HTTPException(400, "every scene video in this episode is locked")
        if config["videoCapabilities"]["referenceImagesRequired"] and not any(scene.image_path for scene in pending):
            raise HTTPException(400, "selected video model requires storyboard images, generate them first")
        voice_sheet_path = None
        if body.with_audio:
            # Refused rather than downgraded: the user opted into a costlier render for a
            # reason, and silently dropping the audio would bill them for something else.
            if not config["videoCapabilities"]["drivingAudio"]:
                raise HTTPException(400, "selected video model does not accept audio, turn withAudio off")
            if not project.voice_sheet_path:
                raise HTTPException(400, "merge the project's voices before rendering with audio")
            voice_sheet_path = project.voice_sheet_path
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
        scene_payloads = _scene_payloads(session, project, episode.episode_number, pending)
    await broadcast(
        project_id,
        {
            "type": "PROJECT_UPDATE",
            "projectId": project_id,
            "data": {"status": "video_generating", "videoStatus": "generating", "videoModel": model},
        },
    )
    asyncio.create_task(
        run_video_generation(
            project_id,
            scene_payloads,
            config,
            user_id,
            episode_id,
            {
                "quality": quality,
                "resolution": resolution,
                "fps": fps,
                "duration": duration,
                "promptExtend": prompt_extend,
                "voiceSheetPath": voice_sheet_path,
            },
        )
    )
    return {
        "projectId": project_id,
        "episodeId": episode_id,
        "status": "video_generating",
        "model": model,
        "sceneCount": len(scene_payloads),
        "withAudio": bool(voice_sheet_path),
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
