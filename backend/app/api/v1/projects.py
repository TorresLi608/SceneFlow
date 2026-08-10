from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import update
from sqlmodel import select

from app.core.database import db
from app.core.realtime import broadcast
from app.api.deps import current_user_id
from app.llms.registry import models
from app.models import Project, Scene
from app.schemas.requests import (
    CreateProjectRequest,
    GenerateProjectRequest,
    GenerateVideoRequest,
    OptimizeProjectRequest,
    ParseProjectRequest,
    ProductionSettingsRequest,
    ReorderScenesRequest,
    UpdateProjectRequest,
    UpdateSceneRequest,
)
from app.schemas.serializers import project_json, scene_json
from app.services.config_service import active_model_config
from app.services.generation_service import run_generation, run_video_generation
from app.services.job_service import list_project_jobs
from app.services.project_service import (
    IDLE_STATUSES,
    claim_project_status,
    prepare_parse,
    production_settings,
    project_and_scenes,
    release_project_status,
    scenes_with_assets,
)
from app.services.usage_service import record_usage, require_model_balance
from app.utils.common import new_id, now


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _settings_payload(request: ProductionSettingsRequest) -> dict[str, Any]:
    """Only the fields the caller actually sent, so a PATCH keeps the rest untouched."""
    return request.model_dump(by_alias=True, exclude_unset=True, exclude_none=True)


