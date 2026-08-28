from __future__ import annotations

import asyncio
import base64
import logging
import time
from typing import Any

from sqlalchemy import update
from sqlmodel import select

from app.core.database import db
from app.core.realtime import broadcast
from app.core import runs
from app.llms.registry import models
from app.models import Episode, Project, Scene
from app.services.artifact_service import (
    artifact_absolute_path,
    media_type_for,
    signed_url_for_stored,
    store_artifact,
)
from app.services.usage_service import record_usage, require_model_balance
from app.services.video_service import generate_video
from app.services.prompt_compiler import compile_prompt
from app.utils.common import now


logger = logging.getLogger(__name__)

MAX_CONCURRENT_SCENES = 3
MAX_CONCURRENT_VIDEO_SCENES = 2
ERROR_DETAIL_CHARS = 220
# Providers cap how many reference images one request may carry, and a crowd scene would
# blow past it. The cast is ordered, so this keeps the characters that matter most.
MAX_REFERENCE_IMAGES = 4


def update_scene_row(scene_id: str, **values: Any) -> None:
    with db() as session:
        session.execute(
            update(Scene).where(Scene.id == scene_id).values(updated_at=now(), **values),
            execution_options={"synchronize_session": False},
        )


def clear_generating_scenes(scene_ids: list[str], column: str) -> None:
    """Drop the `generating` marker a stopped run left behind, and only that.

    Guarded on the current value rather than written blind: a cancelled batch used to reset
    *every* shot it had been given, so a frame that had already landed came back as
    "not generated yet" and the next run re-rendered — and re-paid for — work the provider
    had already been billed for. Only a shot that never finished is reset.
    """
    if not scene_ids:
        return
    with db() as session:
        session.execute(
            update(Scene)
            .where(Scene.id.in_(scene_ids), getattr(Scene, column) == "generating")
            .values(updated_at=now(), **{column: "idle"}),
            execution_options={"synchronize_session": False},
        )


def clear_generating_episode(episode_id: str, column: str) -> None:
    """The same guard as `clear_generating_scenes`, for an episode's own status columns.

    Blind here would be worse than useless: a run cancelled *after* its tone sheet landed
    would throw the anchor away and resample the episode's whole look on the next attempt.
    """
    with db() as session:
        session.execute(
            update(Episode)
            .where(Episode.id == episode_id, getattr(Episode, column) == "generating")
            .values(updated_at=now(), **{column: "idle"}),
            execution_options={"synchronize_session": False},
        )


def update_project_row(project_id: str, **values: Any) -> None:
    with db() as session:
        session.execute(
            update(Project).where(Project.id == project_id).values(updated_at=now(), **values),
            execution_options={"synchronize_session": False},
        )


def update_episode_row(episode_id: str, **values: Any) -> None:
    with db() as session:
        session.execute(
            update(Episode).where(Episode.id == episode_id).values(updated_at=now(), **values),
            execution_options={"synchronize_session": False},
        )


async def scene_event(project_id: str, scene_id: str, **data: Any) -> None:
    await broadcast(project_id, {"type": "SCENE_UPDATE", "projectId": project_id, "sceneId": scene_id, "data": data})


def character_references(scene: dict[str, Any]) -> list[tuple[str, bytes, str]]:
    """Reference portraits for the cast of a shot, so a face carries across episodes.

    A portrait whose file is gone is skipped rather than failing the render: losing
    consistency is a smaller harm than losing the shot.
    """
    references: list[tuple[str, bytes, str]] = []
    for character in scene.get("characters") or []:
        stored = character.get("reference_image_path")
        if not stored:
            continue
        try:
            path = artifact_absolute_path(stored)
            data = path.read_bytes()
        except (ValueError, OSError):
            logger.info("skipping unreadable reference portrait character=%s", character.get("id"))
            continue
        references.append((path.name, data, media_type_for(path.name)))
        if len(references) == MAX_REFERENCE_IMAGES:
            break
    return references


