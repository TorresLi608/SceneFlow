from __future__ import annotations

import sqlite3
from typing import Any

from fastapi import HTTPException

from config_service import active_model_config
from database import row, rows
from utils import now


async def parse_project_model(conn: sqlite3.Connection, user_id: int, project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    script = str(payload.get("script", "")).strip()
    if not script:
        raise HTTPException(400, "script is required")
    existing = row(conn, "SELECT * FROM projects WHERE id=? AND deleted_at IS NULL", (project_id,))
    stamp = now()
    if existing and existing["user_id"] != user_id:
        raise HTTPException(403, "project does not belong to current user")
    if existing:
        conn.execute("UPDATE projects SET original_script=?, status='parsing', updated_at=? WHERE id=?", (script, stamp, project_id))
    else:
        conn.execute(
            "INSERT INTO projects (id, created_at, updated_at, user_id, original_script, status, video_status) VALUES (?, ?, ?, ?, ?, 'parsing', 'idle')",
            (project_id, stamp, stamp, user_id, script),
        )
    config = active_model_config(conn, user_id, "script", "故事生成/分镜拆分")
    return {"script": script, "config": config}


def project_and_scenes(conn: sqlite3.Connection, project_id: str, user_id: int) -> tuple[sqlite3.Row, list[sqlite3.Row]]:
    project = row(conn, "SELECT * FROM projects WHERE id=? AND deleted_at IS NULL", (project_id,))
    if not project:
        raise HTTPException(404, "project not found")
    if project["user_id"] != user_id:
        raise HTTPException(403, "project does not belong to current user")
    return project, rows(conn, "SELECT * FROM scenes WHERE project_id=? AND deleted_at IS NULL ORDER BY order_num ASC", (project_id,))
