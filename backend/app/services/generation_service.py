from __future__ import annotations

import asyncio
import time
from typing import Any

from sqlalchemy import update

from app.core.config import PRIVATE_GENERATED_DIR
from app.core.database import db
from app.core.realtime import broadcast
from app.llms.registry import models
from app.models import Project, Scene
from app.services.artifact_service import save_binary_artifact, signed_file_url
from app.services.usage_service import record_usage, require_model_balance
from app.services.tts_service import synthesize
from app.utils.common import now


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


async def run_generation(project_id: str, scenes: list[dict[str, Any]], config: dict[str, Any], audio_config: dict[str, Any], user_id: int) -> None:
    semaphore = asyncio.Semaphore(3)

    async def one(scene: dict[str, Any]) -> None:
        async with semaphore:
            await broadcast(project_id, {"type": "SCENE_UPDATE", "projectId": project_id, "sceneId": scene["id"], "data": {"imageStatus": "generating", "imageProgress": 5, "audioStatus": "generating", "audioProgress": 0, "errorMsg": ""}})
            _update_scene(scene["id"], image_status="generating")
            try:
                started_at = time.monotonic()
                prompt = build_image_prompt(scene)
                with db() as session:
                    require_model_balance(session, user_id, config)
                await broadcast(project_id, {"type": "SCENE_UPDATE", "projectId": project_id, "sceneId": scene["id"], "data": {"imageStatus": "generating", "imageProgress": 20, "errorMsg": ""}})
                if config["provider"] not in {"openai", "gemini"}:
                    raise ValueError("image generation currently only supports provider openai/gemini")
                image = await models.generate_image(config["apiKey"], config["model"], prompt, base_url=config.get("baseUrl", ""), provider=config["provider"])
                record_usage(user_id, config, "storyboard_image", started_at, quantity=1)
                image_url = persist_scene_image(project_id, scene["id"], image.data, image.format)
                _update_scene(scene["id"], image_status="success", image_url=image_url)
                await broadcast(project_id, {"type": "SCENE_UPDATE", "projectId": project_id, "sceneId": scene["id"], "data": {"imageStatus": "success", "imageProgress": 100, "imageUrl": image_url, "errorMsg": ""}})
            except Exception as exc:
                _update_scene(scene["id"], image_status="error")
                await broadcast(project_id, {"type": "SCENE_UPDATE", "projectId": project_id, "sceneId": scene["id"], "data": {"imageStatus": "error", "imageProgress": 0, "errorMsg": "AI 图片生成失败：" + str(exc)[:220]}})

            try:
                await broadcast(project_id, {"type": "SCENE_UPDATE", "projectId": project_id, "sceneId": scene["id"], "data": {"audioStatus": "generating", "audioProgress": 20, "errorMsg": ""}})
                extension = "mp3" if audio_config["provider"] == "edge" else "wav"
                audio_path = PRIVATE_GENERATED_DIR / "projects" / project_id / f"{scene['id']}.{extension}"
                audio_started_at = time.monotonic()
                audio_path, duration = await synthesize(str(scene.get("narration") or ""), audio_config, audio_path)
                audio_path.chmod(0o600)
                if audio_config["provider"] not in {"edge", "system"}:
                    record_usage(user_id, audio_config, "scene_tts", audio_started_at, quantity=duration)
                audio_url = signed_file_url(
                    audio_path,
                    audio_path.name,
                    "audio/mpeg" if extension == "mp3" else "audio/wav",
                )
                _update_scene(scene["id"], audio_status="success", audio_url=audio_url, audio_duration=duration)
                await broadcast(project_id, {"type": "SCENE_UPDATE", "projectId": project_id, "sceneId": scene["id"], "data": {"audioStatus": "success", "audioProgress": 100, "audioUrl": audio_url, "audioDuration": duration, "errorMsg": ""}})
            except Exception as exc:
                _update_scene(scene["id"], audio_status="error")
                await broadcast(project_id, {"type": "SCENE_UPDATE", "projectId": project_id, "sceneId": scene["id"], "data": {"audioStatus": "error", "audioProgress": 0, "errorMsg": "AI 配音生成失败：" + str(exc)[:220]}})

    await asyncio.gather(*(one(scene) for scene in scenes))
    _update_project(project_id, status="done")
    await broadcast(project_id, {"type": "PROJECT_UPDATE", "projectId": project_id, "data": {"status": "done"}})


def build_image_prompt(scene: dict[str, Any]) -> str:
    narration = str(scene.get("narration") or "").strip()
    visual = str(scene.get("visual_prompt") or narration).strip()
    return f"Create a cinematic anime storyboard frame for a short video. Keep one clear subject, strong composition, dramatic lighting, high detail, no text, no watermark. Scene narration: {narration}. Visual direction: {visual}."


def persist_scene_image(project_id: str, scene_id: str, data: bytes, ext: str) -> str:
    ext = (ext or "png").strip().lower()
    ext = "jpg" if ext in {"jpg", "jpeg"} else ext if ext in {"png", "webp"} else "png"
    media_type = "image/jpeg" if ext == "jpg" else f"image/{ext}"
    return save_binary_artifact(project_id, f"{scene_id}.{ext}", data, media_type)


async def run_video_generation(project_id: str, model: str) -> None:
    for progress in [10, 25, 40, 60, 75, 90, 100]:
        await asyncio.sleep(0.35)
        _update_project(project_id, video_progress=progress)
        await broadcast(project_id, {"type": "VIDEO_UPDATE", "projectId": project_id, "data": {"videoStatus": "generating", "videoProgress": progress, "videoModel": model}})
    video_url = f"https://example.com/video/{project_id}.mp4"
    _update_project(project_id, status="done", video_status="success", video_progress=100, video_url=video_url)
    await broadcast(project_id, {"type": "PROJECT_UPDATE", "projectId": project_id, "data": {"status": "done", "videoStatus": "success", "videoUrl": video_url, "videoModel": model}})