async def _generate_scene_image(project_id: str, scene: dict[str, Any], config: dict[str, Any], user_id: int) -> bool:
    scene_id = scene["id"]
    preserve_error = any(scene.get(field) == "error" for field in ("audio_status", "video_status"))
    values: dict[str, Any] = {"image_status": "generating"}
    if not preserve_error:
        values["error_message"] = None
    update_scene_row(scene_id, **values)
    await scene_event(project_id, scene_id, imageStatus="generating", imageProgress=5, **({} if preserve_error else {"errorMsg": ""}))
    try:
        started_at = time.monotonic()
        with db() as session:
            require_model_balance(session, user_id, config)
        if config["provider"] not in {"openai", "gemini", "qwen"}:
            raise ValueError("image generation currently only supports provider openai/gemini/qwen")
        await scene_event(project_id, scene_id, imageStatus="generating", imageProgress=20, errorMsg="")
        references: list[tuple[str, bytes, str]] = []
        if scene.get("explicitReferences"):
            for stored in scene.get("referenceImagePaths") or []:
                try:
                    path = artifact_absolute_path(stored)
                    references.append((path.name, path.read_bytes(), media_type_for(path.name)))
                except (ValueError, OSError):
                    logger.info("skipping unreadable selected image reference scene=%s", scene_id)
        else:
            references = character_references(scene)
        references = references[: max(0, int(config.get("imageMaxReferenceImages", MAX_REFERENCE_IMAGES)))]
        # Substituted into the shot's own text before the frame template wraps it, so the
        # `图N` the user previewed is the `图N` the model is asked for. Nothing is
        # prepended to an image request, so the numbering starts at the first selection.
        scene = {
            **scene,
            "visual_prompt": compile_prompt(
                str(scene.get("visual_prompt") or ""),
                provider=config["provider"],
                model=config["model"],
                references=scene.get("compiledReferenceItems") or [],
            )["prompt"],
        }
        if references:
            # Image-to-image with the cast's portraits: the appearance prompt alone drifts
            # over a long series, the reference is what actually holds a face steady.
            image = await models.edit_image(
                config["apiKey"],
                config["model"],
                build_image_prompt(scene),
                references,
                base_url=config.get("baseUrl", ""),
                provider=config["provider"],
            )
        else:
            image = await models.generate_image(
                config["apiKey"],
                config["model"],
                build_image_prompt(scene),
                base_url=config.get("baseUrl", ""),
                provider=config["provider"],
            )
        record_usage(user_id, config, "storyboard_image", started_at, quantity=1)
        image_path = persist_scene_image(project_id, scene_id, image.data, image.format)
    except Exception as exc:
        detail = str(exc)[:ERROR_DETAIL_CHARS]
        logger.warning("scene image generation failed project=%s scene=%s: %s", project_id, scene_id, detail)
        # Persisted, not just broadcast: a reload used to lose the reason the shot is blank.
        update_scene_row(scene_id, image_status="error", error_message=f"AI 图片生成失败：{detail}")
        await scene_event(project_id, scene_id, imageStatus="error", imageProgress=0, errorMsg=f"AI 图片生成失败：{detail}")
        return False

    update_scene_row(scene_id, image_status="success", image_path=image_path)
    await scene_event(
        project_id,
        scene_id,
        imageStatus="success",
        imageProgress=100,
        imageUrl=signed_url_for_stored(image_path, f"scene-{scene.get('order_num') or 0}"),
        **({} if preserve_error else {"errorMsg": ""}),
    )
    return True


def terminal_status(outcomes: list[bool]) -> str:
    """Derive the project status from what actually landed.

    A run where every shot failed used to still report `done`, which told the user the
    opposite of the truth.
    """
    if not outcomes or all(outcomes):
        return "done"
    return "partial" if any(outcomes) else "failed"


def episode_media_status(episode_id: str, outcomes: list[bool]) -> str:
    """Keep a successful retry from hiding another shot that is still failed."""
    with db() as session:
        scenes = session.exec(
            select(Scene).where(Scene.episode_id == episode_id, Scene.deleted_at.is_(None))
        ).all()
    has_error = any(
        status == "error"
        for scene in scenes
        for status in (scene.image_status, scene.audio_status, scene.video_status)
    )
    if not has_error:
        return terminal_status(outcomes)
    has_success = any(
        status == "success"
        for scene in scenes
        for status in (scene.image_status, scene.audio_status, scene.video_status)
    )
    return "partial" if has_success else "failed"


