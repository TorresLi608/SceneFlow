from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from sqlalchemy import update

from app.core.config import PRIVATE_GENERATED_DIR
from app.core.database import db
from app.core.realtime import broadcast
from app.llms.registry import models
from app.models import Episode, Project, Scene
from app.services.artifact_service import artifact_relative_path, signed_url_for_stored, store_artifact
from app.services.usage_service import record_usage, require_model_balance
from app.services.tts_service import synthesize
from app.utils.common import now


logger = logging.getLogger(__name__)

MAX_CONCURRENT_SCENES = 3
ERROR_DETAIL_CHARS = 220


def _update_scene(scene_id: str, **values: Any) -> None:
    with db() as session:
        session.execute(
            update(Scene).where(Scene.id == scene_id).values(updated_at=now(), **values),
            execution_options={"synchronize_session": False},
        )


def _update_project(project_id: str, **values: Any) -> None:
    with db() as session:
        session.execute(
            update(Project).where(Project.id == project_id).values(updated_at=now(), **values),
            execution_options={"synchronize_session": False},
        )


def _update_episode(episode_id: str, **values: Any) -> None:
    with db() as session:
        session.execute(
            update(Episode).where(Episode.id == episode_id).values(updated_at=now(), **values),
            execution_options={"synchronize_session": False},
        )


async def _scene_event(project_id: str, scene_id: str, **data: Any) -> None:
    await broadcast(project_id, {"type": "SCENE_UPDATE", "projectId": project_id, "sceneId": scene_id, "data": data})


async def _generate_scene_image(project_id: str, scene: dict[str, Any], config: dict[str, Any], user_id: int) -> bool:
    scene_id = scene["id"]
    _update_scene(scene_id, image_status="generating", error_message=None)
    await _scene_event(project_id, scene_id, imageStatus="generating", imageProgress=5, errorMsg="")
    try:
        started_at = time.monotonic()
        with db() as session:
            require_model_balance(session, user_id, config)
        if config["provider"] not in {"openai", "gemini"}:
            raise ValueError("image generation currently only supports provider openai/gemini")
        await _scene_event(project_id, scene_id, imageStatus="generating", imageProgress=20, errorMsg="")
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
        _update_scene(scene_id, image_status="error", error_message=f"AI 图片生成失败：{detail}")
        await _scene_event(project_id, scene_id, imageStatus="error", imageProgress=0, errorMsg=f"AI 图片生成失败：{detail}")
        return False

    _update_scene(scene_id, image_status="success", image_path=image_path, error_message=None)
    await _scene_event(
        project_id,
        scene_id,
        imageStatus="success",
        imageProgress=100,
        imageUrl=signed_url_for_stored(image_path, f"scene-{scene.get('order_num') or 0}"),
        errorMsg="",
    )
    return True


async def _generate_scene_audio(project_id: str, scene: dict[str, Any], audio_config: dict[str, Any], user_id: int) -> bool:
    scene_id = scene["id"]
    await _scene_event(project_id, scene_id, audioStatus="generating", audioProgress=20, errorMsg="")
    try:
        extension = "mp3" if audio_config["provider"] == "edge" else "wav"
        target = PRIVATE_GENERATED_DIR / "projects" / project_id / f"{scene_id}.{extension}"
        started_at = time.monotonic()
        target, duration = await synthesize(str(scene.get("narration") or ""), audio_config, target)
        target.chmod(0o600)
        if audio_config["provider"] not in {"edge", "system"}:
            record_usage(user_id, audio_config, "scene_tts", started_at, quantity=duration)
        audio_path = artifact_relative_path(target)
    except Exception as exc:
        detail = str(exc)[:ERROR_DETAIL_CHARS]
        logger.warning("scene audio generation failed project=%s scene=%s: %s", project_id, scene_id, detail)
        _update_scene(scene_id, audio_status="error", error_message=f"AI 配音生成失败：{detail}")
        await _scene_event(project_id, scene_id, audioStatus="error", audioProgress=0, errorMsg=f"AI 配音生成失败：{detail}")
        return False

    _update_scene(scene_id, audio_status="success", audio_path=audio_path, audio_duration=duration)
    await _scene_event(
        project_id,
        scene_id,
        audioStatus="success",
        audioProgress=100,
        audioUrl=signed_url_for_stored(audio_path, f"scene-{scene.get('order_num') or 0}"),
        audioDuration=duration,
        errorMsg="",
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


async def run_generation(
    project_id: str,
    scenes: list[dict[str, Any]],
    config: dict[str, Any],
    audio_config: dict[str, Any],
    user_id: int,
    episode_id: str | None = None,
) -> None:
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_SCENES)

    async def one(scene: dict[str, Any]) -> list[bool]:
        async with semaphore:
            image_ok = await _generate_scene_image(project_id, scene, config, user_id)
            audio_ok = await _generate_scene_audio(project_id, scene, audio_config, user_id)
            return [image_ok, audio_ok]

    results = await asyncio.gather(*(one(scene) for scene in scenes))
    status = terminal_status([outcome for scene_result in results for outcome in scene_result])
    logger.info(
        "generation finished project=%s episode=%s scenes=%d status=%s", project_id, episode_id, len(scenes), status
    )
    # Both levels carry the outcome: the project because it holds the busy lock, the
    # episode because that is what the user was actually rendering.
    _update_project(project_id, status=status)
    if episode_id:
        _update_episode(episode_id, status=status)
    await broadcast(
        project_id,
        {"type": "PROJECT_UPDATE", "projectId": project_id, "data": {"status": status, "episodeId": episode_id}},
    )


def build_image_prompt(scene: dict[str, Any]) -> str:
    narration = str(scene.get("narration") or "").strip()
    visual = str(scene.get("visual_prompt") or narration).strip()
    return f"Create a cinematic anime storyboard frame for a short video. Keep one clear subject, strong composition, dramatic lighting, high detail, no text, no watermark. Scene narration: {narration}. Visual direction: {visual}."


def persist_scene_image(project_id: str, scene_id: str, data: bytes, ext: str) -> str:
    ext = (ext or "png").strip().lower()
    ext = "jpg" if ext in {"jpg", "jpeg"} else ext if ext in {"png", "webp"} else "png"
    return store_artifact("projects", project_id, f"{scene_id}.{ext}", data)


async def run_video_generation(project_id: str, model: str) -> None:
    for progress in [10, 25, 40, 60, 75, 90, 100]:
        await asyncio.sleep(0.35)
        _update_project(project_id, video_progress=progress)
        await broadcast(project_id, {"type": "VIDEO_UPDATE", "projectId": project_id, "data": {"videoStatus": "generating", "videoProgress": progress, "videoModel": model}})
    video_url = f"https://example.com/video/{project_id}.mp4"
    _update_project(project_id, status="done", video_status="success", video_progress=100, video_url=video_url)
    await broadcast(project_id, {"type": "PROJECT_UPDATE", "projectId": project_id, "data": {"status": "done", "videoStatus": "success", "videoUrl": video_url, "videoModel": model}})
