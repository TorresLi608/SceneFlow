from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, update
from sqlmodel import Session, select

from app.core.database import db
from app.models import Episode, Project, Scene
from app.services.config_service import active_model_config
from app.services.usage_service import require_model_balance
from app.utils.common import now


logger = logging.getLogger(__name__)

PROJECT_MODES = {"comic", "drama"}
ASPECT_RATIOS = {"9:16", "16:9", "1:1"}
PROJECT_STAGES = {"script", "bible", "storyboard", "audio", "timeline", "export"}
# States a project can be pulled out of to start new work; anything else means a run owns it.
IDLE_STATUSES = {"idle", "done", "partial", "failed"}


def production_settings(payload: dict[str, Any], *, defaults: bool = False) -> dict[str, Any]:
    values: dict[str, Any] = {}

    def take(key: str, default: Any) -> Any:
        return payload[key] if key in payload else default

    def integer(key: str, default: int) -> int:
        try:
            return int(take(key, default))
        except (TypeError, ValueError) as exc:
            raise HTTPException(400, f"{key} must be an integer") from exc

    if defaults or "mode" in payload:
        mode = str(take("mode", "comic")).strip().lower()
        if mode not in PROJECT_MODES:
            raise HTTPException(400, "mode must be comic or drama")
        values["mode"] = mode
    if defaults or "aspectRatio" in payload:
        aspect_ratio = str(take("aspectRatio", "9:16")).strip()
        if aspect_ratio not in ASPECT_RATIOS:
            raise HTTPException(400, "unsupported aspect ratio")
        values["aspect_ratio"] = aspect_ratio
    default_size = {"9:16": (1080, 1920), "16:9": (1920, 1080), "1:1": (1080, 1080)}.get(
        values.get("aspect_ratio", "9:16"),
        (1080, 1920),
    )
    for request_key, column, default in (("width", "width", default_size[0]), ("height", "height", default_size[1])):
        if defaults or request_key in payload:
            value = integer(request_key, default)
            if not 256 <= value <= 4096:
                raise HTTPException(400, f"{request_key} must be between 256 and 4096")
            values[column] = value
    if defaults or "fps" in payload:
        fps = integer("fps", 24)
        if fps not in {24, 30}:
            raise HTTPException(400, "fps must be 24 or 30")
        values["fps"] = fps
    if defaults or "targetDurationMs" in payload:
        duration = integer("targetDurationMs", 60000)
        if not 10000 <= duration <= 600000:
            raise HTTPException(400, "targetDurationMs must be between 10000 and 600000")
        values["target_duration_ms"] = duration
    if defaults or "language" in payload:
        language = str(take("language", "zh-CN")).strip()[:20]
        if not language:
            raise HTTPException(400, "language is required")
        values["language"] = language
    for request_key, column in (("stylePrompt", "style_prompt"), ("negativePrompt", "negative_prompt")):
        if defaults or request_key in payload:
            values[column] = str(take(request_key, ""))[:4000]
    if defaults or "currentStage" in payload:
        stage = str(take("currentStage", "script")).strip().lower()
        if stage not in PROJECT_STAGES:
            raise HTTPException(400, "invalid project stage")
        values["current_stage"] = stage
    if defaults:
        ratios = {"9:16": 9 / 16, "16:9": 16 / 9, "1:1": 1.0}
        if abs(values["width"] / values["height"] - ratios[values["aspect_ratio"]]) > 0.03:
            raise HTTPException(400, "width and height do not match aspectRatio")
    return values


def selected_scenes(
    scenes: list[Scene],
    scene_ids: list[str] | None,
    *,
    status_column: str,
    pending_only: bool = False,
) -> list[Scene]:
    """The shots a render targets, or a 400 saying why there are none.

    An approved (locked) shot is left alone by a batch rerun. `pending_only` narrows that
    further to shots that are not already rendered: a plain rerun re-renders — and re-pays
    for — every unlocked shot, which is the wrong thing when the user is retrying the two
    that failed out of twenty.

    One implementation for both media on purpose. The image and video paths each carried
    their own copy of this, and a cost rule that only half the app enforces is the rule that
    bills twice.
    """
    if scene_ids is None:
        selected = [scene for scene in scenes if not scene.is_locked]
    else:
        requested = {scene_id.strip() for scene_id in scene_ids if scene_id.strip()}
        selected = [scene for scene in scenes if scene.id in requested]
        if len(selected) != len(requested):
            raise HTTPException(400, "sceneIds must belong to the selected episode")
        if any(scene.is_locked for scene in selected):
            raise HTTPException(400, "unlock selected shots before generating them")
    if pending_only:
        selected = [scene for scene in selected if getattr(scene, status_column) != "success"]
    if not selected:
        raise HTTPException(
            400,
            "every selected shot is already rendered, nothing to retry"
            if pending_only
            else "every shot in this episode is locked, unlock one to regenerate",
        )
    return selected


