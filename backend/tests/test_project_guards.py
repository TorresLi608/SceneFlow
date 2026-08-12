from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.models import Project, Scene
from app.services.generation_service import terminal_status
from app.services.project_service import IDLE_STATUSES, claim_project_status, scenes_with_assets


def _session() -> Session:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    return Session(engine, expire_on_commit=False)


def _project(session: Session, status: str = "idle") -> Project:
    project = Project(id="proj_1", created_at="t0", updated_at="t0", user_id=1, title="剧集", status=status)
    session.add(project)
    session.flush()
    return project


def test_scenes_with_assets_flags_only_paid_work() -> None:
    blank = Scene(id="s1", project_id="proj_1", order_num=1, narration="a")
    edited_only = Scene(id="s2", project_id="proj_1", order_num=2, narration="b", visual_prompt="prompt")
    rendered = Scene(id="s3", project_id="proj_1", order_num=3, narration="c", image_path="projects/p/1.png")
    voiced = Scene(id="s4", project_id="proj_1", order_num=4, narration="d", audio_path="projects/p/1.mp3")

    at_risk = scenes_with_assets([blank, edited_only, rendered, voiced])

    assert [scene.id for scene in at_risk] == ["s3", "s4"]


def test_claim_project_status_rejects_a_second_start() -> None:
    session = _session()
    _project(session)

    claim_project_status(session, "proj_1", allowed_from=IDLE_STATUSES, to="generating")
    assert session.exec(select(Project.status).where(Project.id == "proj_1")).first() == "generating"

    try:
        claim_project_status(session, "proj_1", allowed_from=IDLE_STATUSES, to="generating")
    except HTTPException as exc:
        assert exc.status_code == 409
    else:
        raise AssertionError("expected the second claim on a busy project to be refused")


def test_claim_project_status_reclaims_after_a_finished_run() -> None:
    session = _session()
    _project(session, status="failed")

    claim_project_status(session, "proj_1", allowed_from=IDLE_STATUSES, to="generating")

    assert session.exec(select(Project.status).where(Project.id == "proj_1")).first() == "generating"


def test_terminal_status_reports_what_actually_landed() -> None:
    assert terminal_status([True, True]) == "done"
    assert terminal_status([True, False]) == "partial"
    assert terminal_status([False, False]) == "failed"
    assert terminal_status([]) == "done"


if __name__ == "__main__":
    test_scenes_with_assets_flags_only_paid_work()
    test_claim_project_status_rejects_a_second_start()
    test_claim_project_status_reclaims_after_a_finished_run()
    test_terminal_status_reports_what_actually_landed()
