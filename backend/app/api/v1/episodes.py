"""Episode CRUD and storyboard rendering. A series' content hangs off these rows."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import current_user_id
from app.core.database import db
from app.core.realtime import broadcast
from app.models import Episode, Scene
from app.schemas.requests import CreateEpisodeRequest, GenerateStoryboardRequest, UpdateEpisodeRequest
from app.schemas.serializers import episode_json, episode_summary_json
from app.services.character_service import scene_cast
from app.services.config_service import active_model_config
from app.services.episode_service import (
    create_episode,
    delete_episode,
    episode_scenes,
    episodes_for,
    resolve_episode,
    scene_counts,
    touch_episode,
)
from app.services.project_service import IDLE_STATUSES, claim_project_status, owned_project
from app.services.storyboard_service import StoryboardPlan, run_storyboard
from app.services.usage_service import require_model_balance


router = APIRouter(prefix="/api/projects", tags=["episodes"])


def _selected_scenes(scenes: list[Scene], scene_ids: list[str] | None) -> list[Scene]:
    """The shots a render targets. An approved (locked) shot is left alone by a batch rerun."""
    if scene_ids is None:
        return [scene for scene in scenes if not scene.is_locked]
    requested = {scene_id.strip() for scene_id in scene_ids if scene_id.strip()}
    selected = [scene for scene in scenes if scene.id in requested]
    if len(selected) != len(requested):
        raise HTTPException(400, "sceneIds must belong to the selected episode")
    if any(scene.is_locked for scene in selected):
        raise HTTPException(400, "unlock selected shots before rendering them")
    return selected


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


def _reference_sources(session, project, previous: Episode | None) -> list[tuple[str, str]]:
    """The context images a render carries, in the order they matter.

    Only sheets, never the individual portraits: providers cap reference counts, and the
    tone sheet and the previous shot each need a slot of their own.
    """
    sources = [
        (project.character_sheet_path, "角色"),
        (project.prop_sheet_path, "道具"),
    ]
    if previous is not None:
        # The previous episode's anchor, so a series does not restyle itself between episodes.
        sources.append((previous.tone_image_path, f"上一集 · {previous.title}"))
    return [(stored, label) for stored, label in sources if stored]


@router.post("/{project_id}/episodes/{episode_id}/storyboard", status_code=202)
async def generate_storyboard(
    project_id: str,
    episode_id: str,
    body: GenerateStoryboardRequest,
    user_id: int = Depends(current_user_id),
) -> dict[str, Any]:
    """Render this episode: one tone sheet to anchor the look, then a frame per shot."""
    with db() as session:
        project = owned_project(session, project_id, user_id)
        episode = resolve_episode(session, project_id, episode_id)
        scenes = episode_scenes(session, episode.id)
        if not scenes:
            raise HTTPException(400, "no shots in this episode, split the script first")
        pending = _selected_scenes(scenes, body.scene_ids)
        if not pending:
            raise HTTPException(400, "every shot in this episode is locked, unlock one to regenerate")

        previous = None
        if body.previous_episode_id:
            previous = resolve_episode(session, project_id, body.previous_episode_id)
            if previous.id == episode.id:
                raise HTTPException(400, "previousEpisodeId must be a different episode")

        config = active_model_config(session, user_id, "image", "分镜图片生成")
        require_model_balance(session, user_id, config)
        if config["provider"] not in {"openai", "gemini", "qwen"}:
            raise HTTPException(400, "image generation currently only supports provider openai/gemini/qwen")

        # The lock stays on the project: one run owns the series, so a second episode cannot
        # start rendering into the same worker pool while this one is going.
        claim_project_status(session, project_id, allowed_from=IDLE_STATUSES, to="generating")
        touch_episode(session, episode, status="generating")
        plan = StoryboardPlan(
            project_id=project_id,
            episode_id=episode.id,
            episode_title=episode.title or f"第 {episode.episode_number} 集",
            script=episode.source_text or "",
            style_prompt=project.style_prompt or "",
            negative_prompt=project.negative_prompt or "",
            # Plain dicts, because the run outlives this session.
            scenes=[scene.model_dump() for scene in pending],
            reference_sources=_reference_sources(session, project, previous),
            merge_references=body.merge_references,
            regenerate=body.regenerate,
            existing_tone_path=episode.tone_image_path,
        )

    await broadcast(
        project_id,
        {"type": "PROJECT_UPDATE", "projectId": project_id, "data": {"status": "generating", "episodeId": episode_id}},
    )
    asyncio.create_task(run_storyboard(plan, config, user_id))
    return {
        "projectId": project_id,
        "episodeId": plan.episode_id,
        "status": "generating",
        "shotCount": len(plan.scenes),
        "referenceCount": len(plan.reference_sources),
        "mergeReferences": plan.merge_references,
        # False when an existing tone sheet is being reused rather than resampled.
        "regeneratesToneSheet": plan.regenerate or not plan.existing_tone_path,
    }