def release_orphaned_runs() -> int:
    """Clear busy markers left by runs that died with the process, at startup.

    A render lives in an `asyncio.create_task` inside this process (see
    `docs/architecture/boundaries.md`), so a restart — a crash, a deploy, `--reload` picking
    up an edit — kills it with no chance to unwind. What it leaves behind is
    `projects.status = 'generating'`, which is not in `IDLE_STATUSES`, and `/cancel`
    deliberately refuses to clear it because doing so mid-run would let a second render
    write the same rows. The project is then permanently unrenderable: every start 409s and
    the editor polls a status that will never change.

    Startup is the one moment where "nothing is running" is known rather than guessed, so
    this is the only safe place to break that lock. `failed` rather than `idle` because the
    run genuinely did not finish, and it is in `IDLE_STATUSES` so work can start again.

    Single-process only, like the cancel registry it complements: a second worker booting
    while the first is mid-render would clear a lock that is legitimately held.
    """
    stamp = now()
    with db() as session:
        stale = session.execute(
            update(Project)
            .where(func.coalesce(Project.status, "idle").notin_(sorted(IDLE_STATUSES)))
            .values(status="failed", video_status="idle", video_progress=0, updated_at=stamp),
            execution_options={"synchronize_session": False},
        )
        session.execute(
            update(Episode)
            .where(Episode.status == "generating")
            .values(status="failed", error_message="服务重启，本次生成未完成", updated_at=stamp),
            execution_options={"synchronize_session": False},
        )
        # Each media column separately: a shot whose image landed before the restart keeps it.
        for model, column in (
            (Episode, "tone_image_status"),
            (Episode, "video_status"),
            (Scene, "image_status"),
            (Scene, "audio_status"),
            (Scene, "video_status"),
        ):
            session.execute(
                update(model)
                .where(getattr(model, column) == "generating")
                .values(updated_at=stamp, **{column: "idle"}),
                execution_options={"synchronize_session": False},
            )
    if stale.rowcount:
        logger.warning("released %d project run lock(s) left behind by a previous process", stale.rowcount)
    return stale.rowcount or 0


def claim_project_status(session: Session, project_id: str, *, allowed_from: set[str], to: str, **values: Any) -> None:
    """Move a project into a busy state, or refuse if something else already owns it.

    A conditional UPDATE rather than read-then-write: a double-clicked button used to start
    two identical runs that fought over the same rows. Extra columns ride along in the same
    statement so the claim and the fields it guards can never disagree.
    """
    claimed = session.execute(
        update(Project)
        .where(
            Project.id == project_id,
            Project.deleted_at.is_(None),
            func.coalesce(Project.status, "idle").in_(sorted(allowed_from)),
        )
        .values(status=to, updated_at=now(), **values),
        execution_options={"synchronize_session": False},
    )
    if claimed.rowcount != 1:
        raise HTTPException(409, f"project is busy and cannot start {to} right now")


def release_project_status(project_id: str, status: str = "idle") -> None:
    with db() as session:
        session.execute(
            update(Project).where(Project.id == project_id).values(status=status, updated_at=now()),
            execution_options={"synchronize_session": False},
        )


def prepare_parse(session: Session, user_id: int, project_id: str, script: str, title: str = "") -> dict[str, Any]:
    """Resolve the script model and take the parse lock, creating the project on first use."""
    existing = session.exec(select(Project).where(Project.id == project_id, Project.deleted_at.is_(None))).first()
    if existing and existing.user_id != user_id:
        raise HTTPException(403, "project does not belong to current user")
    config = active_model_config(session, user_id, "script", "故事生成/分镜拆分")
    require_model_balance(session, user_id, config)
    if existing:
        claim_project_status(session, project_id, allowed_from=IDLE_STATUSES, to="parsing", original_script=script)
    else:
        stamp = now()
        session.add(
            Project(
                id=project_id,
                created_at=stamp,
                updated_at=stamp,
                user_id=user_id,
                title=title.strip()[:80] or "新项目",
                original_script=script,
                status="parsing",
                video_status="idle",
                video_progress=0,
            )
        )
    return config


def scenes_with_assets(scenes: list[Scene]) -> list[Scene]:
    """Scenes that cost money or manual effort, and so must not be discarded silently."""
    return [scene for scene in scenes if scene.image_path or scene.audio_path or scene.video_path]


def owned_project(session: Session, project_id: str, user_id: int) -> Project:
    project = session.exec(select(Project).where(Project.id == project_id, Project.deleted_at.is_(None))).first()
    if not project:
        raise HTTPException(404, "project not found")
    if project.user_id != user_id:
        raise HTTPException(403, "project does not belong to current user")
    return project


def project_and_scenes(session: Session, project_id: str, user_id: int) -> tuple[Project, list[Scene]]:
    """The project and every shot in it, across all episodes.

    Only for whole-series work. Anything that renders or reorders wants one episode's
    shots, since order numbers restart each episode; use `episode_service.episode_scenes`.
    """
    project = owned_project(session, project_id, user_id)
    scenes = session.exec(
        select(Scene).where(Scene.project_id == project_id, Scene.deleted_at.is_(None)).order_by(Scene.order_num.asc())
    ).all()
    return project, list(scenes)
