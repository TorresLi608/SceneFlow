"""Episode CRUD, script breakdown, and storyboard rendering. A series' content hangs off these rows."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import update

from app.api.deps import current_user_id
from app.core.database import db
from app.core.realtime import broadcast
from app.core import runs
from app.services.character_service import scene_cast
from app.llms.registry import models
from app.models import Episode, Project, Scene
from app.schemas.requests import (
    BreakdownEpisodeRequest,
    CreateEpisodeRequest,
    GenerateStoryboardRequest,
    GenerateToneSheetRequest,
    UpdateEpisodeRequest,
)
from app.schemas.serializers import episode_json, episode_summary_json, scene_json
from app.services import breakdown_service
from app.services.config_service import project_model_config
from app.services.episode_service import (
    create_episode,
    delete_episode,
    episode_scenes,
    episodes_for,
    resolve_episode,
    scene_counts,
    touch_episode,
)
from app.services.project_service import (
    IDLE_STATUSES,
    claim_project_status,
    owned_project,
    release_project_status,
    scenes_with_assets,
    selected_scenes,
)
from app.services.prompt_service import with_shot_label
from app.services.reference_service import resolve_generation_references, stored_generation_references
from app.services.storyboard_service import StoryboardPlan, run_storyboard, run_tone_sheet
from app.services.usage_service import record_usage, require_model_balance
from app.utils.common import new_id, now


logger = logging.getLogger(__name__)

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


def _previous_episode(session, project_id: str, episode: Episode, previous_id: str | None) -> Episode | None:
    if not previous_id:
        return None
    previous = resolve_episode(session, project_id, previous_id)
    if previous.id == episode.id:
        raise HTTPException(400, "previousEpisodeId must be a different episode")
    return previous


def _image_config(session, user_id: int, project) -> dict[str, Any]:
    config = project_model_config(session, user_id, project, "image", "分镜图片生成")
    require_model_balance(session, user_id, config)
    if config["provider"] not in {"openai", "gemini", "qwen"}:
        raise HTTPException(400, "image generation currently only supports provider openai/gemini/qwen")
    return config


def _shot_values(draft: Any, target: str, order: int) -> dict[str, Any]:
    """Columns a drafted shot writes, narrowed to what this target actually produced.

    Both prompts are re-labelled from `order` rather than trusting the model's own
    numbering: it drops the opener often enough, and the number has to survive shots being
    inserted, deleted or reordered afterwards.
    """
    values: dict[str, Any] = {}
    if target in {"shots", "both"}:
        values.update(
            narration=draft.narration,
            visual_prompt=with_shot_label(draft.visualPrompt, order),
            dialogue=draft.dialogue,
            shot_type=draft.shotType,
        )
    if target in {"video", "both"}:
        values.update(
            camera_move=draft.cameraMove,
            transition=draft.transition,
            video_prompt=with_shot_label(draft.videoPrompt, order),
            # Seconds in, milliseconds out: the column is milliseconds like every other
            # duration here, but a model asked for milliseconds guesses far worse.
            duration_ms=draft.durationSeconds * 1000,
        )
    return values


def _replace_shots(project_id: str, episode_id: str, drafts: list[Any], source_text: str, target: str) -> None:
    """Swap one episode's storyboard for a freshly broken-down one.

    Scoped to the episode, so the rest of the series is untouched. Any render of this
    episode describes shots that no longer exist, so it is cleared along with them.
    """
    stamp = now()
    with db() as session:
        session.execute(
            update(Project)
            .where(Project.id == project_id)
            .values(status="idle", video_status="idle", video_progress=0, video_url=None, updated_at=stamp),
            execution_options={"synchronize_session": False},
        )
        session.execute(
            update(Episode)
            .where(Episode.id == episode_id)
            .values(
                status="storyboard",
                source_text=source_text,
                video_status="idle",
                video_progress=0,
                video_path=None,
                updated_at=stamp,
            ),
            execution_options={"synchronize_session": False},
        )
        session.execute(
            update(Scene)
            .where(Scene.episode_id == episode_id, Scene.deleted_at.is_(None))
            .values(deleted_at=stamp, updated_at=stamp),
            execution_options={"synchronize_session": False},
        )
        # Speakers resolved up front: `add_all` over a generator that also queries would
        # interleave reads with pending inserts on the same session.
        speakers = [breakdown_service.resolve_speaker(session, project_id, draft.speaker) for draft in drafts]
        session.add_all(
            Scene(
                id=new_id("scene"),
                created_at=stamp,
                updated_at=stamp,
                project_id=project_id,
                episode_id=episode_id,
                order_num=index,
                image_status="idle",
                audio_status="idle",
                speaker_character_id=speaker,
                **_shot_values(draft, target, index),
            )
            for index, (draft, speaker) in enumerate(zip(drafts, speakers), start=1)
        )


def _apply_video_shots(project_id: str, scenes: list[Scene], drafts: list[Any]) -> None:
    """Write motion directions onto shots that already exist.

    In place rather than a replace: the frames these shots have already rendered cost money,
    and re-deriving how the camera moves is no reason to throw them away.
    """
    stamp = now()
    with db() as session:
        for index, (scene, draft) in enumerate(zip(scenes, drafts), start=1):
            session.execute(
                update(Scene)
                .where(Scene.id == scene.id)
                .values(updated_at=stamp, **_shot_values(draft, "video", scene.order_num or index)),
                execution_options={"synchronize_session": False},
            )


@router.post("/{project_id}/episodes/{episode_id}/breakdown")
async def breakdown_episode(
    project_id: str,
    episode_id: str,
    body: BreakdownEpisodeRequest,
    user_id: int = Depends(current_user_id),
) -> dict[str, Any]:
    """Split this episode's script into shots, motion directions, or both.

    Re-splitting is destructive: the old flow silently deleted every generated image. When
    there is something to lose, the first call reports what it would discard and the client
    repeats with `replaceAll` once the user has agreed. `target: "video"` never triggers
    this, because it updates the existing rows rather than replacing them.
    """
    with db() as session:
        project = owned_project(session, project_id, user_id)
        episode = resolve_episode(session, project_id, episode_id)
        script = (body.script if body.script is not None else episode.source_text or "").strip()
        if not script:
            raise HTTPException(400, "script is required")
        if body.detail_level == "custom" and not (body.detail_prompt or "").strip():
            raise HTTPException(400, "detailPrompt is required when detailLevel is custom")
        existing = episode_scenes(session, episode.id)
        if body.target == "video" and not existing:
            raise HTTPException(400, "no shots to annotate, split the script into shots first")

        # Re-splitting replaces the episode's shot rows, so it must be confirmed even when
        # the existing shots have no rendered files yet. Generated media is only the stronger
        # warning case; the destructive operation is replacing the rows themselves.
        if body.target != "video" and existing and not body.replace_all:
            generated = scenes_with_assets(existing)
            return {
                "projectId": project_id,
                "episodeId": episode.id,
                "target": body.target,
                "applied": False,
                "discardsGeneratedScenes": len(generated),
                "discardsScenes": len(existing),
                "scenes": [scene_json(scene) for scene in existing],
            }

        references = body.references
        context = {
            "characters": breakdown_service.character_context(session, project_id, references.character_ids),
            "props": breakdown_service.prop_context(session, project_id, references.prop_ids),
            "voices": breakdown_service.voice_context(session, project_id, references.voice_profile_ids),
        }
        existing_payload = [scene.model_dump() for scene in existing]
        user_prompt = breakdown_service.build_user_prompt(
            episode=episode,
            script=script,
            target=body.target,
            detail_level=body.detail_level,
            detail_prompt=body.detail_prompt,
            use_cast_sheet=references.use_cast_sheet,
            use_prop_sheet=references.use_prop_sheet,
            use_voice_sheet=references.use_voice_sheet,
            existing_shots=existing_payload,
            **context,
        )
        config = project_model_config(session, user_id, project, "script", "分镜拆解")
        require_model_balance(session, user_id, config)
        claim_project_status(session, project_id, allowed_from=IDLE_STATUSES, to="parsing")

    await broadcast(project_id, {"type": "PROJECT_UPDATE", "projectId": project_id, "data": {"status": "parsing"}})
    started_at = time.monotonic()
    try:
        result = await models.breakdown_script(
            config["provider"],
            config["apiKey"],
            body.model or config["model"],
            breakdown_service.system_prompt(),
            user_prompt,
            config.get("baseUrl", ""),
        )
        record_usage(user_id, config, f"script_breakdown_{body.target}", started_at, result.usage)

        if body.target == "video":
            # Zipped positionally, so a model that returned a different number of shots annotates
            # the ones it did line up with rather than corrupting the whole episode.
            _apply_video_shots(project_id, existing, result.shots)
        else:
            _replace_shots(project_id, episode_id, result.shots, script, body.target)
    except Exception as exc:
        logger.exception("breakdown failed project=%s episode=%s", project_id, episode_id)
        raise HTTPException(502, f"failed to break down script: {str(exc)[:220]}") from exc
    finally:
        # Every claimed run must release the project, including usage-recording and DB-write
        # failures after the provider call has already succeeded.
        release_project_status(project_id)

    with db() as session:
        owned_project(session, project_id, user_id)
        episode = resolve_episode(session, project_id, episode_id)
        data = _detail(session, episode)
    await broadcast(
        project_id,
        {
            "type": "PROJECT_UPDATE",
            "projectId": project_id,
            "data": {"status": "idle", "episodeId": episode_id, "sceneCount": len(data["scenes"])},
        },
    )
    return {
        "projectId": project_id,
        "episodeId": episode_id,
        "target": body.target,
        "detailLevel": body.detail_level,
        "applied": True,
        "discardsGeneratedScenes": 0,
        "shotCount": len(result.shots),
        "scenes": data["scenes"],
    }


def _plan(
    project: Project,
    episode: Episode,
    scenes: list[Scene],
    sources: list[tuple[str, str]],
    *,
    merge_references: bool,
    regenerate: bool,
    max_reference_images: int,
    scene_reference_sources: dict[str, list[tuple[str, str]]] | None = None,
    scene_reference_items: dict[str, list[dict[str, Any]]] | None = None,
) -> StoryboardPlan:
    """Everything a background render needs, resolved before the session closes."""
    return StoryboardPlan(
        project_id=project.id,
        episode_id=episode.id,
        episode_title=episode.title or f"第 {episode.episode_number} 集",
        script=episode.source_text or "",
        style_prompt=project.style_prompt or "",
        negative_prompt=project.negative_prompt or "",
        # Plain dicts, because the run outlives this session.
        scenes=[scene.model_dump() for scene in scenes],
        reference_sources=sources,
        merge_references=merge_references,
        regenerate=regenerate,
        existing_tone_path=episode.tone_image_path,
        size=(project.image_ratio or "").strip(),
        quality=(project.image_resolution or "").strip(),
        max_reference_images=max_reference_images,
        scene_reference_sources=scene_reference_sources or {},
        scene_reference_items=scene_reference_items or {},
    )


def _requested_reference_sources(session, project: Project, previous: Episode | None, references) -> list[tuple[str, str]]:
    if references is None:
        return _reference_sources(session, project, previous)
    resolved = resolve_generation_references(session, project.id, [(item.kind, item.id) for item in references])
    if resolved["videos"] or resolved["audios"]:
        raise HTTPException(400, "tone and storyboard generation only accept image references")
    return resolved["images"]


@router.post("/{project_id}/episodes/{episode_id}/tone-sheet", status_code=202)
async def generate_tone_sheet(
    project_id: str,
    episode_id: str,
    body: GenerateToneSheetRequest,
    user_id: int = Depends(current_user_id),
) -> dict[str, Any]:
    """Anchor this episode's look, without rendering any shots against it yet.

    Its own step because the anchor decides lighting, palette, and render style for every
    frame that follows: approving it first is much cheaper than discovering after twenty
    full-resolution renders that the episode looks wrong.
    """
    with db() as session:
        project = owned_project(session, project_id, user_id)
        episode = resolve_episode(session, project_id, episode_id)
        scenes = episode_scenes(session, episode.id)
        if not scenes:
            raise HTTPException(400, "no shots in this episode, split the script first")
        previous = _previous_episode(session, project_id, episode, body.previous_episode_id)
        config = _image_config(session, user_id, project)
        maximum = max(0, int(config.get("imageMaxReferenceImages", 4)))
        sources = _requested_reference_sources(session, project, previous, body.references)
        if body.references is not None and sources and maximum == 0:
            raise HTTPException(400, "selected image model does not accept reference images")
        claim_project_status(session, project_id, allowed_from=IDLE_STATUSES, to="generating")
        touch_episode(session, episode, status="generating")
        plan = _plan(
            project,
            episode,
            scenes,
            sources,
            merge_references=True if body.references is not None else body.merge_references,
            regenerate=body.regenerate,
            max_reference_images=maximum,
        )

    await broadcast(
        project_id,
        {"type": "PROJECT_UPDATE", "projectId": project_id, "data": {"status": "generating", "episodeId": episode_id}},
    )
    cancellation = runs.register(project_id)
    task = asyncio.create_task(run_tone_sheet(plan, config, user_id, cancellation=cancellation))
    runs.attach_task(project_id, cancellation, task)
    return {
        "projectId": project_id,
        "episodeId": plan.episode_id,
        "status": "generating",
        "regeneratesToneSheet": plan.regenerate or not plan.existing_tone_path,
    }


@router.post("/{project_id}/episodes/{episode_id}/storyboard", status_code=202)
async def generate_storyboard(
    project_id: str,
    episode_id: str,
    body: GenerateStoryboardRequest,
    user_id: int = Depends(current_user_id),
) -> dict[str, Any]:
    """Render this episode's shots against the tone sheet that anchors them.

    The anchor is generated here when it does not exist yet, so a caller that skipped the
    explicit step still gets an anchored render rather than twenty unrelated frames.
    """
    with db() as session:
        project = owned_project(session, project_id, user_id)
        episode = resolve_episode(session, project_id, episode_id)
        scenes = episode_scenes(session, episode.id)
        if not scenes:
            raise HTTPException(400, "no shots in this episode, split the script first")
        pending = selected_scenes(
            scenes, body.scene_ids, status_column="image_status", pending_only=body.pending_only
        )

        previous = _previous_episode(session, project_id, episode, body.previous_episode_id)
        config = _image_config(session, user_id, project)
        maximum = max(0, int(config.get("imageMaxReferenceImages", 4)))
        sources = _requested_reference_sources(session, project, previous, body.references)
        selected_limit = maximum
        if body.references is not None and len(sources) > selected_limit:
            raise HTTPException(400, f"selected image model accepts at most {selected_limit} additional references")
        scene_sources: dict[str, list[tuple[str, str]]] = {}
        scene_reference_items: dict[str, list[dict[str, Any]]] = {}
        if body.references is None:
            for scene in pending:
                pairs = stored_generation_references(scene.image_references_json)
                if scene.image_references_explicit and not pairs:
                    continue
                if not pairs:
                    continue
                resolved = resolve_generation_references(session, project_id, pairs)
                if resolved["videos"] or resolved["audios"]:
                    raise HTTPException(400, "image prompts only accept image references")
                if len(resolved["images"]) > selected_limit:
                    raise HTTPException(400, f"selected image model accepts at most {selected_limit} additional references")
                scene_sources[scene.id] = resolved["images"]
                scene_reference_items[scene.id] = [
                    item for item in resolved["items"] if item.get("media") == "image"
                ]

        # The lock stays on the project: one run owns the series, so a second episode cannot
        # start rendering into the same worker pool while this one is going.
        claim_project_status(session, project_id, allowed_from=IDLE_STATUSES, to="generating")
        touch_episode(session, episode, status="generating")
        plan = _plan(
            project,
            episode,
            pending,
            sources,
            merge_references=False if body.references is not None else body.merge_references,
            regenerate=body.regenerate,
            max_reference_images=maximum,
            scene_reference_sources=scene_sources,
            scene_reference_items=scene_reference_items,
        )

    await broadcast(
        project_id,
        {"type": "PROJECT_UPDATE", "projectId": project_id, "data": {"status": "generating", "episodeId": episode_id}},
    )
    cancellation = runs.register(project_id)
    task = asyncio.create_task(run_storyboard(plan, config, user_id, cancellation=cancellation))
    runs.attach_task(project_id, cancellation, task)
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
