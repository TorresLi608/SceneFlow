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

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from app.core.database import db
from app.models import Scene
from app.core.realtime import broadcast
from app.core import runs
from app.llms.registry import models
from app.services.artifact_service import artifact_absolute_path, media_type_for, signed_url_for_stored
from app.services.generation_service import (
    ERROR_DETAIL_CHARS,
    MAX_REFERENCE_IMAGES,
    clear_generating_episode,
    clear_generating_scenes,
    episode_media_status,
    persist_scene_image,
    scene_event,
    update_episode_row,
    update_project_row,
    update_scene_row,
)
from app.services.media_service import SheetCell, merge_images
from app.services.prompt_compiler import compile_prompt
from app.services.prompt_service import shot_prompt, tone_sheet_prompt
from app.services.usage_service import record_usage, require_model_balance


logger = logging.getLogger(__name__)

# ponytail: tone generation is one provider call; cap a stuck async image task so the
# episode reaches a terminal state instead of keeping the UI in an endless poll.
TONE_SHEET_TIMEOUT_SECONDS = 5 * 60

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
    scene_reference_sources: dict[str, list[tuple[str, str]]] = field(default_factory=dict)
    scene_reference_items: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    merge_references: bool = True
    regenerate: bool = False
    existing_tone_path: str | None = None
    # The image size and quality this series renders at, from its model settings.
    size: str = ""
    quality: str = ""
    max_reference_images: int = MAX_REFERENCE_IMAGES


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
    options: dict[str, Any] = {}
    if plan.size:
        options["size"] = plan.size
    if plan.quality:
        options["quality"] = plan.quality
    if context:
        image = await models.edit_image(
            config["apiKey"],
            config["model"],
            prompt,
            context,
            base_url=config.get("baseUrl", ""),
            provider=config["provider"],
            **options,
        )
    else:
        image = await models.generate_image(
            config["apiKey"],
            config["model"],
            prompt,
            base_url=config.get("baseUrl", ""),
            provider=config["provider"],
            **options,
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
        narration = str(scene.get("narration") or "").strip()
        visual_prompt = str(scene.get("visual_prompt") or "").strip()
        text = visual_prompt or narration
        if not text:
            raise ValueError("该分镜没有内容，先填写分镜描述")
        if narration and visual_prompt and narration != visual_prompt:
            text = f"{narration}\n画面提示词：{visual_prompt}"
        text = compile_prompt(
            text,
            provider=config["provider"],
            model=config["model"],
            references=scene.get("compiledImageReferenceItems") or [],
        )["prompt"]
        prompt = shot_prompt(
            text,
            index + 1,
            len(plan.scenes),
            plan.episode_title,
            plan.style_prompt,
            plan.negative_prompt,
        )
        method = models.edit_image if references else models.generate_image
        image = await method(
            config["apiKey"],
            config["model"],
            prompt,
            *([references] if references else []),
            base_url=config.get("baseUrl", ""),
            provider=config["provider"],
            **({"size": plan.size} if plan.size else {}),
            **({"quality": plan.quality} if plan.quality else {}),
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

    update_episode_row(plan.episode_id, tone_image_path=tone_path, tone_image_status="success", error_message=None)
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


async def run_tone_sheet(
    plan: StoryboardPlan,
    config: dict[str, Any],
    user_id: int,
    cancellation: asyncio.Event | None = None,
) -> None:
    """Produce only the episode's style anchor, as a step the user can approve.

    Split out of `run_storyboard` because the anchor is what every shot in the episode is
    matched against: rendering twenty full-resolution frames against a tone sheet nobody
    looked at is how an episode ends up being paid for twice.

    One provider call, so the cancel flag is checked once — before it starts. There is no
    "between shots" here to stop at, and abandoning a sheet already being drawn would bill
    the user for nothing.
    """
    try:
        if runs.is_cancelled(cancellation):
            logger.info("tone sheet canceled before starting project=%s", plan.project_id)
            update_project_row(plan.project_id, status="idle")
            update_episode_row(plan.episode_id, status="storyboard")
            await broadcast(
                plan.project_id,
                {
                    "type": "PROJECT_UPDATE",
                    "projectId": plan.project_id,
                    "data": {"status": "idle", "episodeId": plan.episode_id, "canceled": True},
                },
            )
            return
        context = build_context_references(plan.reference_sources, merge=plan.merge_references)[: plan.max_reference_images]
        try:
            tone_path = await asyncio.wait_for(
                _anchor(plan, config, user_id, context), timeout=TONE_SHEET_TIMEOUT_SECONDS
            )
        except asyncio.TimeoutError:
            detail = f"基调图生成超过 {TONE_SHEET_TIMEOUT_SECONDS // 60} 分钟，已停止等待"
            logger.warning("tone sheet timed out project=%s episode=%s", plan.project_id, plan.episode_id)
            update_episode_row(
                plan.episode_id,
                tone_image_status="error",
                status="failed",
                error_message=detail,
            )
            update_project_row(plan.project_id, status="failed")
            tone_path = None
    except asyncio.CancelledError:
        logger.info("tone sheet canceled project=%s episode=%s", plan.project_id, plan.episode_id)
        update_episode_row(plan.episode_id, tone_image_status="idle", status="storyboard")
        update_project_row(plan.project_id, status="idle")
        await broadcast(
            plan.project_id,
            {
                "type": "PROJECT_UPDATE",
                "projectId": plan.project_id,
                "data": {"status": "idle", "episodeId": plan.episode_id, "canceled": True},
            },
        )
        return
    finally:
        runs.release(plan.project_id, cancellation)
    status = "storyboard" if tone_path else "failed"
    update_project_row(plan.project_id, status="idle" if tone_path else "failed")
    update_episode_row(plan.episode_id, status=status)
    await broadcast(
        plan.project_id,
        {
            "type": "PROJECT_UPDATE",
            "projectId": plan.project_id,
            "data": {"status": "idle" if tone_path else "failed", "episodeId": plan.episode_id},
        },
    )


async def run_storyboard(
    plan: StoryboardPlan,
    config: dict[str, Any],
    user_id: int,
    cancellation: asyncio.Event | None = None,
) -> None:
    """Anchor the episode, then render its shots against the anchor."""
    try:
        context = build_context_references(plan.reference_sources, merge=plan.merge_references)
        tone_path = await _anchor(plan, config, user_id, context)
        if tone_path is None:
            return

        tone = _load(tone_path, "tone") if plan.max_reference_images else None
        results: list[bool] = []
        skipped = 0
        # Sequential, not fanned out: each shot references the previous shot's render, so the
        # continuity anchor does not exist until its predecessor has landed. This costs
        # wall-clock time and buys the one thing the old parallel path could not deliver.
        previous: Reference | None = None
        for index, scene in enumerate(plan.scenes):
            # Between shots rather than mid-request: a frame the provider is already drawing
            # has been paid for, so finishing it and keeping it is strictly better than
            # throwing it away, and the next one is what the user is actually stopping.
            if runs.is_cancelled(cancellation):
                skipped = len(plan.scenes) - index
                logger.info(
                    "storyboard canceled project=%s episode=%s remaining=%d",
                    plan.project_id,
                    plan.episode_id,
                    skipped,
                )
                break
            scene_context = build_context_references(
                plan.scene_reference_sources.get(scene["id"], []), merge=False
            )
            # Only references represented by the shot's editor mentions are sent. The tone
            # sheet and previous frame are not silently injected into the provider request.
            references = scene_context[: plan.max_reference_images]
            scene = {
                **scene,
                "compiledImageReferenceItems": plan.scene_reference_items.get(scene["id"], []),
            }
            succeeded = await _generate_shot(plan, scene, index, config, user_id, references)
            results.append(succeeded)
            if succeeded:
                previous = _load(_stored_image_path(scene["id"]), "previous") or previous
    except asyncio.CancelledError:
        logger.info("storyboard canceled project=%s episode=%s", plan.project_id, plan.episode_id)
        # A stopped run must not leave a permanent "generating" marker on the rows it was
        # holding — the shot the provider was drawing, and the tone sheet when the stop
        # landed during the anchor. Both guards skip whatever already succeeded.
        clear_generating_scenes([scene["id"] for scene in plan.scenes], "image_status")
        clear_generating_episode(plan.episode_id, "tone_image_status")
        update_project_row(plan.project_id, status="idle")
        update_episode_row(plan.episode_id, status="storyboard")
        await broadcast(
            plan.project_id,
            {
                "type": "PROJECT_UPDATE",
                "projectId": plan.project_id,
                "data": {"status": "idle", "episodeId": plan.episode_id, "canceled": True},
            },
        )
        return
    finally:
        runs.release(plan.project_id, cancellation)

    status = episode_media_status(plan.episode_id, results)
    if skipped:
        # A stopped run is not a failed one. Reporting `failed` would tell the user their
        # render broke when in fact they stopped it, and would hide the frames that landed.
        status = "partial" if any(results) else "idle"
    logger.info(
        "storyboard finished project=%s episode=%s shots=%d skipped=%d status=%s",
        plan.project_id,
        plan.episode_id,
        len(plan.scenes),
        skipped,
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
            "data": {"status": status, "episodeId": plan.episode_id, "canceled": bool(skipped)},
        },
    )
