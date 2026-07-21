from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException

from app.core.database import row, rows
from app.utils.common import new_id, now


JOB_TYPES = {"storyboards", "audio", "videos", "preview", "export"}


def job_json(job: sqlite3.Row) -> dict[str, Any]:
    def load(value: str | None) -> Any:
        if not value:
            return None
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None

    return {
        "id": job["id"],
        "projectId": job["project_id"],
        "sceneId": job["scene_id"],
        "jobType": job["job_type"],
        "status": job["status"],
        "progress": job["progress"],
        "input": load(job["input_json"]) or {},
        "result": load(job["result_json"]),
        "attempt": job["attempt"],
        "maxAttempts": job["max_attempts"],
        "errorCode": job["error_code"],
        "errorMessage": job["error_message"],
        "createdAt": job["created_at"],
        "updatedAt": job["updated_at"],
        "startedAt": job["started_at"],
        "finishedAt": job["finished_at"],
    }


def _project(conn: sqlite3.Connection, project_id: str, user_id: int) -> sqlite3.Row:
    project = row(conn, "SELECT * FROM projects WHERE id=? AND deleted_at IS NULL", (project_id,))
    if not project:
        raise HTTPException(404, "project not found")
    if project["user_id"] != user_id:
        raise HTTPException(403, "project does not belong to current user")
    return project


def enqueue_job(
    conn: sqlite3.Connection,
    user_id: int,
    project_id: str,
    job_type: str,
    input_data: dict[str, Any] | None = None,
    *,
    scene_id: str | None = None,
    idempotency_key: str | None = None,
    max_attempts: int = 3,
) -> sqlite3.Row:
    _project(conn, project_id, user_id)
    normalized_type = job_type.strip().lower()
    if normalized_type not in JOB_TYPES:
        raise HTTPException(400, "invalid job type")
    if scene_id and not row(
        conn,
        "SELECT 1 FROM scenes WHERE id=? AND project_id=? AND deleted_at IS NULL",
        (scene_id, project_id),
    ):
        raise HTTPException(404, "scene not found")
    key = (idempotency_key or "").strip()[:160] or None
    if key:
        existing = row(
            conn,
            "SELECT * FROM generation_jobs WHERE user_id=? AND project_id=? AND idempotency_key=?",
            (user_id, project_id, key),
        )
        if existing:
            return existing
    attempts = max(1, min(int(max_attempts), 10))
    stamp = now()
    job_id = new_id("job")
    conn.execute(
        """INSERT INTO generation_jobs
        (id, created_at, updated_at, user_id, project_id, scene_id, job_type, status, progress,
         input_json, attempt, max_attempts, idempotency_key)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'queued', 0, ?, 0, ?, ?)""",
        (job_id, stamp, stamp, user_id, project_id, scene_id, normalized_type, json.dumps(input_data or {}, ensure_ascii=False), attempts, key),
    )
    return row(conn, "SELECT * FROM generation_jobs WHERE id=?", (job_id,))


def list_project_jobs(conn: sqlite3.Connection, user_id: int, project_id: str) -> list[dict[str, Any]]:
    _project(conn, project_id, user_id)
    return [
        job_json(item)
        for item in rows(conn, "SELECT * FROM generation_jobs WHERE project_id=? ORDER BY created_at DESC", (project_id,))
    ]


def job_for_user(conn: sqlite3.Connection, job_id: str, user_id: int) -> sqlite3.Row:
    job = row(conn, "SELECT * FROM generation_jobs WHERE id=?", (job_id,))
    if not job:
        raise HTTPException(404, "job not found")
    if job["user_id"] != user_id:
        raise HTTPException(403, "job does not belong to current user")
    return job


def cancel_job(conn: sqlite3.Connection, job_id: str, user_id: int) -> sqlite3.Row:
    job = job_for_user(conn, job_id, user_id)
    if job["status"] not in {"queued", "running"}:
        raise HTTPException(409, "only queued or running jobs can be canceled")
    stamp = now()
    conn.execute(
        """UPDATE generation_jobs SET status='canceled', updated_at=?, finished_at=?, lease_owner=NULL,
        lease_expires_at=NULL, heartbeat_at=NULL WHERE id=?""",
        (stamp, stamp, job_id),
    )
    return row(conn, "SELECT * FROM generation_jobs WHERE id=?", (job_id,))


def retry_job(conn: sqlite3.Connection, job_id: str, user_id: int) -> sqlite3.Row:
    job = job_for_user(conn, job_id, user_id)
    if job["status"] not in {"failed", "canceled"}:
        raise HTTPException(409, "only failed or canceled jobs can be retried")
    if job["attempt"] >= job["max_attempts"]:
        raise HTTPException(409, "job has reached its retry limit")
    conn.execute(
        """UPDATE generation_jobs SET status='queued', progress=0, updated_at=?, started_at=NULL,
        finished_at=NULL, lease_owner=NULL, lease_expires_at=NULL, heartbeat_at=NULL,
        error_code=NULL, error_message=NULL WHERE id=?""",
        (now(), job_id),
    )
    return row(conn, "SELECT * FROM generation_jobs WHERE id=?", (job_id,))


def claim_next_job(conn: sqlite3.Connection, worker_id: str, lease_seconds: int = 60) -> sqlite3.Row | None:
    stamp = now()
    candidate = row(
        conn,
        """SELECT * FROM generation_jobs
        WHERE attempt < max_attempts AND (
          status='queued' OR (status='running' AND lease_expires_at IS NOT NULL AND lease_expires_at < ?)
        ) ORDER BY created_at ASC LIMIT 1""",
        (stamp,),
    )
    if not candidate:
        return None
    lease_until = (datetime.now(timezone.utc) + timedelta(seconds=max(10, lease_seconds))).isoformat()
    started_at = candidate["started_at"] or stamp
    updated = conn.execute(
        """UPDATE generation_jobs SET status='running', progress=CASE WHEN status='queued' THEN 0 ELSE progress END,
        attempt=attempt+1, updated_at=?, started_at=?, finished_at=NULL, lease_owner=?, lease_expires_at=?, heartbeat_at=?
        WHERE id=? AND attempt=? AND status=?""",
        (stamp, started_at, worker_id[:120], lease_until, stamp, candidate["id"], candidate["attempt"], candidate["status"]),
    )
    if updated.rowcount != 1:
        return None
    return row(conn, "SELECT * FROM generation_jobs WHERE id=?", (candidate["id"],))


def finish_job(
    conn: sqlite3.Connection,
    job_id: str,
    worker_id: str,
    *,
    result: dict[str, Any] | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
) -> sqlite3.Row:
    job = row(conn, "SELECT * FROM generation_jobs WHERE id=?", (job_id,))
    if not job or job["status"] != "running" or job["lease_owner"] != worker_id[:120]:
        raise ValueError("job lease is not owned by this worker")
    stamp = now()
    succeeded = error_code is None
    conn.execute(
        """UPDATE generation_jobs SET status=?, progress=?, result_json=?, error_code=?, error_message=?,
        updated_at=?, finished_at=?, lease_owner=NULL, lease_expires_at=NULL, heartbeat_at=NULL WHERE id=?""",
        (
            "succeeded" if succeeded else "failed",
            100 if succeeded else job["progress"],
            json.dumps(result, ensure_ascii=False) if result is not None else None,
            error_code,
            (error_message or "")[:500] or None,
            stamp,
            stamp,
            job_id,
        ),
    )
    return row(conn, "SELECT * FROM generation_jobs WHERE id=?", (job_id,))
