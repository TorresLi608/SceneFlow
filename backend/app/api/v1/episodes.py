"""Episode CRUD. A series' content hangs off these rows, so this is where it is managed."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import current_user_id
from app.core.database import db
from app.core.realtime import broadcast
from app.schemas.requests import CreateEpisodeRequest, UpdateEpisodeRequest
from app.schemas.serializers import episode_json, episode_summary_json
from app.services.character_service import scene_cast
from app.services.episode_service import (
    create_episode,
    delete_episode,
    episode_scenes,
    episodes_for,
    resolve_episode,
    scene_counts,
    touch_episode,
)
from app.services.project_service import IDLE_STATUSES, owned_project


router = APIRouter(prefix="/api/projects", tags=["episodes"])


def _detail(session, episode) -> dict[str, Any]:
    """One episode with its ordered shots and the cast of each."""
    scenes = episode_scenes(session, episode.id)
    return episode_json(episode, scenes, scene_cast(session, [scene.id for scene in scenes]))


@router.get("/{project_id}/episodes")
def list_episodes(project_id: str, user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    with db() as session:
        owned_project(session, project_id, user_id)
        episodes = episodes_for(session, project_id)
        counts = scene_counts(session, [project_id])
        data = [episode_summary_json(episode, counts.get(episode.id, 0)) for episode in episodes]
    return {"episodes": data}


@router.post("/{project_id}/episodes", status_code=201)
async def add_episode(
    project_id: str,
    body: CreateEpisodeRequest,
    user_id: int = Depends(current_user_id),
) -> dict[str, Any]:
    with db() as session:
        owned_project(session, project_id, user_id)
        episode = create_episode(
            session,
            project_id,
            title=body.title,
            synopsis=body.synopsis,
            source_text=body.source_text,
        )
        data = episode_json(episode, [])
    await broadcast(project_id, {"type": "EPISODE_UPDATE", "projectId": project_id, "episodeId": data["id"], "data": data})
    return {"episode": data}


@router.get("/{project_id}/episodes/{episode_id}")
def get_episode(project_id: str, episode_id: str, user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    with db() as session:
        owned_project(session, project_id, user_id)
        episode = resolve_episode(session, project_id, episode_id)
        data = _detail(session, episode)
    return {"episode": data}


@router.patch("/{project_id}/episodes/{episode_id}")
async def update_episode(
    project_id: str,
    episode_id: str,
    body: UpdateEpisodeRequest,
    user_id: int = Depends(current_user_id),
) -> dict[str, Any]:
    updates = {
        column: value
        for column, value in (
            ("title", body.title),
            ("synopsis", body.synopsis),
            ("source_text", body.source_text),
            ("status", body.status),
        )
        if value is not None
    }
    if not updates:
        raise HTTPException(400, "no fields to update")

    with db() as session:
        owned_project(session, project_id, user_id)
        episode = resolve_episode(session, project_id, episode_id)
        touch_episode(session, episode, **updates)
        data = _detail(session, episode)
    await broadcast(project_id, {"type": "EPISODE_UPDATE", "projectId": project_id, "episodeId": episode_id, "data": data})
    return {"episode": data}


@router.delete("/{project_id}/episodes/{episode_id}", status_code=204)
async def remove_episode(project_id: str, episode_id: str, user_id: int = Depends(current_user_id)) -> None:
    with db() as session:
        project = owned_project(session, project_id, user_id)
        # A run holds the episode's scenes open, and generation writes back to rows it
        # already read. Deleting underneath it would strand that work.
        if (project.status or "idle") not in IDLE_STATUSES:
            raise HTTPException(409, "project is busy, cannot delete an episode right now")
        episode = resolve_episode(session, project_id, episode_id)
        delete_episode(session, episode)
    await broadcast(project_id, {"type": "EPISODE_DELETED", "projectId": project_id, "episodeId": episode_id})