async def run_generation(
    project_id: str,
    scenes: list[dict[str, Any]],
    config: dict[str, Any],
    user_id: int,
    episode_id: str | None = None,
    cancellation: asyncio.Event | None = None,
) -> None:
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_SCENES)

    async def one(scene: dict[str, Any]) -> bool | None:
        async with semaphore:
            # Checked after acquiring the slot, not before: a queued shot that has not
            # started costs nothing to skip, and this is the last moment before it would.
            if runs.is_cancelled(cancellation):
                return None
            return await _generate_scene_image(project_id, scene, config, user_id)

    try:
        outcomes = await asyncio.gather(*(one(scene) for scene in scenes))
    except asyncio.CancelledError:
        clear_generating_scenes([scene["id"] for scene in scenes], "image_status")
        update_project_row(project_id, status="idle")
        if episode_id:
            update_episode_row(episode_id, status="storyboard")
        await broadcast(
            project_id,
            {"type": "PROJECT_UPDATE", "projectId": project_id, "data": {"status": "idle", "episodeId": episode_id, "canceled": True}},
        )
        return
    finally:
        runs.release(project_id, cancellation)
    # None marks a shot that never ran. It is neither a success nor a failure, and counting
    # it as either would make a cancelled run report an outcome nobody asked it to produce.
    results = [outcome for outcome in outcomes if outcome is not None]
    skipped = len(outcomes) - len(results)
    status = episode_media_status(episode_id, results) if episode_id else terminal_status(results)
    if skipped:
        status = "partial" if any(results) else "idle"
    logger.info(
        "generation finished project=%s episode=%s scenes=%d skipped=%d status=%s",
        project_id,
        episode_id,
        len(scenes),
        skipped,
        status,
    )
    # Both levels carry the outcome: the project because it holds the busy lock, the
    # episode because that is what the user was actually rendering.
    update_project_row(project_id, status=status)
    if episode_id:
        update_episode_row(episode_id, status=status)
    await broadcast(
        project_id,
        {
            "type": "PROJECT_UPDATE",
            "projectId": project_id,
            "data": {"status": status, "episodeId": episode_id, "canceled": bool(skipped)},
        },
    )


def build_image_prompt(scene: dict[str, Any]) -> str:
    narration = str(scene.get("narration") or "").strip()
    visual = str(scene.get("visual_prompt") or narration).strip()
    prompt = f"Create a cinematic anime storyboard frame for a short video. Keep one clear subject, strong composition, dramatic lighting, high detail, no text, no watermark. Scene narration: {narration}. Visual direction: {visual}."
    framing = ", ".join(
        part for part in (str(scene.get("shot_type") or "").strip(), str(scene.get("camera_move") or "").strip()) if part
    )
    if framing:
        prompt += f" Framing: {framing}."
    # Named, not just pictured: the model holds a described character steadier than an
    # unnamed one, and this is the only consistency lever on providers without references.
    cast = "; ".join(
        f"{character['name']}: {character['appearance_prompt']}"
        for character in scene.get("characters") or []
        if character.get("appearance_prompt")
    )
    if cast:
        prompt += f" Keep these characters consistent — {cast}."
    # The project's house style. Carried on the scene payload because the worker runs after
    # the request session closes and cannot read the project row itself.
    style = str(scene.get("style_prompt") or "").strip()
    if style:
        prompt += f" Overall style: {style}."
    negative = str(scene.get("negative_prompt") or "").strip()
    if negative:
        prompt += f" Avoid: {negative}."
    return prompt


def persist_scene_image(project_id: str, scene_id: str, data: bytes, ext: str) -> str:
    ext = (ext or "png").strip().lower()
    ext = "jpg" if ext in {"jpg", "jpeg"} else ext if ext in {"png", "webp"} else "png"
    return store_artifact("projects", project_id, f"{scene_id}.{ext}", data)


def _stored_media(stored: str) -> dict[str, str]:
    path = artifact_absolute_path(stored)
    data = path.read_bytes()
    return {
        "name": path.name,
        "data": f"data:{media_type_for(path.name)};base64,{base64.b64encode(data).decode('ascii')}",
    }


