from __future__ import annotations

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.models import Project, Scene, User
from app.services.job_service import cancel_job, claim_next_job, enqueue_job, finish_job, job_json, retry_job


def _session() -> Session:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    session = Session(engine, expire_on_commit=False)
    session.add(User(id=7, username="job-owner", password="x"))
    session.add(Project(id="project-1", user_id=7))
    session.add(Project(id="project-2", user_id=7))
    session.add(Scene(id="scene-1", project_id="project-1"))
    session.flush()
    return session


def test_job_lifecycle_and_idempotency() -> None:
    session = _session()
    first = enqueue_job(session, 7, "project-1", "storyboards", {"count": 2}, scene_id="scene-1", idempotency_key="same")
    duplicate = enqueue_job(session, 7, "project-1", "storyboards", {"count": 99}, idempotency_key="same")
    assert first.id == duplicate.id
    assert job_json(first)["input"] == {"count": 2}
    other_project = enqueue_job(session, 7, "project-2", "storyboards", idempotency_key="same")
    assert other_project.id != first.id

    claimed = claim_next_job(session, "worker-1")
    assert claimed is not None
    assert claimed.status == "running"
    assert claimed.attempt == 1

    failed = finish_job(session, claimed.id, "worker-1", error_code="PROVIDER_FAILED", error_message="temporary")
    assert failed.status == "failed"
    queued = retry_job(session, failed.id, 7)
    assert queued.status == "queued"
    canceled = cancel_job(session, queued.id, 7)
    assert canceled.status == "canceled"


if __name__ == "__main__":
    test_job_lifecycle_and_idempotency()
