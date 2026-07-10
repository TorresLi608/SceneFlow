from __future__ import annotations

import asyncio
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from config_service import active_model_config
from database import db, row, rows
from generation_service import run_generation, run_video_generation
from model_registry import models
from project_service import parse_project_model, project_and_scenes
from realtime import broadcast
from security import current_user_id
from serializers import project_json, scene_json
from utils import new_id, now
from usage_service import record_usage


router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("")
def list_projects(user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    with db() as conn:
        projects = rows(
            conn,
            "SELECT * FROM projects WHERE user_id=? AND deleted_at IS NULL ORDER BY updated_at DESC",
            (user_id,),
        )
        data = [
            project_json(
                project,
                rows(conn, "SELECT * FROM scenes WHERE project_id=? AND deleted_at IS NULL ORDER BY order_num ASC", (project["id"],)),
            )
            for project in projects
        ]
    return {"projects": data}


@router.post("", status_code=201)
def create_project(payload: dict[str, Any], user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    stamp = now()
    title = str(payload.get("title", "")).strip()[:80] or "新项目"
    script = str(payload.get("originalScript", "")).strip()
    project_id = new_id("proj")
    with db() as conn:
        conn.execute(
            """INSERT INTO projects
            (id, created_at, updated_at, user_id, title, original_script, status, video_status, video_progress)
            VALUES (?, ?, ?, ?, ?, ?, 'idle', 'idle', 0)""",
            (project_id, stamp, stamp, user_id, title, script),
        )
        project = row(conn, "SELECT * FROM projects WHERE id=?", (project_id,))
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

    with db() as conn:
        project, _ = project_and_scenes(conn, project_id, user_id)
        conn.execute(
            f"UPDATE projects SET {', '.join(f'{key}=?' for key in updates)}, updated_at=? WHERE id=?",
            (*updates.values(), stamp, project["id"]),
        )
        project, scenes = project_and_scenes(conn, project_id, user_id)
    await broadcast(project_id, {"type": "PROJECT_UPDATE", "projectId": project_id, "data": payload})
    return {"project": project_json(project, scenes)}


@router.patch("/{project_id}/scenes/reorder")
async def reorder_project_scenes(project_id: str, payload: dict[str, Any], user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    scene_ids = [str(item) for item in payload.get("sceneIds", []) if str(item).strip()]
    if not scene_ids:
        raise HTTPException(400, "sceneIds is required")
    stamp = now()
    with db() as conn:
        project, scenes = project_and_scenes(conn, project_id, user_id)
        existing_ids = {scene["id"] for scene in scenes}
        if set(scene_ids) != existing_ids:
            raise HTTPException(400, "sceneIds must match current project scenes")
        for index, scene_id in enumerate(scene_ids, start=1):
            conn.execute("UPDATE scenes SET order_num=?, updated_at=? WHERE id=? AND project_id=?", (index, stamp, scene_id, project_id))
        conn.execute("UPDATE projects SET updated_at=? WHERE id=?", (stamp, project["id"]))
        project, scenes = project_and_scenes(conn, project_id, user_id)
    await broadcast(project_id, {"type": "PROJECT_UPDATE", "projectId": project_id, "data": {"updatedAt": stamp}})
    return {"project": project_json(project, scenes)}


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

    with db() as conn:
        project_and_scenes(conn, project_id, user_id)
        scene = row(conn, "SELECT * FROM scenes WHERE id=? AND project_id=? AND deleted_at IS NULL", (scene_id, project_id))
        if not scene:
            raise HTTPException(404, "scene not found")
        conn.execute(
            f"UPDATE scenes SET {', '.join(f'{key}=?' for key in updates)}, updated_at=? WHERE id=? AND project_id=?",
            (*updates.values(), stamp, scene_id, project_id),
        )
        conn.execute("UPDATE projects SET updated_at=? WHERE id=?", (stamp, project_id))
        scene = row(conn, "SELECT * FROM scenes WHERE id=?", (scene_id,))
    await broadcast(project_id, {"type": "SCENE_UPDATE", "projectId": project_id, "sceneId": scene_id, "data": payload})
    return {"scene": scene_json(scene)}


@router.post("/{project_id}/parse")
async def parse_project(project_id: str, payload: dict[str, Any], user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    if not project_id.strip():
        raise HTTPException(400, "invalid project id")
    with db() as conn:
        data = await parse_project_model(conn, user_id, project_id, payload)

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
        with db() as conn:
            conn.execute("UPDATE projects SET status='idle', updated_at=? WHERE id=?", (now(), project_id))
        raise HTTPException(502, "failed to parse script: " + str(exc)) from exc
    record_usage(user_id, config, "script_parse", started_at, result.usage)

    stamp = now()
    with db() as conn:
        conn.execute(
            "UPDATE projects SET original_script=?, status='idle', video_status='idle', video_progress=0, video_url=NULL, updated_at=? WHERE id=?",
            (data["script"], stamp, project_id),
        )
        conn.execute("UPDATE scenes SET deleted_at=?, updated_at=? WHERE project_id=? AND deleted_at IS NULL", (stamp, stamp, project_id))
        scene_rows = []
        for index, draft in enumerate(result.scenes, start=1):
            scene_id = new_id("scene")
            conn.execute(
                """INSERT INTO scenes
                (id, created_at, updated_at, project_id, order_num, narration, visual_prompt, image_status, audio_status)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'idle', 'idle')""",
                (scene_id, stamp, stamp, project_id, index, draft.narration, draft.visualPrompt),
            )
            scene_rows.append(row(conn, "SELECT * FROM scenes WHERE id=?", (scene_id,)))

    for scene in scene_rows:
        await broadcast(project_id, {"type": "SCENE_UPDATE", "projectId": project_id, "sceneId": scene["id"], "data": {"order": scene["order_num"], "narration": scene["narration"], "visualPrompt": scene["visual_prompt"], "parseStatus": "ready"}})
    await broadcast(project_id, {"type": "PROJECT_UPDATE", "projectId": project_id, "data": {"status": "idle", "sceneCount": len(scene_rows), "source": result.source, "warning": result.warning}})
    return {"projectId": project_id, "status": "idle", "source": result.source, "warning": result.warning, "scenes": [scene_json(scene) for scene in scene_rows]}


@router.post("/{project_id}/optimize")
async def optimize_project(project_id: str, payload: dict[str, Any], user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    with db() as conn:
        project, _ = project_and_scenes(conn, project_id, user_id)
        script = str(payload.get("script") or project["original_script"] or "").strip()
        if not script:
            raise HTTPException(400, "script is required")
        config = active_model_config(conn, user_id, "script", "故事生成/剧本优化")
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
    with db() as conn:
        conn.execute("UPDATE projects SET original_script=?, status='idle', updated_at=? WHERE id=?", (result.optimizedScript, now(), project_id))
    await broadcast(project_id, {"type": "PROJECT_UPDATE", "projectId": project_id, "data": {"status": "idle", "optimizedScript": result.optimizedScript, "warning": result.warning}})
    return {"projectId": project_id, "optimizedScript": result.optimizedScript, "tips": result.tips, "source": result.source, "warning": result.warning, "appliedToProject": True}


@router.post("/{project_id}/generate", status_code=202)
async def generate_project(project_id: str, payload: dict[str, Any], user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    with db() as conn:
        project, scenes = project_and_scenes(conn, project_id, user_id)
        if not scenes:
            raise HTTPException(400, "no scenes available, parse script first")
        if project["status"] == "generating":
            raise HTTPException(409, "project is already generating")
        try:
            config, warning = active_model_config(conn, user_id, "image", "镜头提示词生成"), ""
        except HTTPException as image_error:
            config = active_model_config(conn, user_id, "script", "镜头提示词生成回退")
            warning = "图片生成默认模型当前不可用，已回退到剧本/提示词默认模型。原始原因：" + str(image_error.detail)
        conn.execute("UPDATE projects SET status='generating', updated_at=? WHERE id=?", (now(), project_id))
    await broadcast(project_id, {"type": "PROJECT_UPDATE", "projectId": project_id, "data": {"status": "generating"}})
    asyncio.create_task(run_generation(project_id, [dict(scene) for scene in scenes], config, user_id))
    return {"projectId": project_id, "status": "generating", "model": str(payload.get("model") or config["model"]), "provider": config["provider"], "imageModel": config["model"], "warning": warning, "sceneCount": len(scenes)}


@router.post("/{project_id}/generate-video", status_code=202)
async def generate_video(project_id: str, payload: dict[str, Any], user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    with db() as conn:
        project, scenes = project_and_scenes(conn, project_id, user_id)
        if not scenes:
            raise HTTPException(400, "no scenes available, parse script first")
        if project["status"] == "video_generating":
            raise HTTPException(409, "project video is already generating")
        config = active_model_config(conn, user_id, "video", "视频生成")
        model = str(payload.get("model") or config["model"]).strip()
        conn.execute("UPDATE projects SET status='video_generating', video_status='generating', video_progress=0, updated_at=? WHERE id=?", (now(), project_id))
    await broadcast(project_id, {"type": "PROJECT_UPDATE", "projectId": project_id, "data": {"status": "video_generating", "videoStatus": "generating", "videoModel": model}})
    asyncio.create_task(run_video_generation(project_id, model))
    return {"projectId": project_id, "status": "video_generating", "model": model}


@router.delete("/{project_id}", status_code=204)
async def delete_project(project_id: str, user_id: int = Depends(current_user_id)) -> None:
    with db() as conn:
        project = row(conn, "SELECT * FROM projects WHERE id=? AND deleted_at IS NULL", (project_id,))
        if not project:
            return
        if project["user_id"] != user_id:
            raise HTTPException(403, "project does not belong to current user")
        conn.execute("UPDATE projects SET deleted_at=?, updated_at=? WHERE id=?", (now(), now(), project_id))
    await broadcast(project_id, {"type": "PROJECT_DELETED", "projectId": project_id})
