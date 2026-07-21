from __future__ import annotations

import sqlite3
from typing import Any

from fastapi import HTTPException

from app.core.database import row, rows
from app.services.config_service import active_model_config
from app.services.usage_service import require_model_balance
from app.utils.common import now


PROJECT_MODES = {"comic", "drama"}
ASPECT_RATIOS = {"9:16", "16:9", "1:1"}
PROJECT_STAGES = {"script", "bible", "storyboard", "audio", "timeline", "export"}


def production_settings(payload: dict[str, Any], *, defaults: bool = False) -> dict[str, Any]:
    values: dict[str, Any] = {}

    def take(key: str, default: Any) -> Any:
        return payload[key] if key in payload else default

    def integer(key: str, default: int) -> int:
        try:
            return int(take(key, default))
        except (TypeError, ValueError) as exc:
            raise HTTPException(400, f"{key} must be an integer") from exc

    if defaults or "mode" in payload:
        mode = str(take("mode", "comic")).strip().lower()
        if mode not in PROJECT_MODES:
            raise HTTPException(400, "mode must be comic or drama")
        values["mode"] = mode
    if defaults or "aspectRatio" in payload:
        aspect_ratio = str(take("aspectRatio", "9:16")).strip()
        if aspect_ratio not in ASPECT_RATIOS:
            raise HTTPException(400, "unsupported aspect ratio")
        values["aspect_ratio"] = aspect_ratio
    for request_key, column, default in (("width", "width", 1080), ("height", "height", 1920)):
        if defaults or request_key in payload:
            value = integer(request_key, default)
            if not 256 <= value <= 4096:
                raise HTTPException(400, f"{request_key} must be between 256 and 4096")
            values[column] = value
    if defaults or "fps" in payload:
        fps = integer("fps", 24)
        if fps not in {24, 30}:
            raise HTTPException(400, "fps must be 24 or 30")
        values["fps"] = fps
    if defaults or "targetDurationMs" in payload:
        duration = integer("targetDurationMs", 60000)
        if not 10000 <= duration <= 600000:
            raise HTTPException(400, "targetDurationMs must be between 10000 and 600000")
        values["target_duration_ms"] = duration
    if defaults or "language" in payload:
        language = str(take("language", "zh-CN")).strip()[:20]
        if not language:
            raise HTTPException(400, "language is required")
        values["language"] = language
    for request_key, column in (("stylePrompt", "style_prompt"), ("negativePrompt", "negative_prompt")):
        if defaults or request_key in payload:
            values[column] = str(take(request_key, ""))[:4000]
    if defaults or "currentStage" in payload:
        stage = str(take("currentStage", "script")).strip().lower()
        if stage not in PROJECT_STAGES:
            raise HTTPException(400, "invalid project stage")
        values["current_stage"] = stage
    return values


async def parse_project_model(conn: sqlite3.Connection, user_id: int, project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    script = str(payload.get("script", "")).strip()
    if not script:
        raise HTTPException(400, "script is required")
    existing = row(conn, "SELECT * FROM projects WHERE id=? AND deleted_at IS NULL", (project_id,))
    stamp = now()
    if existing and existing["user_id"] != user_id:
        raise HTTPException(403, "project does not belong to current user")
    config = active_model_config(conn, user_id, "script", "故事生成/分镜拆分")
    require_model_balance(conn, user_id, config)
    if existing:
        conn.execute("UPDATE projects SET original_script=?, status='parsing', updated_at=? WHERE id=?", (script, stamp, project_id))
    else:
        title = str(payload.get("title", "")).strip()[:80] or "新项目"
        conn.execute(
            "INSERT INTO projects (id, created_at, updated_at, user_id, title, original_script, status, video_status, video_progress) VALUES (?, ?, ?, ?, ?, ?, 'parsing', 'idle', 0)",
            (project_id, stamp, stamp, user_id, title, script),
        )
    return {"script": script, "config": config}


def project_and_scenes(conn: sqlite3.Connection, project_id: str, user_id: int) -> tuple[sqlite3.Row, list[sqlite3.Row]]:
    project = row(conn, "SELECT * FROM projects WHERE id=? AND deleted_at IS NULL", (project_id,))
    if not project:
        raise HTTPException(404, "project not found")
    if project["user_id"] != user_id:
        raise HTTPException(403, "project does not belong to current user")
    return project, rows(conn, "SELECT * FROM scenes WHERE project_id=? AND deleted_at IS NULL ORDER BY order_num ASC", (project_id,))
