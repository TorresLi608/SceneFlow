from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import and_, case, or_, update
from sqlmodel import Session, select

from app.models import GenerationJob, Project, Scene
from app.utils.common import new_id, now


JOB_TYPES = {"storyboards", "audio", "videos", "preview", "export"}


def job_json(job: GenerationJob) -> dict[str, Any]:
    def load(value: str | None) -> Any:
        if not value:
            return None
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None

    return {
        "id": job.id,
        "projectId": job.project_id,
        "sceneId": job.scene_id,
        "jobType": job.job_type,
        "status": job.status,
        "progress": job.progress,
        "input": load(job.input_json) or {},
        "result": load(job.result_json),
        "attempt": job.attempt,
        "maxAttempts": job.max_attempts,
        "errorCode": job.error_code,
        "errorMessage": job.error_message,
        "createdAt": job.created_at,
        "updatedAt": job.updated_at,
        "startedAt": job.started_at,
        "finishedAt": job.finished_at,
    }


def _project(session: Session, project_id: str, user_id: int) -> Project:
    project = session.exec(select(Project).where(Project.id == project_id, Project.deleted_at.is_(None))).first()
    if not project:
        raise HTTPException(404, "project not found")
    if project.user_id != user_id:
        raise HTTPException(403, "project does not belong to current user")
    return project


def enqueue_job(
    session: Session,
    user_id: int,
    project_id: str,
    job_type: str,
    input_data: dict[str, Any] | None = None,
    *,
    scene_id: str | None = None,
    idempotency_key: str | None = None,
    max_attempts: int = 3,
) -> GenerationJob:
    _project(session, project_id, user_id)
    normalized_type = job_type.strip().lower()
    if normalized_type not in JOB_TYPES:
        raise HTTPException(400, "invalid job type")
    if scene_id and not session.exec(
        select(Scene.id).where(Scene.id == scene_id, Scene.project_id == project_id, Scene.deleted_at.is_(None))
    ).first():
        raise HTTPException(404, "scene not found")
    key = (idempotency_key or "").strip()[:160] or None
    if key:
        existing = session.exec(
            select(GenerationJob).where(
                GenerationJob.user_id == user_id,
                GenerationJob.project_id == project_id,
                GenerationJob.idempotency_key == key,
            )
        ).first()
        if existing:
            return existing
    stamp = now()
    job = GenerationJob(
        id=new_id("job"),
        created_at=stamp,
        updated_at=stamp,
        user_id=user_id,
        project_id=project_id,
        scene_id=scene_id,
        job_type=normalized_type,
        status="queued",
        progress=0,
        input_json=json.dumps(input_data or {}, ensure_ascii=False),
        attempt=0,
        max_attempts=max(1, min(int(max_attempts), 10)),
        idempotency_key=key,
    )
    session.add(job)
    session.flush()
    return job


def list_project_jobs(session: Session, user_id: int, project_id: str) -> list[dict[str, Any]]:
    _project(session, project_id, user_id)
    jobs = session.exec(
        select(GenerationJob).where(GenerationJob.project_id == project_id).order_by(GenerationJob.created_at.desc())
    ).all()
    return [job_json(job) for job in jobs]


def job_for_user(session: Session, job_id: str, user_id: int) -> GenerationJob:
    job = session.exec(select(GenerationJob).where(GenerationJob.id == job_id)).first()
    if not job:
        raise HTTPException(404, "job not found")
    if job.user_id != user_id:
        raise HTTPException(403, "job does not belong to current user")
    return job


def cancel_job(session: Session, job_id: str, user_id: int) -> GenerationJob:
    job = job_for_user(session, job_id, user_id)
    if job.status not in {"queued", "running"}:
        raise HTTPException(409, "only queued or running jobs can be canceled")
    stamp = now()
    job.status = "canceled"
    job.updated_at = stamp
    job.finished_at = stamp
    job.lease_owner = None
    job.lease_expires_at = None
    job.heartbeat_at = None
    session.add(job)
    session.flush()
    return job


def retry_job(session: Session, job_id: str, user_id: int) -> GenerationJob:
    job = job_for_user(session, job_id, user_id)
    if job.status not in {"failed", "canceled"}:
        raise HTTPException(409, "only failed or canceled jobs can be retried")
    if job.attempt >= job.max_attempts:
        raise HTTPException(409, "job has reached its retry limit")
    job.status = "queued"
    job.progress = 0
    job.updated_at = now()
    job.started_at = None
    job.finished_at = None
    job.lease_owner = None
    job.lease_expires_at = None
    job.heartbeat_at = None
    job.error_code = None
    job.error_message = None
    session.add(job)
    session.flush()
    return job


def claim_next_job(session: Session, worker_id: str, lease_seconds: int = 60) -> GenerationJob | None:
    stamp = now()
    candidate = session.exec(
        select(GenerationJob)
        .where(
            GenerationJob.attempt < GenerationJob.max_attempts,
            or_(
                GenerationJob.status == "queued",
                and_(
                    GenerationJob.status == "running",
                    GenerationJob.lease_expires_at.is_not(None),
                    GenerationJob.lease_expires_at < stamp,
                ),
            ),
        )
        .order_by(GenerationJob.created_at.asc())
        .limit(1)
    ).first()
    if not candidate:
        return None
    lease_until = (datetime.now(timezone.utc) + timedelta(seconds=max(10, lease_seconds))).isoformat()
    started_at = candidate.started_at or stamp
    # Optimistic claim: another worker that grabbed this job first moves attempt/status and loses us the row.
    claimed = session.execute(
        update(GenerationJob)
        .where(
            GenerationJob.id == candidate.id,
            GenerationJob.attempt == candidate.attempt,
            GenerationJob.status == candidate.status,
        )
        .values(
            status="running",
            progress=case((GenerationJob.status == "queued", 0), else_=GenerationJob.progress),
            attempt=GenerationJob.attempt + 1,
            updated_at=stamp,
            started_at=started_at,
            finished_at=None,
            lease_owner=worker_id[:120],
            lease_expires_at=lease_until,
            heartbeat_at=stamp,
        ),
        execution_options={"synchronize_session": False},
    )
    if claimed.rowcount != 1:
        return None
    session.refresh(candidate)
    return candidate


def finish_job(
    session: Session,
    job_id: str,
    worker_id: str,
    *,
    result: dict[str, Any] | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
) -> GenerationJob:
    job = session.exec(select(GenerationJob).where(GenerationJob.id == job_id)).first()
    if not job or job.status != "running" or job.lease_owner != worker_id[:120]:
        raise ValueError("job lease is not owned by this worker")
    stamp = now()
    succeeded = error_code is None
    job.status = "succeeded" if succeeded else "failed"
    job.progress = 100 if succeeded else job.progress
    job.result_json = json.dumps(result, ensure_ascii=False) if result is not None else None
    job.error_code = error_code
    job.error_message = (error_message or "")[:500] or None
    job.updated_at = stamp
    job.finished_at = stamp
    job.lease_owner = None
    job.lease_expires_at = None
    job.heartbeat_at = None
    session.add(job)
    session.flush()
    return job
