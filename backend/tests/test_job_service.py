from __future__ import annotations

import sqlite3

from app.services.job_service import cancel_job, claim_next_job, enqueue_job, finish_job, job_json, retry_job


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE projects (id text PRIMARY KEY, user_id integer NOT NULL, deleted_at datetime);
        CREATE TABLE scenes (id text PRIMARY KEY, project_id text NOT NULL, deleted_at datetime);
        CREATE TABLE generation_jobs (
            id text PRIMARY KEY, created_at datetime NOT NULL, updated_at datetime NOT NULL,
            started_at datetime, finished_at datetime, user_id integer NOT NULL, project_id text NOT NULL,
            scene_id text, job_type text NOT NULL, status text NOT NULL DEFAULT 'queued', progress integer NOT NULL DEFAULT 0,
            input_json text NOT NULL DEFAULT '{}', result_json text, attempt integer NOT NULL DEFAULT 0,
            max_attempts integer NOT NULL DEFAULT 3, idempotency_key text, lease_owner text,
            lease_expires_at datetime, heartbeat_at datetime, error_code text, error_message text
        );
        CREATE UNIQUE INDEX jobs_key ON generation_jobs(user_id, project_id, idempotency_key) WHERE idempotency_key IS NOT NULL;
        INSERT INTO projects VALUES ('project-1', 7, NULL);
        INSERT INTO projects VALUES ('project-2', 7, NULL);
        INSERT INTO scenes VALUES ('scene-1', 'project-1', NULL);
        """
    )
    return conn


def test_job_lifecycle_and_idempotency() -> None:
    conn = _conn()
    first = enqueue_job(conn, 7, "project-1", "storyboards", {"count": 2}, scene_id="scene-1", idempotency_key="same")
    duplicate = enqueue_job(conn, 7, "project-1", "storyboards", {"count": 99}, idempotency_key="same")
    assert first["id"] == duplicate["id"]
    assert job_json(first)["input"] == {"count": 2}
    other_project = enqueue_job(conn, 7, "project-2", "storyboards", idempotency_key="same")
    assert other_project["id"] != first["id"]

    claimed = claim_next_job(conn, "worker-1")
    assert claimed is not None
    assert claimed["status"] == "running"
    assert claimed["attempt"] == 1

    failed = finish_job(conn, claimed["id"], "worker-1", error_code="PROVIDER_FAILED", error_message="temporary")
    assert failed["status"] == "failed"
    queued = retry_job(conn, failed["id"], 7)
    assert queued["status"] == "queued"
    canceled = cancel_job(conn, queued["id"], 7)
    assert canceled["status"] == "canceled"


if __name__ == "__main__":
    test_job_lifecycle_and_idempotency()
