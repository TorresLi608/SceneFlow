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
    """Queue a merge of the chosen shots, in the order they were given."""
    with db() as session:
        owned_project(session, project_id, user_id)
        stored_paths = resolve_clips(session, project_id, body.scene_ids)
        job = create_export(session, user_id, project_id, body.scene_ids, body.range_label)
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