def _scene_duration(scene: dict[str, Any], options: dict[str, Any], capabilities: dict[str, Any]) -> int:
    """How many seconds this shot runs for.

    The breakdown estimates a length per shot, which is the whole reason it asks the model
    for one — a six-second beat and a two-second reaction rendered at the same fixed
    duration is exactly the pacing problem the estimate exists to fix. A shot that never
    got an estimate falls back to the batch default, and everything is clamped to what the
    model will actually accept rather than refused.
    """
    milliseconds = int(scene.get("duration_ms") or 0)
    seconds = round(milliseconds / 1000) if milliseconds else int(options["duration"])
    minimum = int(capabilities.get("minDuration") or 1)
    maximum = int(capabilities.get("maxDuration") or max(seconds, minimum))
    return min(max(seconds, minimum), maximum)


async def _generate_scene_video(
    project_id: str,
    scene: dict[str, Any],
    config: dict[str, Any],
    user_id: int,
    options: dict[str, Any],
) -> bool:
    scene_id = scene["id"]
    preserve_error = any(scene.get(field) == "error" for field in ("image_status", "audio_status"))
    values: dict[str, Any] = {"video_status": "generating"}
    if not preserve_error:
        values["error_message"] = None
    update_scene_row(scene_id, **values)
    await scene_event(project_id, scene_id, videoStatus="generating", videoProgress=5, **({} if preserve_error else {"errorMsg": ""}))
    try:
        capabilities = config["videoCapabilities"]
        references = []
        if capabilities["referenceImages"] and scene.get("image_path"):
            references.append(_stored_media(scene["image_path"]))
        # How many images the render prepends before the user's own. `图1` in a compiled
        # prompt has to name the slot in the request, and the storyboard frame takes the
        # first one whenever the model accepts images.
        image_offset = len(references)
        if scene.get("explicitReferences") or options.get("explicitReferences"):
            references.extend(_stored_media(stored) for stored in (
                scene.get("referenceImagePaths") or options.get("referenceImagePaths") or []
            ))
        else:
            for _, data, mime_type in character_references(scene):
                if len(references) >= capabilities["maxReferenceImages"]:
                    break
                references.append({"name": "character.png", "data": f"data:{mime_type};base64,{base64.b64encode(data).decode('ascii')}"})
        references = references[: capabilities["maxReferenceImages"]]
        if capabilities["referenceImagesRequired"] and not references:
            raise ValueError("该分镜缺少模型必需的参考图")
        reference_videos = [_stored_media(stored) for stored in (
            scene.get("referenceVideoPaths") or options.get("referenceVideoPaths") or []
        )]
        reference_audios = [_stored_media(stored) for stored in (
            scene.get("referenceAudioPaths") or options.get("referenceAudioPaths") or []
        )]
        if capabilities["referenceAudio"] and options.get("voiceSheetPath"):
            # Backward compatibility for callers that still opt into the merged timbre track.
            reference_audios.append(_stored_media(options["voiceSheetPath"]))
        # The motion prompt first: `visual_prompt` describes a frame, and a clip generated
        # from it tends to hold still. Narration is the last resort.
        prompt = str(
            scene.get("video_prompt") or scene.get("visual_prompt") or scene.get("narration") or ""
        ).strip()
        if not prompt:
            raise ValueError("该分镜缺少画面提示词")
        # Camera and transition reach the video model or nothing does — they are the two
        # things the breakdown works out that the still prompt has no place to carry.
        direction = "；".join(
            part
            for part in (
                f"运镜：{str(scene.get('camera_move') or '').strip()}" if scene.get("camera_move") else "",
                f"转场：{str(scene.get('transition') or '').strip()}" if scene.get("transition") else "",
            )
            if part
        )
        if direction:
            prompt = f"{prompt}\n{direction}"
        prompt = compile_prompt(
            prompt,
            provider=config["provider"],
            model=config["model"],
            references=scene.get("compiledReferenceItems") or options.get("compiledReferenceItems") or [],
            dialogue=str(scene.get("dialogue") or ""),
            image_offset=image_offset,
        )["prompt"]
        previous_prompt = str(scene.get("previous_video_prompt") or "").strip()
        if previous_prompt:
            prompt = (
                f"{prompt}\n连续性约束：本镜开场必须直接承接上一镜结束时的人物姿态、位置、朝向、服装、手持物和环境状态，"
                f"不得无过渡改变。上一镜提示词：{previous_prompt}"
            )
        duration = _scene_duration(scene, options, capabilities)
        started_at = time.monotonic()
        with db() as session:
            require_model_balance(session, user_id, config)
        await scene_event(project_id, scene_id, videoStatus="generating", videoProgress=20, errorMsg="")
        result = await generate_video(
            provider=config["provider"],
            api_key=config["apiKey"],
            model=config["model"],
            prompt=prompt,
            quality=options["quality"],
            aspect_ratio=options["aspectRatio"],
            fps=options["fps"],
            duration=duration,
            prompt_extend=options["promptExtend"],
            output_audio=options.get("outputAudio"),
            references=references,
            reference_videos=reference_videos,
            reference_audios=reference_audios,
            base_url=config.get("baseUrl", ""),
        )
        record_usage(user_id, config, "scene_video", started_at, quantity=duration)
        video_path = store_artifact("projects", project_id, f"{scene_id}.{result.format}", result.data)
    except Exception as exc:
        detail = str(exc)[:ERROR_DETAIL_CHARS]
        logger.warning("scene video generation failed project=%s scene=%s: %s", project_id, scene_id, detail)
        update_scene_row(scene_id, video_status="error", error_message=f"AI 视频生成失败：{detail}")
        await scene_event(project_id, scene_id, videoStatus="error", videoProgress=0, errorMsg=f"AI 视频生成失败：{detail}")
        return False

    update_scene_row(scene_id, video_status="success", video_path=video_path)
    await scene_event(
        project_id,
        scene_id,
        videoStatus="success",
        videoProgress=100,
        videoUrl=signed_url_for_stored(video_path, f"scene-{scene.get('order_num') or 0}"),
        **({} if preserve_error else {"errorMsg": ""}),
    )
    return True


