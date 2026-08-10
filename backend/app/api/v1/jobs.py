from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.api.deps import current_user_id
from app.core.database import db
from app.core.realtime import broadcast
from app.services.job_service import cancel_job, job_json, retry_job


router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.post("/{job_id}/cancel")
async def cancel_generation_job(job_id: str, user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    with db() as session:
        job = cancel_job(session, job_id, user_id)
    data = job_json(job)
    await broadcast(job.project_id, {"type": "JOB_UPDATE", "projectId": job.project_id, "jobId": job_id, "data": data})
    return {"job": data}


@router.post("/{job_id}/retry")
async def retry_generation_job(job_id: str, user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    with db() as session:
        job = retry_job(session, job_id, user_id)
    data = job_json(job)
    await broadcast(job.project_id, {"type": "JOB_UPDATE", "projectId": job.project_id, "jobId": job_id, "data": data})
    return {"job": data}
