from __future__ import annotations

import asyncio
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
from app.schemas.serializers import project_json, scene_json
from app.services.config_service import active_model_config
from app.services.generation_service import run_generation, run_video_generation
from app.services.job_service import list_project_jobs
from app.services.project_service import parse_project_model, production_settings, project_and_scenes
from app.services.usage_service import record_usage, require_model_balance
from app.utils.common import new_id, now


router = APIRouter(prefix="/api/projects", tags=["projects"])


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
def create_project(payload: dict[str, Any], user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    stamp = now()
    settings = production_settings(payload.get("productionSettings", {}), defaults=True)
    with db() as session:
        project = Project(
            id=new_id("proj"),
            created_at=stamp,
            updated_at=stamp,
            user_id=user_id,
            title=str(payload.get("title", "")).strip()[:80] or "新项目",
            original_script=str(payload.get("originalScript", "")).strip(),
            status="idle",
            video_status="idle",
            video_progress=0,
            **settings,
        )
        session.add(project)
        session.flush()
        return {"project": project_json(project, [])}


@router.patch("/{project_id}")
async def update_project(project_id: str, payload: dict[str, Any], user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    stamp = now()
    updates: dict[str, Any] = {}
    if "title" in payload:
        updates["title"] = str(payload["title"]).strip()[:80] or "未命名项目"
    if "originalScript" in payload:
        updates["original_script"] = str(payload["originalScript"])
    if not updates:
        raise HTTPException(400, "no fields to update")

    with db() as session:
        project, scenes = project_and_scenes(session, project_id, user_id)
        for key, value in updates.items():
            setattr(project, key, value)
        project.updated_at = stamp
        session.add(project)
        session.flush()
        data = project_json(project, scenes)
    await broadcast(project_id, {"type": "PROJECT_UPDATE", "projectId": project_id, "data": payload})
    return {"project": data}


@router.patch("/{project_id}/production-settings")
async def update_production_settings(
    project_id: str,
    payload: dict[str, Any],
    user_id: int = Depends(current_user_id),
) -> dict[str, Any]:
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
async def reorder_project_scenes(project_id: str, payload: dict[str, Any], user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    scene_ids = [str(item) for item in payload.get("sceneIds", []) if str(item).strip()]
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
async def update_project_scene(project_id: str, scene_id: str, payload: dict[str, Any], user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    stamp = now()
    updates: dict[str, Any] = {}
    if "narration" in payload:
        updates["narration"] = str(payload["narration"])
    if "visualPrompt" in payload:
        updates["visual_prompt"] = str(payload["visualPrompt"])
    if not updates:
        raise HTTPException(400, "no fields to update")

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
    await broadcast(project_id, {"type": "SCENE_UPDATE", "projectId": project_id, "sceneId": scene_id, "data": payload})
    return {"scene": data}


@router.post("/{project_id}/parse")
async def parse_project(project_id: str, payload: dict[str, Any], user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    if not project_id.strip():
        raise HTTPException(400, "invalid project id")
    with db() as session:
        data = await parse_project_model(session, user_id, project_id, payload)

    await broadcast(project_id, {"type": "PROJECT_UPDATE", "projectId": project_id, "data": {"status": "parsing"}})
    config = data["config"]
    started_at = time.monotonic()
    try:
        result = await models.parse_script(
            config["provider"],
            config["apiKey"],
            str(payload.get("model") or config["model"]),
            data["script"],
            config.get("baseUrl", ""),
        )
    except Exception as exc:
        with db() as session:
            session.execute(
                update(Project).where(Project.id == project_id).values(status="idle", updated_at=now()),
                execution_options={"synchronize_session": False},
            )
        raise HTTPException(502, "failed to parse script: " + str(exc)) from exc
    record_usage(user_id, config, "script_parse", started_at, result.usage)

    stamp = now()
    with db() as session:
        session.execute(
            update(Project)
            .where(Project.id == project_id)
            .values(
                original_script=data["script"],
                status="idle",
                video_status="idle",
                video_progress=0,
                video_url=None,
                updated_at=stamp,
            ),
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
            for index, draft in enumerate(result.scenes, start=1)
        ]
        session.add_all(scene_rows)
        session.flush()

    for scene in scene_rows:
        await broadcast(project_id, {"type": "SCENE_UPDATE", "projectId": project_id, "sceneId": scene.id, "data": {"order": scene.order_num, "narration": scene.narration, "visualPrompt": scene.visual_prompt, "parseStatus": "ready"}})
    await broadcast(project_id, {"type": "PROJECT_UPDATE", "projectId": project_id, "data": {"status": "idle", "sceneCount": len(scene_rows), "source": result.source, "warning": result.warning}})
    return {"projectId": project_id, "status": "idle", "source": result.source, "warning": result.warning, "scenes": [scene_json(scene) for scene in scene_rows]}


@router.post("/{project_id}/optimize")
async def optimize_project(project_id: str, payload: dict[str, Any], user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    with db() as session:
        project, _ = project_and_scenes(session, project_id, user_id)
        script = str(payload.get("script") or project.original_script or "").strip()
        if not script:
            raise HTTPException(400, "script is required")
        config = active_model_config(session, user_id, "script", "故事生成/剧本优化")
        require_model_balance(session, user_id, config)
    started_at = time.monotonic()
    try:
        result = await models.optimize_script(
            config["provider"],
            config["apiKey"],
            str(payload.get("model") or config["model"]),
            script,
            config.get("baseUrl", ""),
        )
    except Exception as exc:
        raise HTTPException(502, "failed to optimize script: " + str(exc)) from exc
    record_usage(user_id, config, "script_optimize", started_at, result.usage)
    with db() as session:
        session.execute(
            update(Project)
            .where(Project.id == project_id)
            .values(original_script=result.optimizedScript, status="idle", updated_at=now()),
            execution_options={"synchronize_session": False},
        )
    await broadcast(project_id, {"type": "PROJECT_UPDATE", "projectId": project_id, "data": {"status": "idle", "optimizedScript": result.optimizedScript, "warning": result.warning}})
    return {"projectId": project_id, "optimizedScript": result.optimizedScript, "tips": result.tips, "source": result.source, "warning": result.warning, "appliedToProject": True}


@router.post("/{project_id}/generate", status_code=202)
async def generate_project(project_id: str, payload: dict[str, Any], user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    with db() as session:
        project, scenes = project_and_scenes(session, project_id, user_id)
        if not scenes:
            raise HTTPException(400, "no scenes available, parse script first")
        if project.status == "generating":
            raise HTTPException(409, "project is already generating")
        config = active_model_config(session, user_id, "image", "分镜图片生成")
        warning = ""
        require_model_balance(session, user_id, config)
        try:
            audio_config = active_model_config(session, user_id, "audio", "场景配音")
        except HTTPException:
            audio_config = {"provider": "edge", "model": "zh-CN-XiaoxiaoNeural", "apiKey": "", "baseUrl": "", "source": "builtin"}
        if audio_config["provider"] not in {"edge", "system"}:
            require_model_balance(session, user_id, audio_config)
        project.status = "generating"
        project.updated_at = now()
        session.add(project)
        scene_payloads = [scene.model_dump() for scene in scenes]
    await broadcast(project_id, {"type": "PROJECT_UPDATE", "projectId": project_id, "data": {"status": "generating"}})
    asyncio.create_task(run_generation(project_id, scene_payloads, config, audio_config, user_id))
    return {"projectId": project_id, "status": "generating", "model": str(payload.get("model") or config["model"]), "provider": config["provider"], "imageModel": config["model"], "warning": warning, "sceneCount": len(scene_payloads)}


@router.post("/{project_id}/generate-video", status_code=202)
async def generate_video(project_id: str, payload: dict[str, Any], user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    with db() as session:
        project, scenes = project_and_scenes(session, project_id, user_id)
        if not scenes:
            raise HTTPException(400, "no scenes available, parse script first")
        if project.status == "video_generating":
            raise HTTPException(409, "project video is already generating")
        config = active_model_config(session, user_id, "video", "视频生成")
        require_model_balance(session, user_id, config)
        model = str(payload.get("model") or config["model"]).strip()
        project.status = "video_generating"
        project.video_status = "generating"
        project.video_progress = 0
        project.updated_at = now()
        session.add(project)
    await broadcast(project_id, {"type": "PROJECT_UPDATE", "projectId": project_id, "data": {"status": "video_generating", "videoStatus": "generating", "videoModel": model}})
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
        project.deleted_at = now()
        project.updated_at = now()
        session.add(project)
    await broadcast(project_id, {"type": "PROJECT_DELETED", "projectId": project_id})