async def run_video_generation(
    project_id: str,
    scenes: list[dict[str, Any]],
    config: dict[str, Any],
    user_id: int,
    episode_id: str,
    options: dict[str, Any],
    cancellation: asyncio.Event | None = None,
) -> None:
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_VIDEO_SCENES)
    completed = 0
    completed_lock = asyncio.Lock()

    async def run(scene: dict[str, Any]) -> bool | None:
        nonlocal completed
        async with semaphore:
            if runs.is_cancelled(cancellation):
                return None
            succeeded = await _generate_scene_video(project_id, scene, config, user_id, options)
        async with completed_lock:
            completed += 1
            progress = round(completed / len(scenes) * 100)
            update_project_row(project_id, video_progress=progress)
            update_episode_row(episode_id, video_progress=progress)
            await broadcast(project_id, {"type": "VIDEO_UPDATE", "projectId": project_id, "data": {"videoStatus": "generating", "videoProgress": progress, "videoModel": config["model"]}})
        return succeeded

    try:
        outcomes = await asyncio.gather(*(run(scene) for scene in scenes))
    except asyncio.CancelledError:
        clear_generating_scenes([scene["id"] for scene in scenes], "video_status")
        update_project_row(project_id, status="idle", video_status="idle", video_progress=0)
        update_episode_row(episode_id, status="storyboard", video_status="idle", video_progress=0)
        await broadcast(
            project_id,
            {"type": "PROJECT_UPDATE", "projectId": project_id, "data": {"status": "idle", "videoStatus": "idle", "episodeId": episode_id, "canceled": True}},
        )
        return
    finally:
        runs.release(project_id, cancellation)
    results = [outcome for outcome in outcomes if outcome is not None]
    skipped = len(outcomes) - len(results)
    successes = sum(results)
    batch_status = terminal_status(results)
    status = episode_media_status(episode_id, results)
    video_status = "success" if batch_status == "done" and not skipped else "error" if not skipped else "idle"
    detail = ""
    if skipped:
        status = "partial" if any(results) else "idle"
        detail = f"已停止，剩余 {skipped} 个分镜未生成"
    elif batch_status != "done":
        detail = f"{len(results) - successes} 个分镜视频生成失败"
    update_project_row(project_id, status=status, video_status=video_status, video_progress=100, video_url=None)
    update_episode_row(episode_id, status=status, video_status=video_status, video_progress=100, error_message=detail or None)
    await broadcast(project_id, {"type": "PROJECT_UPDATE", "projectId": project_id, "data": {"status": status, "videoStatus": video_status, "videoProgress": 100, "videoModel": config["model"], "canceled": bool(skipped)}})
