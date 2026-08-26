from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.core.database import db, init_db
from app.models import Episode, Project, Scene
from app.services.generation_service import clear_generating_scenes, terminal_status
from app.services.project_service import (
    IDLE_STATUSES,
    claim_project_status,
    release_orphaned_runs,
    scenes_with_assets,
    selected_scenes,
)


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


def _shot(
    scene_id: str,
    order: int,
    *,
    image: str = "idle",
    video: str = "idle",
    locked: bool = False,
    project_id: str = "proj_1",
    episode_id: str = "ep_1",
) -> Scene:
    return Scene(
        id=scene_id,
        project_id=project_id,
        episode_id=episode_id,
        order_num=order,
        narration="n",
        image_status=image,
        video_status=video,
        is_locked=locked,
    )


def test_selected_scenes_pending_only_skips_what_is_already_rendered() -> None:
    """The whole point: retrying a partly failed batch must not re-pay for the frames that landed."""
    scenes = [
        _shot("s1", 1, image="success"),
        _shot("s2", 2, image="error"),
        _shot("s3", 3, image="idle"),
        _shot("s4", 4, image="success", locked=True),
    ]

    assert [scene.id for scene in selected_scenes(scenes, None, status_column="image_status")] == ["s1", "s2", "s3"]
    retried = selected_scenes(scenes, None, status_column="image_status", pending_only=True)
    assert [scene.id for scene in retried] == ["s2", "s3"]


def test_selected_scenes_pending_only_reads_the_media_it_was_asked_about() -> None:
    """A shot with a frame but no clip is pending for video and finished for images."""
    scenes = [_shot("s1", 1, image="success", video="error")]

    assert selected_scenes(scenes, None, status_column="video_status", pending_only=True)[0].id == "s1"
    try:
        selected_scenes(scenes, None, status_column="image_status", pending_only=True)
    except HTTPException as exc:
        assert exc.status_code == 400
    else:
        raise AssertionError("expected a fully rendered shot to leave nothing to retry")


def test_selected_scenes_refuses_an_empty_batch_with_the_reason() -> None:
    locked = [_shot("s1", 1, locked=True)]
    rendered = [_shot("s2", 1, image="success")]

    for scenes, pending_only, expected in ((locked, False, "locked"), (rendered, True, "already rendered")):
        try:
            selected_scenes(scenes, None, status_column="image_status", pending_only=pending_only)
        except HTTPException as exc:
            assert exc.status_code == 400
            assert expected in exc.detail
        else:
            raise AssertionError(f"expected a 400 mentioning {expected!r}")


def _seed_episode(
    session: Session,
    *,
    project_id: str,
    episode_id: str,
    project_status: str = "idle",
    **episode: Any,
) -> None:
    """Parents for the shots below. `PRAGMA foreign_keys = ON`, so they cannot be skipped.

    Flushed one at a time: these tables carry `foreign_key` columns but no ORM relationship,
    so SQLAlchemy has no dependency graph to order the inserts by. Each test seeds its own
    ids — the whole file shares one database.
    """
    session.add(
        Project(id=project_id, created_at="t0", updated_at="t0", user_id=1, title="剧集", status=project_status)
    )
    session.flush()
    session.add(
        Episode(id=episode_id, created_at="t0", updated_at="t0", project_id=project_id, episode_number=1, **episode)
    )
    session.flush()


def test_clear_generating_scenes_keeps_work_the_provider_was_already_paid_for() -> None:
    """A stopped run resets only what never finished; a blind reset billed the user twice."""
    init_db()
    ids = {"project_id": "proj_clear", "episode_id": "ep_clear"}
    with db() as session:
        _seed_episode(session, **ids)
        session.add(_shot("done", 1, image="success", video="success", **ids))
        session.add(_shot("mid_flight", 2, image="generating", video="generating", **ids))

    clear_generating_scenes(["done", "mid_flight"], "image_status")

    with db() as session:
        rows = {
            scene.id: (scene.image_status, scene.video_status)
            for scene in session.exec(select(Scene).where(Scene.episode_id == "ep_clear")).all()
        }
    # The finished shot keeps its frame; only what never landed goes back to idle. And the
    # other column is untouched: stopping an image run says nothing about the clips.
    assert rows == {"done": ("success", "success"), "mid_flight": ("idle", "generating")}


def test_release_orphaned_runs_breaks_a_lock_no_live_run_holds() -> None:
    """A render dies with its process holding `status='generating'`, and /cancel will not clear it."""
    init_db()
    ids = {"project_id": "proj_dead", "episode_id": "ep_dead"}
    with db() as session:
        _seed_episode(session, **ids, project_status="generating", status="generating", tone_image_status="success")
        session.add(Project(id="proj_live", created_at="t0", updated_at="t0", user_id=1, title="b", status="done"))
        session.flush()
        session.add(_shot("landed", 1, image="success", **ids))
        session.add(_shot("stuck", 2, image="generating", **ids))

    assert release_orphaned_runs() >= 1

    with db() as session:
        dead = session.get(Project, "proj_dead")
        live = session.get(Project, "proj_live")
        episode = session.get(Episode, "ep_dead")
        shots = {
            scene.id: scene.image_status
            for scene in session.exec(select(Scene).where(Scene.episode_id == "ep_dead")).all()
        }
    # `failed` is in IDLE_STATUSES, so the project can be rendered again.
    assert dead.status == "failed"
    assert live.status == "done"
    assert episode.status == "failed"
    # The anchor survived the restart and must not be resampled.
    assert episode.tone_image_status == "success"
    assert shots == {"landed": "success", "stuck": "idle"}


if __name__ == "__main__":
    test_scenes_with_assets_flags_only_paid_work()
    test_claim_project_status_rejects_a_second_start()
    test_claim_project_status_reclaims_after_a_finished_run()
    test_terminal_status_reports_what_actually_landed()
    test_selected_scenes_pending_only_skips_what_is_already_rendered()
    test_selected_scenes_pending_only_reads_the_media_it_was_asked_about()
    test_selected_scenes_refuses_an_empty_batch_with_the_reason()
    test_clear_generating_scenes_keeps_work_the_provider_was_already_paid_for()
    test_release_orphaned_runs_breaks_a_lock_no_live_run_holds()
