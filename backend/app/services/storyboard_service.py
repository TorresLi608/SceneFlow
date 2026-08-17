"""Storyboard rendering: anchor the episode's look once, then render each shot against it.

The problem this solves is coherence. Rendering shots independently gives every frame its
own sampling of lighting, palette, set dressing, and render style; the cast sheet pins faces
and nothing else. So an episode is rendered in two passes:

1. **Tone sheet.** One image holding thumbnails of every shot, generated in a single pass.
   Never a deliverable — each cell is far too small — but one sampling is what makes the
   whole episode agree with itself.
2. **Per-shot renders.** Each shot at full resolution, carrying the tone sheet, the merged
   context sheet (cast, props, and optionally the previous episode's anchor), and the
   previous shot's render. Style, cast, and scene continuity each get their own anchor.

If the tone sheet fails the batch stops: rendering shots without the anchor is the very
thing this module exists to avoid, and it would bill the user for the privilege.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from app.core.database import db
from app.models import Scene
from app.core.realtime import broadcast
from app.llms.registry import models
from app.services.artifact_service import artifact_absolute_path, media_type_for, signed_url_for_stored
from app.services.generation_service import (
    ERROR_DETAIL_CHARS,
    MAX_REFERENCE_IMAGES,
    episode_media_status,
    persist_scene_image,
    scene_event,
    update_episode_row,
    update_project_row,
    update_scene_row,
)
from app.services.media_service import SheetCell, merge_images
from app.services.prompt_service import shot_prompt, tone_sheet_prompt
from app.services.usage_service import record_usage, require_model_balance


logger = logging.getLogger(__name__)

# (filename, bytes, mime type) — the shape `ModelRouter.edit_image` takes.
Reference = tuple[str, bytes, str]


@dataclass
class StoryboardPlan:
    """Everything the background run needs, resolved while the request session is open."""

    project_id: str
    episode_id: str
    episode_title: str
    script: str
    style_prompt: str
    negative_prompt: str
    scenes: list[dict[str, Any]]
    # (stored path, label) for the cast sheet, the prop sheet, and the previous episode's
    # tone sheet — whichever of them exist.
    reference_sources: list[tuple[str, str]] = field(default_factory=list)
    merge_references: bool = True
    regenerate: bool = False
    existing_tone_path: str | None = None


def _load(stored: str | None, label: str) -> Reference | None:
    """Read a stored artifact, or None if it is gone.

    A missing reference costs consistency; failing the render would cost the shot.
    """
    if not stored:
        return None
    try:
        path = artifact_absolute_path(stored)
        return (path.name, path.read_bytes(), media_type_for(path.name))
    except (ValueError, OSError):
        logger.info("skipping unreadable storyboard reference label=%s", label)
        return None


def build_context_references(sources: list[tuple[str, str]], *, merge: bool) -> list[Reference]:
    """The cast sheet, prop sheet, and previous tone sheet, as the model will receive them.

    Merged, they occupy one reference slot instead of three — which matters because providers
    cap reference counts at `MAX_REFERENCE_IMAGES`, and the tone sheet and the previous shot
    each need a slot of their own. Unmerged is offered because tiling costs resolution, and a
    caller may prefer to spend tokens instead.
    """
    loaded = [(reference, label) for stored, label in sources if (reference := _load(stored, label))]
    if not loaded:
        return []
    if not merge:
        return [reference for reference, _ in loaded]
    try:
        sheet = merge_images([SheetCell(data, label) for (_, data, _), label in loaded])
    except ValueError:
        # Nothing tileable after all; pass through whatever did load.
        return [reference for reference, _ in loaded]
    return [("context.jpg", sheet, "image/jpeg")]


async def _generate_tone_sheet(
    plan: StoryboardPlan,
    config: dict[str, Any],
    user_id: int,
    context: list[Reference],
) -> str:
    prompt = tone_sheet_prompt(
        plan.episode_title,
        plan.script,
        [str(scene.get("narration") or scene.get("visual_prompt") or "") for scene in plan.scenes],
        plan.style_prompt,
        plan.negative_prompt,
    )
    started_at = time.monotonic()
    if context:
        image = await models.edit_image(
            config["apiKey"],
            config["model"],
            prompt,
            context,
            base_url=config.get("baseUrl", ""),
            provider=config["provider"],
        )
    else:
        image = await models.generate_image(
            config["apiKey"],
            config["model"],
            prompt,
            base_url=config.get("baseUrl", ""),
            provider=config["provider"],
        )
    record_usage(user_id, config, "storyboard_tone_sheet", started_at, quantity=1)
    return persist_scene_image(plan.project_id, f"{plan.episode_id}-tone", image.data, image.format)


async def _generate_shot(
    plan: StoryboardPlan,
    scene: dict[str, Any],
    index: int,
    config: dict[str, Any],
    user_id: int,
    references: list[Reference],
) -> bool:
    scene_id = scene["id"]
    preserve_error = any(scene.get(column) == "error" for column in ("audio_status", "video_status"))
    values: dict[str, Any] = {"image_status": "generating"}
    if not preserve_error:
        values["error_message"] = None
    update_scene_row(scene_id, **values)
    await scene_event(
        plan.project_id,
        scene_id,
        imageStatus="generating",
        imageProgress=20,
        **({} if preserve_error else {"errorMsg": ""}),
    )
    try:
        started_at = time.monotonic()
        with db() as session:
            require_model_balance(session, user_id, config)
        text = str(scene.get("narration") or scene.get("visual_prompt") or "").strip()
        if not text:
            raise ValueError("该分镜没有内容，先填写分镜描述")
        image = await models.edit_image(
            config["apiKey"],
            config["model"],
            shot_prompt(
                text,
                index + 1,
                len(plan.scenes),
                plan.episode_title,
                plan.style_prompt,
                plan.negative_prompt,
            ),
            references,
            base_url=config.get("baseUrl", ""),
            provider=config["provider"],
        )
        record_usage(user_id, config, "storyboard_image", started_at, quantity=1)
        image_path = persist_scene_image(plan.project_id, scene_id, image.data, image.format)
    except Exception as exc:
        detail = str(exc)[:ERROR_DETAIL_CHARS]
        logger.warning("shot render failed project=%s scene=%s: %s", plan.project_id, scene_id, detail)
        # Persisted, not just broadcast: a reload used to lose the reason the shot is blank.
        update_scene_row(scene_id, image_status="error", error_message=f"AI 图片生成失败：{detail}")
        await scene_event(
            plan.project_id, scene_id, imageStatus="error", imageProgress=0, errorMsg=f"AI 图片生成失败：{detail}"
        )
        return False

    update_scene_row(scene_id, image_status="success", image_path=image_path)
    await scene_event(
        plan.project_id,
        scene_id,
        imageStatus="success",
        imageProgress=100,
        imageUrl=signed_url_for_stored(image_path, f"scene-{scene.get('order_num') or 0}"),
        **({} if preserve_error else {"errorMsg": ""}),
    )
    return True


async def _anchor(plan: StoryboardPlan, config: dict[str, Any], user_id: int, context: list[Reference]) -> str | None:
    """Produce the tone sheet, or None if it failed and the run must stop."""
    if plan.existing_tone_path and not plan.regenerate:
        return plan.existing_tone_path

    update_episode_row(plan.episode_id, tone_image_status="generating")
    await broadcast(
        plan.project_id,
        {
            "type": "EPISODE_UPDATE",
            "projectId": plan.project_id,
            "episodeId": plan.episode_id,
            "data": {"toneImageStatus": "generating"},
        },
    )
    try:
        tone_path = await _generate_tone_sheet(plan, config, user_id, context)
    except Exception as exc:
        detail = str(exc)[:ERROR_DETAIL_CHARS]
        logger.warning("tone sheet failed project=%s episode=%s: %s", plan.project_id, plan.episode_id, detail)
        update_episode_row(
            plan.episode_id,
            tone_image_status="error",
            status="failed",
            error_message=f"基调图生成失败：{detail}",
        )
        update_project_row(plan.project_id, status="failed")
        await broadcast(
            plan.project_id,
            {
                "type": "PROJECT_UPDATE",
                "projectId": plan.project_id,
                "data": {
                    "status": "failed",
                    "episodeId": plan.episode_id,
                    "toneImageStatus": "error",
                    "errorMsg": f"基调图生成失败：{detail}",
                },
            },
        )
        return None

    update_episode_row(plan.episode_id, tone_image_path=tone_path, tone_image_status="success")
    await broadcast(
        plan.project_id,
        {
            "type": "EPISODE_UPDATE",
            "projectId": plan.project_id,
            "episodeId": plan.episode_id,
            "data": {
                "toneImageStatus": "success",
                "toneImageUrl": signed_url_for_stored(tone_path, f"episode-tone-{plan.episode_id}"),
            },
        },
    )
    return tone_path


def _stored_image_path(scene_id: str) -> str | None:
    with db() as session:
        scene = session.get(Scene, scene_id)
        return scene.image_path if scene else None


async def run_storyboard(plan: StoryboardPlan, config: dict[str, Any], user_id: int) -> None:
    """Anchor the episode, then render its shots against the anchor."""
    context = build_context_references(plan.reference_sources, merge=plan.merge_references)
    tone_path = await _anchor(plan, config, user_id, context)
    if tone_path is None:
        return

    tone = _load(tone_path, "tone")
    results: list[bool] = []
    # Sequential, not fanned out: each shot references the previous shot's render, so the
    # continuity anchor does not exist until its predecessor has landed. This costs
    # wall-clock time and buys the one thing the old parallel path could not deliver.
    previous: Reference | None = None
    for index, scene in enumerate(plan.scenes):
        references = [item for item in (tone, *context, previous) if item][:MAX_REFERENCE_IMAGES]
        succeeded = await _generate_shot(plan, scene, index, config, user_id, references)
        results.append(succeeded)
        if succeeded:
            previous = _load(_stored_image_path(scene["id"]), "previous") or previous

    status = episode_media_status(plan.episode_id, results)
    logger.info(
        "storyboard finished project=%s episode=%s shots=%d status=%s",
        plan.project_id,
        plan.episode_id,
        len(plan.scenes),
        status,
    )
    # Both levels carry the outcome: the project because it holds the busy lock, the episode
    # because that is what the user was actually rendering.
    update_project_row(plan.project_id, status=status)
    update_episode_row(plan.episode_id, status=status)
    await broadcast(
        plan.project_id,
        {
            "type": "PROJECT_UPDATE",
            "projectId": plan.project_id,
            "data": {"status": status, "episodeId": plan.episode_id},
        },
    )