@router.get("")
def list_projects(user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    with db() as session:
        projects = session.exec(
            select(Project)
            .where(Project.user_id == user_id, Project.deleted_at.is_(None))
            .order_by(Project.updated_at.desc())
        ).all()
        data = [
            project_json(
                project,
                list(
                    session.exec(
                        select(Scene)
                        .where(Scene.project_id == project.id, Scene.deleted_at.is_(None))
                        .order_by(Scene.order_num.asc())
                    ).all()
                ),
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
            original_script=body.original_script,
            status="idle",
            video_status="idle",
            video_progress=0,
            **settings,
        )
        session.add(project)
        session.flush()
        return {"project": project_json(project, [])}


@router.patch("/{project_id}")
async def update_project(project_id: str, body: UpdateProjectRequest, user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    broadcast_data: dict[str, Any] = {}
    if body.title is not None:
        updates["title"] = body.title or "未命名项目"
        broadcast_data["title"] = updates["title"]
    if body.original_script is not None:
        updates["original_script"] = body.original_script
        broadcast_data["originalScript"] = body.original_script
    if not updates:
        raise HTTPException(400, "no fields to update")

    stamp = now()
    with db() as session:
        project, scenes = project_and_scenes(session, project_id, user_id)
        for key, value in updates.items():
            setattr(project, key, value)
        project.updated_at = stamp
        session.add(project)
        session.flush()
        data = project_json(project, scenes)
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
        project, scenes = project_and_scenes(session, project_id, user_id)
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
        serialized = project_json(project, scenes)
    data = {
        "productionSettings": serialized["productionSettings"],
        "currentStage": serialized["currentStage"],
        "updatedAt": stamp,
    }
    await broadcast(project_id, {"type": "PROJECT_UPDATE", "projectId": project_id, "data": data})
    return {"project": serialized}


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
        project, scenes = project_and_scenes(session, project_id, user_id)
        by_id = {scene.id: scene for scene in scenes}
        if set(scene_ids) != set(by_id):
            raise HTTPException(400, "sceneIds must match current project scenes")
        for index, scene_id in enumerate(scene_ids, start=1):
            scene = by_id[scene_id]
            scene.order_num = index
            scene.updated_at = stamp
            session.add(scene)
        project.updated_at = stamp
        session.add(project)
        session.flush()
        project, scenes = project_and_scenes(session, project_id, user_id)
        data = project_json(project, scenes)
    await broadcast(project_id, {"type": "PROJECT_UPDATE", "projectId": project_id, "data": {"updatedAt": stamp}})
    return {"project": data}


@router.patch("/{project_id}/scenes/{scene_id}")
async def update_project_scene(project_id: str, scene_id: str, body: UpdateSceneRequest, user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    if body.narration is not None:
        updates["narration"] = body.narration
    if body.visual_prompt is not None:
        updates["visual_prompt"] = body.visual_prompt
    if not updates:
        raise HTTPException(400, "no fields to update")

    stamp = now()
    with db() as session:
        project, _ = project_and_scenes(session, project_id, user_id)
        scene = session.exec(
            select(Scene).where(Scene.id == scene_id, Scene.project_id == project_id, Scene.deleted_at.is_(None))
        ).first()
        if not scene:
            raise HTTPException(404, "scene not found")
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
            "data": {"narration": body.narration, "visualPrompt": body.visual_prompt},
        },
    )
    return {"scene": data}


def _replace_scenes(project_id: str, drafts: list[Any]) -> list[Scene]:
    stamp = now()
    with db() as session:
        session.execute(
            update(Project)
            .where(Project.id == project_id)
            .values(status="idle", video_status="idle", video_progress=0, video_url=None, updated_at=stamp),
            execution_options={"synchronize_session": False},
        )
        session.execute(
            update(Scene)
            .where(Scene.project_id == project_id, Scene.deleted_at.is_(None))
            .values(deleted_at=stamp, updated_at=stamp),
            execution_options={"synchronize_session": False},
        )
        scene_rows = [
            Scene(
                id=new_id("scene"),
                created_at=stamp,
                updated_at=stamp,
                project_id=project_id,
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
        project, existing = project_and_scenes(session, project_id, user_id)
        at_risk = scenes_with_assets(existing)

    # Reparsing is destructive: the old flow silently deleted every generated image and voice
    # track. When there is something to lose, hand back a preview and let the user decide.
    if at_risk and not body.replace_all:
        release_project_status(project_id)
        return {
            "projectId": project_id,
            "status": "idle",
            "source": result.source,
            "warning": result.warning,
            "applied": False,
            "discardsGeneratedScenes": len(at_risk),
            "pendingScenes": [
                {"order": index, "narration": draft.narration, "visualPrompt": draft.visualPrompt}
                for index, draft in enumerate(result.scenes, start=1)
            ],
            "scenes": [scene_json(scene) for scene in existing],
        }

    scene_rows = _replace_scenes(project_id, result.scenes)
    for scene in scene_rows:
        await broadcast(
            project_id,
            {
                "type": "SCENE_UPDATE",
                "projectId": project_id,
                "sceneId": scene.id,
                "data": {
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
            "data": {"status": "idle", "sceneCount": len(scene_rows), "source": result.source, "warning": result.warning},
        },
    )
    return {
        "projectId": project_id,
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
        project, _ = project_and_scenes(session, project_id, user_id)
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
        project, scenes = project_and_scenes(session, project_id, user_id)
        if not scenes:
            raise HTTPException(400, "no scenes available, parse script first")
        config = active_model_config(session, user_id, "image", "分镜图片生成")
        require_model_balance(session, user_id, config)
        try:
            audio_config = active_model_config(session, user_id, "audio", "场景配音")
        except HTTPException:
            audio_config = {"provider": "edge", "model": "zh-CN-XiaoxiaoNeural", "apiKey": "", "baseUrl": "", "source": "builtin"}
        if audio_config["provider"] not in {"edge", "system"}:
            require_model_balance(session, user_id, audio_config)
        claim_project_status(session, project_id, allowed_from=IDLE_STATUSES, to="generating")
        scene_payloads = [scene.model_dump() for scene in scenes]
    await broadcast(project_id, {"type": "PROJECT_UPDATE", "projectId": project_id, "data": {"status": "generating"}})
    asyncio.create_task(run_generation(project_id, scene_payloads, config, audio_config, user_id))
    return {
        "projectId": project_id,
        "status": "generating",
        "model": body.model or config["model"],
        "provider": config["provider"],
        "imageModel": config["model"],
        "sceneCount": len(scene_payloads),
    }


@router.post("/{project_id}/generate-video", status_code=202)
async def generate_video(project_id: str, body: GenerateVideoRequest, user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    with db() as session:
        project, scenes = project_and_scenes(session, project_id, user_id)
        if not scenes:
            raise HTTPException(400, "no scenes available, parse script first")
        config = active_model_config(session, user_id, "video", "视频生成")
        require_model_balance(session, user_id, config)
        model = (body.model or config["model"]).strip()
        claim_project_status(
            session,
            project_id,
            allowed_from=IDLE_STATUSES,
            to="video_generating",
            video_status="generating",
            video_progress=0,
        )
    await broadcast(
        project_id,
        {
            "type": "PROJECT_UPDATE",
            "projectId": project_id,
            "data": {"status": "video_generating", "videoStatus": "generating", "videoModel": model},
        },
    )
    asyncio.create_task(run_video_generation(project_id, model))
    return {"projectId": project_id, "status": "video_generating", "model": model}


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
