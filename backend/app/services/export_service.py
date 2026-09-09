"""Compose shots into an episode, then merge episode videos into delivery exports."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import HTTPException
from sqlmodel import Session, select
from sqlalchemy import update

from app.core.database import db
from app.models import ExportJob, Project, Scene
from app.models import Episode
from app.services.artifact_service import (
    artifact_absolute_path,
    remove_stored_artifacts,
    signed_url_for_stored,
    store_artifact,
)
from app.services.media_service import concat_videos
from app.utils.common import new_id, now


logger = logging.getLogger(__name__)


def recover_interrupted_exports() -> None:
    """Single-process startup: unfinished merges cannot resume after a restart."""
    with db() as session:
        session.execute(update(ExportJob).where(ExportJob.status.in_(["queued", "running"])).values(
            status="failed", progress=0, finished_at=now(), updated_at=now(), error_message="Export interrupted by server restart"
        ))


def _signed(stored: str | None, download_stem: str) -> str | None:
    """A fresh link, or None when the file is gone.

    Same shape as `serializers.scene_asset_url`; importing it here would make the service
    layer depend on the response layer.
    """
    if not stored:
        return None
    try:
        return signed_url_for_stored(stored, download_stem)
    except (ValueError, OSError):
        return None


def export_job_json(job: ExportJob) -> dict[str, Any]:
    try:
        scene_ids = json.loads(job.source_scene_ids or "[]")
    except json.JSONDecodeError:
        scene_ids = []
    return {
        "id": job.id,
        "projectId": job.project_id,
        "sceneIds": scene_ids if isinstance(scene_ids, list) else [],
        "episodeIds": json.loads(job.source_episode_ids or "[]"),
        "targetEpisodeId": job.target_episode_id,
        "rangeLabel": job.range_label or "",
        "status": job.status,
        "progress": job.progress or 0,
        # Minted per response like every other asset: the row keeps a path.
        "videoUrl": _signed(job.output_path, f"export-{job.id}"),
        "fileSize": job.file_size or 0,
        "errorMessage": job.error_message or "",
        "createdAt": job.created_at,
        "updatedAt": job.updated_at,
        "finishedAt": job.finished_at,
    }


def exports_for(session: Session, project_id: str) -> list[ExportJob]:
    return list(
        session.exec(
            select(ExportJob).where(ExportJob.project_id == project_id).order_by(ExportJob.created_at.desc())
        ).all()
    )


def owned_export(session: Session, project_id: str, job_id: str) -> ExportJob:
    job = session.exec(
        select(ExportJob).where(ExportJob.id == job_id, ExportJob.project_id == project_id)
    ).first()
    if not job:
        raise HTTPException(404, "export not found")
    return job


def delete_export(session: Session, project_id: str, job_id: str) -> None:
    job = owned_export(session, project_id, job_id)
    if job.status in {"queued", "running"}:
        raise HTTPException(409, "cannot delete a running export")
    if job.output_path:
        for episode in session.exec(select(Episode).where(Episode.project_id == project_id, Episode.video_path == job.output_path)).all():
            episode.video_path = None
            episode.updated_at = now()
            session.add(episode)
        remove_stored_artifacts([job.output_path])
    session.delete(job)
    session.flush()


def resolve_clips(session: Session, project_id: str, scene_ids: list[str]) -> list[str]:
    """The stored video paths for the chosen shots, in the order the user asked for.

    Ordered by the request rather than by `order_num`: the whole point of the video section
    is assembling a cut, which may not follow the storyboard.
    """
    rows = {
        scene.id: scene
        for scene in session.exec(
            select(Scene).where(
                Scene.id.in_(scene_ids), Scene.project_id == project_id, Scene.deleted_at.is_(None)
            )
        ).all()
    }
    missing = [scene_id for scene_id in scene_ids if scene_id not in rows]
    if missing:
        raise HTTPException(400, f"unknown shot for this project: {', '.join(missing)}")
    unrendered = [scene_id for scene_id in scene_ids if not rows[scene_id].video_path]
    if unrendered:
        raise HTTPException(400, f"these shots have no video yet: {', '.join(unrendered)}")
    return [rows[scene_id].video_path for scene_id in scene_ids]


def create_export(session: Session, user_id: int, project_id: str, scene_ids: list[str], range_label: str, *, episode_ids: list[str] | None = None, target_episode_id: str | None = None) -> ExportJob:
    stamp = now()
    job = ExportJob(
        id=new_id("export"),
        created_at=stamp,
        updated_at=stamp,
        user_id=user_id,
        project_id=project_id,
        source_scene_ids=json.dumps(scene_ids, ensure_ascii=False),
        source_episode_ids=json.dumps(episode_ids or []),
        target_episode_id=target_episode_id,
        range_label=range_label[:120],
        status="queued",
    )
    session.add(job)
    session.flush()
    return job


def _finish(job_id: str, **values: Any) -> None:
    with db() as session:
        job = session.get(ExportJob, job_id)
        if not job:
            return
        for key, value in values.items():
            setattr(job, key, value)
        job.updated_at = now()
        session.add(job)
        if values.get("status") == "succeeded" and job.target_episode_id:
            episode = session.get(Episode, job.target_episode_id)
            if episode and not episode.deleted_at and episode.project_id == job.project_id:
                episode.video_path = job.output_path
                episode.updated_at = now()
                session.add(episode)


async def run_export(job_id: str, project_id: str, stored_paths: list[str]) -> None:
    """Concatenate the chosen clips. Runs in the background; the client polls the job."""
    _finish(job_id, status="running", started_at=now(), progress=10)
    try:
        with db() as session:
            project = session.get(Project, project_id)
            if not project:
                raise ValueError("project not found")
            width, height, fps = project.width, project.height, project.fps
        clips = []
        for stored in stored_paths:
            # Unlike a reference sheet, a missing clip here means the export would silently
            # skip part of what the user selected, so it fails instead.
            clips.append(artifact_absolute_path(stored).read_bytes())
        _finish(job_id, progress=40)
        merged = await asyncio.to_thread(concat_videos, clips, width=width, height=height, fps=fps)
        output_path = store_artifact("exports", project_id, f"{job_id}.mp4", merged)
    except Exception as exc:
        detail = str(exc)[:220]
        logger.warning("export failed job=%s project=%s: %s", job_id, project_id, detail)
        _finish(job_id, status="failed", progress=0, finished_at=now(), error_message=detail)
        return

    _finish(
        job_id,
        status="succeeded",
        progress=100,
        finished_at=now(),
        output_path=output_path,
        file_size=len(merged),
        error_message=None,
    )


def resolve_episode_videos(session: Session, project_id: str, episode_ids: list[str]) -> list[str]:
    rows = {episode.id: episode for episode in session.exec(select(Episode).where(
        Episode.id.in_(episode_ids), Episode.project_id == project_id, Episode.deleted_at.is_(None)
    )).all()}
    if any(episode_id not in rows or not rows[episode_id].video_path for episode_id in episode_ids):
        raise HTTPException(400, "selected episodes must belong to this project and have a composed video")
    return [rows[episode_id].video_path for episode_id in episode_ids]
