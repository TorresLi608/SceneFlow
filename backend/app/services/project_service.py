from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, update
from sqlmodel import Session, select

from app.core.database import db
from app.models import Project, Scene
from app.services.config_service import active_model_config
from app.services.usage_service import require_model_balance
from app.utils.common import now


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
