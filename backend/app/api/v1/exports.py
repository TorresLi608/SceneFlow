"""Video export: pick rendered shots, merge them, download the result."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends

from app.api.deps import current_user_id
from app.core.database import db
from app.schemas.requests import CreateExportRequest
from app.services.export_service import (
    create_export,
    delete_export,
    export_job_json,
    exports_for,
    owned_export,
    resolve_clips,
    resolve_episode_videos,
    run_export,
)
from app.services.project_service import owned_project


router = APIRouter(prefix="/api/projects", tags=["exports"])


@router.get("/{project_id}/exports")
def list_exports(project_id: str, user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    with db() as session:
        owned_project(session, project_id, user_id)
        data = [export_job_json(job) for job in exports_for(session, project_id)]
    return {"exports": data}


@router.post("/{project_id}/exports", status_code=202)
async def add_export(
    project_id: str,
    body: CreateExportRequest,
    user_id: int = Depends(current_user_id),
) -> dict[str, Any]:
    """Queue composed episodes in selection order (legacy scene selections still accepted)."""
    with db() as session:
        owned_project(session, project_id, user_id)
        stored_paths = resolve_episode_videos(session, project_id, body.episode_ids) if body.episode_ids is not None else resolve_clips(session, project_id, body.scene_ids or [])
        job = create_export(session, user_id, project_id, body.scene_ids or [], body.range_label, episode_ids=body.episode_ids)
        data = export_job_json(job)

    # No project-level lock: merging reads finished artifacts and writes only its own row,
    # so it cannot collide with a render the way generation does.
    asyncio.create_task(run_export(data["id"], project_id, stored_paths))
    return {"export": data}


@router.get("/{project_id}/exports/{export_id}")
def get_export(project_id: str, export_id: str, user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    with db() as session:
        owned_project(session, project_id, user_id)
        data = export_job_json(owned_export(session, project_id, export_id))
    return {"export": data}


@router.delete("/{project_id}/exports/{export_id}")
def remove_export(project_id: str, export_id: str, user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    with db() as session:
        owned_project(session, project_id, user_id)
        delete_export(session, project_id, export_id)
    return {"success": True}
